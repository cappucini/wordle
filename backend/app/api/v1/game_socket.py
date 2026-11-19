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
"""

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
# the standard WebSocket code for "this request breaks the rules"
CLOSE_POLICY_VIOLATION = 1008


def _reason_to_refuse(token: str | None, game_id: UUID) -> int | None:
    """The close code to refuse this connection with, or None if it is allowed."""
    if token is None:
        return CLOSE_NOT_AUTHENTICATED
    # A database session just for this check. It is closed again before the connection
    # settles in, so an open WebSocket does not hold a database connection for its lifetime.
    with SessionLocal() as session:
        try:
            auth_session = user_service.get_auth_session(session, token)
            game_service.get_game(session, auth_session.user, game_id)
        except NotAuthenticated:
            return CLOSE_NOT_AUTHENTICATED
        except GameNotFound:
            return CLOSE_GAME_NOT_FOUND
        except NotAPlayer:
            return CLOSE_NOT_A_PLAYER
    return None


@router.websocket("/api/v1/games/{game_id}/ws")
async def watch_game(websocket: WebSocket, game_id: UUID):
    # A request from another website is turned away before the connection is even opened.
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=CLOSE_POLICY_VIOLATION)
        return

    token = websocket.cookies.get(SESSION_COOKIE)
    # the check talks to the database, which would block every other connection if run here
    close_code = await run_in_threadpool(_reason_to_refuse, token, game_id)

    # Open the connection first even when refusing: a browser can only read a close code
    # from a connection that was opened, and the page needs the code to know not to retry.
    await websocket.accept()
    if close_code is not None:
        await websocket.close(code=close_code)
        return

    watchers.add(game_id, websocket)
    try:
        # Nothing the page sends is used. Waiting here is how the server finds out
        # that the page has gone, which raises WebSocketDisconnect.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        watchers.remove(game_id, websocket)
