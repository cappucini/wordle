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

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app import game_service, user_service
from app.api.v1.auth import SESSION_COOKIE
from app.api.v1.origins import ALLOWED_ORIGINS
from app.db import SessionLocal
from app.domain.errors import GameNotFound, NotAPlayer, NotAuthenticated
from app.live import watchers

router = APIRouter(tags=["games"])

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
    user_id: UUID | None = None
    session_hash: str | None = None
    expires_at: datetime | None = None


def _check_access(token: str | None, game_id: UUID) -> _Access:
    """Looks up the sign-in and the game, and says whether this request may watch.

    An ordinary (not async) function because it uses the database; watch_game runs it
    on a worker thread.
    """
    if token is None:
        return _Access(close_code=CLOSE_NOT_AUTHENTICATED)
    # A database session just for this check. It is closed again before the connection
    # settles in, so an open WebSocket does not hold a database connection for its lifetime.
    with SessionLocal() as session:
        try:
            auth_session = user_service.get_auth_session(session, token)
            # called for its checks only: it raises if the game is missing or not theirs
            game_service.get_game(session, auth_session.user, game_id)
        except NotAuthenticated:
            return _Access(close_code=CLOSE_NOT_AUTHENTICATED)
        except GameNotFound:
            return _Access(close_code=CLOSE_GAME_NOT_FOUND)
        except NotAPlayer:
            return _Access(close_code=CLOSE_NOT_A_PLAYER)
        return _Access(
            user_id=auth_session.user_id,
            session_hash=auth_session.token_hash,
            expires_at=auth_session.expires_at,
        )


def _sign_in_has_ended(token: str) -> bool:
    """True if the sign-in this token belongs to no longer exists or has expired.

    An ordinary function, for the same reason as _check_access: it uses the database.
    """
    with SessionLocal() as session:
        try:
            user_service.get_auth_session(session, token)
        except NotAuthenticated:
            return True
        return False


@router.websocket("/api/v1/games/{game_id}/ws")
async def watch_game(websocket: WebSocket, game_id: UUID):
    """Opens the live connection for one game, after checking who is asking.

    Then waits until the page goes away, and stops sending it notices.
    """
    # A request from another website is turned away before the connection is even opened.
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        return

    token = websocket.cookies.get(SESSION_COOKIE)
    # the check talks to the database, which would block every other connection if run here
    access = await run_in_threadpool(_check_access, token, game_id)

    # Open the connection first even when refusing: a browser can only read a close code
    # from a connection that was opened, and the page needs the code to know not to retry.
    await websocket.accept()
    if access.close_code is not None:
        await websocket.close(code=access.close_code)
        return

    added = watchers.add(
        game_id, websocket, access.user_id, access.session_hash, access.expires_at
    )
    if not added:
        await websocket.close(code=CLOSE_TOO_MANY_CONNECTIONS)
        return
    try:
        # The sign-in was checked a moment ago, before this connection was listed. If the
        # player logged out in between, the log-out found nothing to close, so look once
        # more now that the connection is listed. (A log-out from here on closes it itself.)
        if await run_in_threadpool(_sign_in_has_ended, token):
            await websocket.close(code=CLOSE_NOT_AUTHENTICATED)
            return
        # Nothing the page sends is used. Waiting here is how the server finds out
        # that the page has gone.
        while True:
            # receive() accepts any kind of message, text or binary, and reports the
            # page going away as a message of its own
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        # runs however the wait above ends, so a gone connection is never left listed
        watchers.remove(game_id, websocket)
