"""app/live.py: the list of connections watching each game, and notifying them."""

import asyncio
from uuid import uuid4

from app.live import GAME_UPDATED, GameWatchers

GAME = uuid4()
OTHER_GAME = uuid4()


class FakeSocket:
    """Stands in for a WebSocket: remembers what it was sent."""

    def __init__(self, broken: bool = False):
        self.broken = broken
        self.sent = []
        self.was_sent_something = asyncio.Event()

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
        watchers.add(GAME, first)
        watchers.add(GAME, second)

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
        watchers.add(GAME, watching)
        watchers.add(OTHER_GAME, elsewhere)

        await notify_from_another_thread(watchers, GAME)
        await received(watching)

        assert elsewhere.sent == []

    asyncio.run(scenario())


def test_removed_connection_is_no_longer_notified():
    async def scenario():
        watchers = GameWatchers()
        stays, leaves = FakeSocket(), FakeSocket()
        watchers.add(GAME, stays)
        watchers.add(GAME, leaves)

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
        watchers.add(GAME, broken)
        watchers.add(GAME, working)

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
        watchers.add(GAME, socket)
        assert watchers.count(GAME) == 1

        watchers.remove(GAME, socket)
        watchers.remove(GAME, socket)  # removing twice is harmless

        assert watchers.count(GAME) == 0

    asyncio.run(scenario())


def test_the_notice_carries_no_game_data():
    # the page fetches the game through the API, where access is checked
    assert GAME_UPDATED == {"type": "game_updated"}
