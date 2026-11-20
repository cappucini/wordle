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

# asyncio: Python's way of running many waiting tasks (here, open connections) on one thread
import asyncio
# threading: for the lock that stops two threads changing the watchers at the same moment
import threading
# dataclass: writes a class's __init__ for it from the list of its fields
from dataclasses import dataclass
# datetime and timezone: for comparing a sign-in's expiry time with the current time
from datetime import datetime, timezone
# UUID: the type of a game's id and a user's id
from uuid import UUID

# WebSocket: FastAPI's object for one open two-way connection to a page
from fastapi import WebSocket

# how many live connections one player may hold open at once (10)
from app.domain.rules import MAX_LIVE_CONNECTIONS_PER_USER

# the one message this file ever sends: "the game changed, fetch it again"
GAME_UPDATED = {"type": "game_updated"}

# WebSocket close codes the page understands (see frontend/src/api.js)
# 4401 means "your sign-in is no longer valid"; the number echoes HTTP's 401
CLOSE_NOT_AUTHENTICATED = 4401


@dataclass(eq=False)  # compared by identity: each open connection is its own entry
class _Watcher:
    """One open WebSocket, with what is needed to send to it and to know when to close it."""

    # the connection itself, used to send a message or to close it
    websocket: WebSocket
    # the event loop the connection belongs to; notices are handed to it from other threads
    loop: asyncio.AbstractEventLoop
    # the player on the other end, used to count how many connections they hold
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
        # keep the limit on the object, so a test can make one with a smaller limit
        self.max_per_user = max_per_user
        # game id -> the open connections watching it
        self._watchers: dict[UUID, list[_Watcher]] = {}
        # routes run on several threads, so every change to the dict above takes this lock
        self._lock = threading.Lock()

    def now(self) -> datetime:
        """The current time. A method so tests can move it forward."""
        # the time in UTC, to match the expiry times stored with each sign-in
        return datetime.now(timezone.utc)

    def add(
        self,
        # the game the page has open
        game_id: UUID,
        # the page's connection
        websocket: WebSocket,
        # the signed-in player who opened it
        user_id: UUID,
        # which sign-in it was opened with
        session_hash: str,
        # when that sign-in ends
        expires_at: datetime,
    ) -> bool:
        """Start sending this connection the game's notices. Call from the connection's own task.

        Returns False, and adds nothing, if this user already holds as many connections
        as one user may.
        """
        # Bundle the connection with its details. get_running_loop() is the event loop this
        # connection is being served on; it is kept so notices can be sent back through it.
        watcher = _Watcher(
            websocket, asyncio.get_running_loop(), user_id, session_hash, expires_at
        )
        # take the lock; it is released on leaving the `with` block, including on return
        with self._lock:
            # how many connections this user already has, counted across every game
            held = sum(
                # count one...
                1
                # ...for each game's list of watchers...
                for watching in self._watchers.values()
                # ...for each watcher in that list...
                for other in watching
                # ...that belongs to this user
                if other.user_id == user_id
            )
            # at the limit already: refuse, and the caller closes the connection
            if held >= self.max_per_user:
                return False
            # setdefault returns the game's list, first storing an empty one if it had none
            self._watchers.setdefault(game_id, []).append(watcher)
            # added: the connection will now be told when this game changes
            return True

    def remove(self, game_id: UUID, websocket: WebSocket) -> None:
        """Stop sending this connection the game's notices. Called when its page has gone."""
        # take the lock while the list is changed
        with self._lock:
            # the lambda is the test _drop applies to each watcher; `is` matches this
            # exact connection object, not one that merely looks equal
            self._drop(game_id, lambda watcher: watcher.websocket is websocket)

    def count(self, game_id: UUID) -> int:
        """How many connections are watching this game."""
        # take the lock so the list cannot change while it is being counted
        with self._lock:
            # the () default stands in for "no watchers", so an unknown game counts as 0
            return len(self._watchers.get(game_id, ()))

    def notify(self, game_id: UUID) -> None:
        """Tell every page watching this game that it changed.

        Safe to call from any thread, and returns straight away: each message is handed to
        the connection's event loop to send, so a slow connection never holds up the request
        that made the change. A connection whose sign-in has expired is closed instead.
        """
        # read the clock once, so every watcher is judged against the same moment
        now = self.now()
        # take the lock only for the bookkeeping, not for the sending
        with self._lock:
            # copy the list while holding the lock; the sending below happens outside it
            watching = list(self._watchers.get(game_id, ()))
            # the watchers whose sign-in has run out
            expired = [watcher for watcher in watching if watcher.expires_at <= now]
            # forget those, so they are not sent anything in future
            self._drop(game_id, lambda watcher: watcher.expires_at <= now)
        # the lock is released; now deal with each connection that was watching
        for watcher in watching:
            if watcher in expired:
                # sign-in over: close the connection, telling the page why
                _run(watcher, _close(watcher.websocket, CLOSE_NOT_AUTHENTICATED))
            else:
                # still signed in: send the "game updated" message
                _run(watcher, _send_update(watcher.websocket))

    def close_session(self, session_hash: str) -> None:
        """Close every connection opened with this sign-in. Called when it is logged out."""
        # the connections to close, gathered first and closed after the lock is released
        closing = []
        with self._lock:
            # go through every game that has watchers.
            # list(...) copies the keys first, because _drop may delete a game from the dict
            for game_id in list(self._watchers):
                # add this game's watchers that were opened with the sign-in being ended
                closing += [
                    watcher
                    for watcher in self._watchers[game_id]
                    if watcher.session_hash == session_hash
                ]
                # and forget them, so they are no longer sent notices
                self._drop(game_id, lambda watcher: watcher.session_hash == session_hash)
        # close each one, telling its page the sign-in is no longer valid
        for watcher in closing:
            _run(watcher, _close(watcher.websocket, CLOSE_NOT_AUTHENTICATED))

    def extend_session(self, session_hash: str, expires_at: datetime) -> None:
        """A sign-in was extended: its open connections now last until the new time too."""
        with self._lock:
            # look at every watcher of every game
            for watching in self._watchers.values():
                for watcher in watching:
                    # one opened with this sign-in: give it the new, later end time
                    if watcher.session_hash == session_hash:
                        watcher.expires_at = expires_at

    def _drop(self, game_id: UUID, should_drop) -> None:
        """Removes the matching connections from a game. The caller holds the lock."""
        # should_drop is a function: given a watcher, it answers "remove this one?"
        # build a new list of the watchers to keep
        remaining = [
            watcher
            for watcher in self._watchers.get(game_id, ())
            if not should_drop(watcher)
        ]
        if remaining:
            # some are left: store the shorter list
            self._watchers[game_id] = remaining
        else:
            # nobody is left: remove the game's entry, so the dict does not fill up with
            # empty lists. The None default means "no error if it was already gone".
            self._watchers.pop(game_id, None)


def _run(watcher: _Watcher, coroutine) -> None:
    """Hands a coroutine to the connection's own event loop, from whatever thread this is."""
    # a coroutine is an async function that has been called but has not run yet
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
        # send the message as JSON; `await` waits for it without blocking other connections
        await websocket.send_json(GAME_UPDATED)
    except Exception:
        # The connection is closing or already gone. Its own handler removes it from the
        # watchers; there is nothing to do here, and one dead connection must not stop
        # the notice reaching the others.
        pass


async def _close(websocket: WebSocket, code: int) -> None:
    """Closes a connection with the given code. One that is already closed is ignored."""
    try:
        # close it; the page receives the code and uses it to decide what to do next
        await websocket.close(code=code)
    except Exception:
        pass  # already closed


# the one set of watchers for this server process
# (routes import this object and call watchers.notify, watchers.add and so on)
watchers = GameWatchers()
