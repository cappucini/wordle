"""The WebSocket a page keeps open while it shows a game in progress.

    ws://<host>:8000/api/v1/games/{game_id}/ws

The server sends {"type": "game_updated"} on it whenever the game changes (see app/live.py).
Nothing the page sends is used; the connection only exists to be told about changes.

Who may connect
---------------
The same rules as reading the game, checked once when the connection opens:

  - The session cookie must belong to a signed-in user. The browser sends it with the
    connection request by itself, as it does for ordinary requests.
  - That user must be one of the game's players.
  - If the request names the website it came from (the Origin header, which browsers always
    send), that website must be our own frontend. Browsers do not apply CORS to WebSockets,
    so without this check a page on another site could open this connection using a
    signed-in player's cookie.

A refused connection is closed with a code the page can read:

    4401  not signed in (no session, or it has expired)
    4403  signed in, but not a player in this game
    4404  no such game
    4429  this player already has as many connections open as one player may

An open connection is closed with 4401 when its sign-in is logged out or expires (app/live.py).
"""

# dataclass: writes a class's __init__ for it from the list of its fields
from dataclasses import dataclass
# datetime: the type of a sign-in's expiry time
from datetime import datetime
# UUID: the type of a game's id and a user's id
from uuid import UUID

# APIRouter: collects this file's route so main.py can add it to the app
# WebSocket: one open two-way connection to a page
# WebSocketDisconnect: the error raised when the page on the other end has gone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
# run_in_threadpool: runs an ordinary function on a worker thread and waits for its result
from starlette.concurrency import run_in_threadpool

# the services: user_service looks up the sign-in, game_service looks up the game
from app import game_service, user_service
# the name of the cookie that holds the session token
from app.api.v1.auth import SESSION_COOKIE
# the frontend addresses that are allowed to connect
from app.api.v1.origins import ALLOWED_ORIGINS
# SessionLocal() opens a database session
from app.db import SessionLocal
# the three errors the services raise when the answer is "no"
from app.domain.errors import GameNotFound, NotAPlayer, NotAuthenticated
# the list of open connections per game, kept in app/live.py
from app.live import watchers

# main.py adds this router to the app; the tag groups its route under "games" in the API docs
router = APIRouter(tags=["games"])

# The codes a connection is closed with (listed in the note at the top of this file).
# WebSocket leaves 4000 to 4999 for an application's own use; these echo HTTP's 401, 403,
# 404 and 429. The page has the same numbers in frontend/src/api.js.
CLOSE_NOT_AUTHENTICATED = 4401
CLOSE_NOT_A_PLAYER = 4403
CLOSE_GAME_NOT_FOUND = 4404
CLOSE_TOO_MANY_CONNECTIONS = 4429
# the standard WebSocket code for "this request breaks the rules"
CLOSE_POLICY_VIOLATION = 1008


# @dataclass writes __init__ from the fields listed in the class
@dataclass
class _Access:
    """The answer to "may this request watch this game?"."""

    close_code: int | None = None  # set when the answer is no
    # The other three are set when the answer is yes. They are what watchers.add needs:
    user_id: UUID | None = None  # the player, to count how many connections they hold
    session_hash: str | None = None  # which sign-in opened it, so a log-out can find it
    expires_at: datetime | None = None  # when that sign-in ends, and the connection with it


def _check_access(token: str | None, game_id: UUID) -> _Access:
    """Looks up the sign-in and the game, and says whether this request may watch.

    An ordinary (not async) function because it uses the database; watch_game runs it
    on a worker thread.
    """
    # no session cookie came with the request: not signed in
    if token is None:
        return _Access(close_code=CLOSE_NOT_AUTHENTICATED)
    # A database session just for this check. It is closed again before the connection
    # settles in, so an open WebSocket does not hold a database connection for its lifetime.
    with SessionLocal() as session:
        try:
            # find the sign-in the cookie belongs to; raises NotAuthenticated if there is
            # none or it has expired
            auth_session = user_service.get_auth_session(session, token)
            # called for its checks only: it raises if the game is missing or not theirs
            game_service.get_game(session, auth_session.user, game_id)
        # each error becomes the close code that tells the page what was wrong
        except NotAuthenticated:
            return _Access(close_code=CLOSE_NOT_AUTHENTICATED)
        except GameNotFound:
            return _Access(close_code=CLOSE_GAME_NOT_FOUND)
        except NotAPlayer:
            return _Access(close_code=CLOSE_NOT_A_PLAYER)
        # nothing was raised: a signed-in player of this game. Hand back the three
        # values watch_game needs, so it never has to hold on to a database row.
        return _Access(
            user_id=auth_session.user_id,
            session_hash=auth_session.token_hash,
            expires_at=auth_session.expires_at,
        )


