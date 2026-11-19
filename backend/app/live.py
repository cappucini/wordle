"""Tells the pages that have a game open when that game changes.

Each page showing a game in progress keeps a WebSocket open to the server (see
app/api/v1/game_socket.py). When a guess is made or a player joins, the route that handled it
calls `watchers.notify(game_id)`, and every page watching that game is sent one small message:

    {"type": "game_updated"}

The message carries no game data. The page reacts by fetching the game through the normal
GET /games/{id} route, so who may see what (and the answer staying hidden) is decided in
exactly one place, the same as before.

A connection does not outlive the sign-in it was opened with: it is closed when that session
is logged out (close_session), and when the session's expiry time has passed (checked each
time its game is announced). One player may hold MAX_LIVE_CONNECTIONS_PER_USER at once.

Limit: the list of watchers lives in this process's memory. That is right for one server
process, which is how the app runs. With several processes, a guess handled by one would not
reach pages connected to another; that would need a shared channel such as Postgres
LISTEN/NOTIFY or Redis.
"""

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import WebSocket

from app.domain.rules import MAX_LIVE_CONNECTIONS_PER_USER

GAME_UPDATED = {"type": "game_updated"}

# WebSocket close codes the page understands (see frontend/src/api.js)
CLOSE_NOT_AUTHENTICATED = 4401


@dataclass(eq=False)  # compared by identity: each open connection is its own entry
class _Watcher:
    """One open WebSocket, with what is needed to send to it and to know when to close it."""

    websocket: WebSocket
    # the event loop the connection belongs to; notices are handed to it from other threads
    loop: asyncio.AbstractEventLoop
    user_id: UUID
    # which sign-in opened it (the hash of the session token), and when that sign-in ends
    session_hash: str
    expires_at: datetime


class GameWatchers:
    """Remembers which open connections are watching which game, and sends them notices.

    Safe to call from several threads at once.
    """

    def __init__(self, max_per_user: int = MAX_LIVE_CONNECTIONS_PER_USER) -> None:
        """Starts with nobody watching. max_per_user is how many connections one user may hold."""
        self.max_per_user = max_per_user
        # game id -> the open connections watching it
        self._watchers: dict[UUID, list[_Watcher]] = {}
        # routes run on several threads, so every change to the dict above takes this lock
        self._lock = threading.Lock()

    def now(self) -> datetime:
        """The current time. A method so tests can move it forward."""
        return datetime.now(timezone.utc)

    def add(
        self,
        game_id: UUID,
        websocket: WebSocket,
        user_id: UUID,
        session_hash: str,
        expires_at: datetime,
    ) -> bool:
        """Start sending this connection the game's notices. Call from the connection's own task.

        Returns False, and adds nothing, if this user already holds as many connections
        as one user may.
        """
        watcher = _Watcher(
            websocket, asyncio.get_running_loop(), user_id, session_hash, expires_at
        )
        with self._lock:
            # how many connections this user already has, counted across every game
            held = sum(
                1
                for watching in self._watchers.values()
                for other in watching
                if other.user_id == user_id
            )
            if held >= self.max_per_user:
                return False
            # setdefault returns the game's list, first storing an empty one if it had none
            self._watchers.setdefault(game_id, []).append(watcher)
            return True

    def remove(self, game_id: UUID, websocket: WebSocket) -> None:
        """Stop sending this connection the game's notices. Called when its page has gone."""
        with self._lock:
            # the lambda is the test _drop applies to each watcher; `is` matches this
            # exact connection object, not one that merely looks equal
            self._drop(game_id, lambda watcher: watcher.websocket is websocket)

    def count(self, game_id: UUID) -> int:
        """How many connections are watching this game."""
        with self._lock:
            # the () default stands in for "no watchers", so an unknown game counts as 0
            return len(self._watchers.get(game_id, ()))

    def notify(self, game_id: UUID) -> None:
        """Tell every page watching this game that it changed.

        Safe to call from any thread, and returns straight away: each message is handed to
        the connection's event loop to send, so a slow connection never holds up the request
        that made the change. A connection whose sign-in has expired is closed instead.
        """
        now = self.now()
        with self._lock:
            # copy the list while holding the lock; the sending below happens outside it
            watching = list(self._watchers.get(game_id, ()))
            expired = [watcher for watcher in watching if watcher.expires_at <= now]
            self._drop(game_id, lambda watcher: watcher.expires_at <= now)
        for watcher in watching:
            if watcher in expired:
                _run(watcher, _close(watcher.websocket, CLOSE_NOT_AUTHENTICATED))
            else:
                _run(watcher, _send_update(watcher.websocket))

    def close_session(self, session_hash: str) -> None:
        """Close every connection opened with this sign-in. Called when it is logged out."""
        closing = []
        with self._lock:
            # list(...) copies the keys first, because _drop may delete a game from the dict
            for game_id in list(self._watchers):
                closing += [
                    watcher
                    for watcher in self._watchers[game_id]
                    if watcher.session_hash == session_hash
                ]
                self._drop(game_id, lambda watcher: watcher.session_hash == session_hash)
        for watcher in closing:
            _run(watcher, _close(watcher.websocket, CLOSE_NOT_AUTHENTICATED))

    def extend_session(self, session_hash: str, expires_at: datetime) -> None:
        """A sign-in was extended: its open connections now last until the new time too."""
        with self._lock:
            for watching in self._watchers.values():
                for watcher in watching:
                    if watcher.session_hash == session_hash:
                        watcher.expires_at = expires_at

    def _drop(self, game_id: UUID, should_drop) -> None:
        """Removes the matching connections from a game. The caller holds the lock."""
        remaining = [
            watcher
            for watcher in self._watchers.get(game_id, ())
            if not should_drop(watcher)
        ]
        if remaining:
            self._watchers[game_id] = remaining
        else:
            self._watchers.pop(game_id, None)


def _run(watcher: _Watcher, coroutine) -> None:
    """Hands a coroutine to the connection's own event loop, from whatever thread this is."""
    if watcher.loop.is_closed():
        # the loop can no longer run anything; close() throws the coroutine away
        # cleanly, without Python warning that it was never awaited
        coroutine.close()
        return
    # Routes run on worker threads, where `await` is not available. This queues the
    # coroutine on the loop's own thread and returns at once, without waiting for it.
    asyncio.run_coroutine_threadsafe(coroutine, watcher.loop)


async def _send_update(websocket: WebSocket) -> None:
    """Sends the "game updated" message. A connection that has gone is ignored."""
    try:
        await websocket.send_json(GAME_UPDATED)
    except Exception:
        # The connection is closing or already gone. Its own handler removes it from the
        # watchers; there is nothing to do here, and one dead connection must not stop
        # the notice reaching the others.
        pass


async def _close(websocket: WebSocket, code: int) -> None:
    """Closes a connection with the given code. One that is already closed is ignored."""
    try:
        await websocket.close(code=code)
    except Exception:
        pass  # already closed


# the one set of watchers for this server process
watchers = GameWatchers()
