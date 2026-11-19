"""app/live.py: the list of connections watching each game, and notifying them."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.live import GAME_UPDATED, GameWatchers

ERICA = uuid4()
SAM = uuid4()
NEXT_WEEK = datetime.now(timezone.utc) + timedelta(days=7)
LAST_WEEK = datetime.now(timezone.utc) - timedelta(days=7)


def watch(watchers, game_id, socket, user_id=ERICA, session="session-1", expires_at=NEXT_WEEK):
    """Registers a connection the way the WebSocket route does."""
    return watchers.add(game_id, socket, user_id, session, expires_at)

GAME = uuid4()
OTHER_GAME = uuid4()


class FakeSocket:
    """Stands in for a WebSocket: remembers what it was sent."""

    def __init__(self, broken: bool = False):
        self.broken = broken
        self.sent = []
        self.closed_with = None
        self.was_sent_something = asyncio.Event()
        self.was_closed = asyncio.Event()

    async def close(self, code=1000):
        self.closed_with = code
        self.was_closed.set()

    async def send_json(self, message):
        if self.broken:
            raise RuntimeError("this connection has gone away")
        self.sent.append(message)
        self.was_sent_something.set()


async def notify_from_another_thread(watchers: GameWatchers, game_id) -> None:
    # routes run on worker threads, so this is how notify() is called in the real app
    await asyncio.to_thread(watchers.notify, game_id)


async def received(socket: FakeSocket) -> None:
    await asyncio.wait_for(socket.was_sent_something.wait(), timeout=5)


def test_notify_reaches_every_connection_watching_the_game():
    async def scenario():
        watchers = GameWatchers()
        first, second = FakeSocket(), FakeSocket()
        watch(watchers, GAME, first)
        watch(watchers, GAME, second)

        await notify_from_another_thread(watchers, GAME)
        await received(first)
        await received(second)

        assert first.sent == [GAME_UPDATED]
        assert second.sent == [GAME_UPDATED]

    asyncio.run(scenario())


def test_notify_does_not_reach_connections_watching_another_game():
    async def scenario():
        watchers = GameWatchers()
        watching, elsewhere = FakeSocket(), FakeSocket()
        watch(watchers, GAME, watching)
        watch(watchers, OTHER_GAME, elsewhere)

        await notify_from_another_thread(watchers, GAME)
        await received(watching)

        assert elsewhere.sent == []

    asyncio.run(scenario())


def test_removed_connection_is_no_longer_notified():
    async def scenario():
        watchers = GameWatchers()
        stays, leaves = FakeSocket(), FakeSocket()
        watch(watchers, GAME, stays)
        watch(watchers, GAME, leaves)

        watchers.remove(GAME, leaves)
        await notify_from_another_thread(watchers, GAME)
        await received(stays)

        assert leaves.sent == []
        assert watchers.count(GAME) == 1

    asyncio.run(scenario())


def test_one_broken_connection_does_not_stop_the_others_being_notified():
    async def scenario():
        watchers = GameWatchers()
        broken, working = FakeSocket(broken=True), FakeSocket()
        watch(watchers, GAME, broken)
        watch(watchers, GAME, working)

        await notify_from_another_thread(watchers, GAME)
        await received(working)

        assert working.sent == [GAME_UPDATED]

    asyncio.run(scenario())


def test_notify_with_nobody_watching_does_nothing():
    GameWatchers().notify(GAME)  # must not raise


def test_removing_the_last_connection_forgets_the_game():
    async def scenario():
        watchers = GameWatchers()
        socket = FakeSocket()
        watch(watchers, GAME, socket)
        assert watchers.count(GAME) == 1

        watchers.remove(GAME, socket)
        watchers.remove(GAME, socket)  # removing twice is harmless

        assert watchers.count(GAME) == 0

    asyncio.run(scenario())


def test_the_notice_carries_no_game_data():
    # the page fetches the game through the API, where access is checked
    assert GAME_UPDATED == {"type": "game_updated"}


async def closed(socket: FakeSocket) -> None:
    await asyncio.wait_for(socket.was_closed.wait(), timeout=5)


def test_a_connection_whose_session_has_expired_is_closed_instead_of_notified():
    async def scenario():
        watchers = GameWatchers()
        expired, current = FakeSocket(), FakeSocket()
        watch(watchers, GAME, expired, session="old", expires_at=LAST_WEEK)
        watch(watchers, GAME, current, session="new")

        await notify_from_another_thread(watchers, GAME)
        await received(current)
        await closed(expired)

        assert expired.sent == []
        assert expired.closed_with == 4401
        assert watchers.count(GAME) == 1

    asyncio.run(scenario())


def test_closing_a_session_closes_its_connections_on_every_game():
    async def scenario():
        watchers = GameWatchers()
        first, second, someone_else = FakeSocket(), FakeSocket(), FakeSocket()
        watch(watchers, GAME, first, session="logged-out")
        watch(watchers, OTHER_GAME, second, session="logged-out")
        watch(watchers, GAME, someone_else, user_id=SAM, session="still-here")

        await asyncio.to_thread(watchers.close_session, "logged-out")
        await closed(first)
        await closed(second)

        assert (first.closed_with, second.closed_with) == (4401, 4401)
        assert someone_else.closed_with is None
        assert watchers.count(GAME) == 1
        assert watchers.count(OTHER_GAME) == 0

    asyncio.run(scenario())


def test_one_user_can_only_hold_so_many_connections():
    async def scenario():
        watchers = GameWatchers(max_per_user=3)
        sockets = [FakeSocket() for _ in range(3)]
        for socket in sockets:
            assert watch(watchers, GAME, socket) is True

        assert watch(watchers, OTHER_GAME, FakeSocket()) is False  # a fourth, on any game
        assert watch(watchers, GAME, FakeSocket(), user_id=SAM) is True  # other users are unaffected

        watchers.remove(GAME, sockets[0])
        assert watch(watchers, OTHER_GAME, FakeSocket()) is True  # room again

    asyncio.run(scenario())
