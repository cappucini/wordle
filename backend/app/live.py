"""Tells the pages that have a game open when that game changes.

Each page showing a game in progress keeps a WebSocket open to the server (see
app/api/v1/game_socket.py). When a guess is made or a player joins, the route that handled it
calls `watchers.notify(game_id)`, and every page watching that game is sent one small message:

    {"type": "game_updated"}

The message carries no game data. The page reacts by fetching the game through the normal
GET /games/{id} route, so who may see what (and the answer staying hidden) is decided in
exactly one place, the same as before.

Limit: the list of watchers lives in this process's memory. That is right for one server
process, which is how the app runs. With several processes, a guess handled by one would not
reach pages connected to another; that would need a shared channel such as Postgres
LISTEN/NOTIFY or Redis.
"""

import asyncio
import threading
from uuid import UUID

from fastapi import WebSocket

GAME_UPDATED = {"type": "game_updated"}


class GameWatchers:
    def __init__(self) -> None:
        # game id -> the open connections watching it. Each connection is kept with the
        # event loop it belongs to, because notify() is called from other threads.
        self._watchers: dict[UUID, set[tuple[WebSocket, asyncio.AbstractEventLoop]]] = {}
        # routes run on several threads, so every change to the dict above takes this lock
        self._lock = threading.Lock()

    def add(self, game_id: UUID, websocket: WebSocket) -> None:
        """Start sending this connection the game's notices. Call from the connection's own task."""
        entry = (websocket, asyncio.get_running_loop())
        with self._lock:
            self._watchers.setdefault(game_id, set()).add(entry)

    def remove(self, game_id: UUID, websocket: WebSocket) -> None:
        with self._lock:
            entries = self._watchers.get(game_id, set())
            for entry in [entry for entry in entries if entry[0] is websocket]:
                entries.discard(entry)
            if not entries:
                self._watchers.pop(game_id, None)

    def count(self, game_id: UUID) -> int:
        with self._lock:
            return len(self._watchers.get(game_id, ()))

    def notify(self, game_id: UUID) -> None:
        """Tell every page watching this game that it changed.

        Safe to call from any thread, and returns straight away: each message is handed to
        the connection's event loop to send, so a slow connection never holds up the request
        that made the change.
        """
        with self._lock:
            entries = list(self._watchers.get(game_id, ()))
        for websocket, loop in entries:
            if loop.is_closed():
                continue
            asyncio.run_coroutine_threadsafe(_send_update(websocket), loop)


async def _send_update(websocket: WebSocket) -> None:
    try:
        await websocket.send_json(GAME_UPDATED)
    except Exception:
        # The connection is closing or already gone. Its own handler removes it from the
        # watchers; there is nothing to do here, and one dead connection must not stop
        # the notice reaching the others.
        pass


# the one set of watchers for this server process
watchers = GameWatchers()