def _sign_in_has_ended(token: str) -> bool:
    """True if the sign-in this token belongs to no longer exists or has expired.

    An ordinary function, for the same reason as _check_access: it uses the database.
    """
    # a short database session of its own, closed again as soon as the answer is known
    with SessionLocal() as session:
        try:
            # called only to see whether it raises; the row it returns is not needed
            user_service.get_auth_session(session, token)
        except NotAuthenticated:
            # logged out or expired since the first check
            return True
        # still a valid sign-in
        return False


# @router.websocket marks this as the handler for WebSocket connections to this address.
# {game_id} in the address is passed in as the game_id parameter, already checked to be a UUID.
# `async def`: the function can pause at each `await` while it waits, and the server looks
# after other connections in the meantime. One of these runs for each open connection.
@router.websocket("/api/v1/games/{game_id}/ws")
async def watch_game(websocket: WebSocket, game_id: UUID):
    """Opens the live connection for one game, after checking who is asking.

    Then waits until the page goes away, and stops sending it notices.
    """
    # A request from another website is turned away before the connection is even opened.
    # the website the request says it came from, or None if it does not say
    origin = websocket.headers.get("origin")
    # None is let through: only browsers are open to this trick, and they always send one
    if origin is not None and origin not in ALLOWED_ORIGINS:
        # closing before accept() refuses the connection outright
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        return

    # the session token from the cookie the browser sent, or None if there is no cookie
    token = websocket.cookies.get(SESSION_COOKIE)
    # the check talks to the database, which would block every other connection if run here
    access = await run_in_threadpool(_check_access, token, game_id)

    # Open the connection first even when refusing: a browser can only read a close code
    # from a connection that was opened, and the page needs the code to know not to retry.
    await websocket.accept()
    # the check said no: close with its code (4401, 4403 or 4404) and stop here
    if access.close_code is not None:
        await websocket.close(code=access.close_code)
        return

    # List this connection under the game, so watchers.notify(game_id) reaches it.
    # add() returns False, and lists nothing, if this player already holds as many
    # connections as one player may.
    added = watchers.add(
        game_id, websocket, access.user_id, access.session_hash, access.expires_at
    )
    if not added:
        await websocket.close(code=CLOSE_TOO_MANY_CONNECTIONS)
        return
    # From here the connection is listed, so everything below sits inside try/finally:
    # however this function ends, the `finally` takes the connection off the list again.
    try:
        # The sign-in was checked a moment ago, before this connection was listed. If the
        # player logged out in between, the log-out found nothing to close, so look once
        # more now that the connection is listed. (A log-out from here on closes it itself.)
        if await run_in_threadpool(_sign_in_has_ended, token):
            await websocket.close(code=CLOSE_NOT_AUTHENTICATED)
            return
        # Nothing the page sends is used. Waiting here is how the server finds out
        # that the page has gone.
        # This loop sends nothing. The "game updated" notices are sent from app/live.py,
        # by whichever request changed the game, while this function is paused here.
        while True:
            # receive() accepts any kind of message, text or binary, and reports the
            # page going away as a message of its own
            message = await websocket.receive()
            # the page closed the connection, or it dropped: stop waiting
            if message["type"] == "websocket.disconnect":
                break
            # anything else the page sent is ignored; go round and wait again
    except WebSocketDisconnect:
        # the page went away while one of the awaits above was waiting; nothing to report
        pass
    finally:
        # runs however the wait above ends, so a gone connection is never left listed
        watchers.remove(game_id, websocket)
