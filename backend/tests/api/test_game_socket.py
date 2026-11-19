"""Live updates: the WebSocket at /games/{id}/ws, and which changes are announced on it.

Who may connect is tested in tests/security/test_game_socket_security.py.
"""

import pytest

from tests.support import NOT_A_WORD

GAME_UPDATED = {"type": "game_updated"}


@pytest.fixture
def notices(monkeypatch):
    """Records which games were announced as changed, instead of sending anything.

    For checking that something was *not* announced: with a real socket that would mean
    waiting for a message that never comes.
    """
    from app.live import watchers

    announced = []
    monkeypatch.setattr(watchers, "notify", lambda game_id: announced.append(str(game_id)))
    return announced


# ---------- what a watching page receives ----------


def test_another_players_guess_is_announced_to_a_watching_page(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    with player.watch(game["id"]) as socket:
        other_player.guess(game["id"], "slate")

        assert socket.receive_json() == GAME_UPDATED

    # the notice says only that something changed; the page then reads the game as usual
    assert [guess["word"] for guess in player.game(game["id"])["guesses"]] == ["slate"]


def test_a_player_joining_is_announced_to_a_watching_page(player, other_player):
    game = player.create_game()

    with player.watch(game["id"]) as socket:
        other_player.join(game["id"])

        assert socket.receive_json() == GAME_UPDATED


def test_every_watching_page_is_told(make_player):
    owner, second, third = make_player(), make_player(), make_player()
    game = owner.create_game()
    second.join(game["id"])
    third.join(game["id"])

    with owner.watch(game["id"]) as owners_page, second.watch(game["id"]) as seconds_page:
        third.guess(game["id"], "slate")

        assert owners_page.receive_json() == GAME_UPDATED
        assert seconds_page.receive_json() == GAME_UPDATED


def test_one_notice_per_guess_in_order(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    with player.watch(game["id"]) as socket:
        other_player.guess(game["id"], "slate")
        other_player.guess(game["id"], "react")
        other_player.guess(game["id"], "crane")  # wins the game

        assert [socket.receive_json() for _ in range(3)] == [GAME_UPDATED] * 3

    assert player.game(game["id"])["status"] == "won"


def test_page_is_forgotten_when_it_disconnects(player, other_player):
    from uuid import UUID

    from app.live import watchers

    game = player.create_game()
    other_player.join(game["id"])

    with player.watch(game["id"]):
        assert watchers.count(UUID(game["id"])) == 1

    assert watchers.count(UUID(game["id"])) == 0
    # and a guess afterwards is handled normally with nobody watching
    assert other_player.guess(game["id"], "slate").status_code == 201


# ---------- which changes are announced ----------


def test_a_saved_guess_is_announced_for_its_game(player, notices):
    game = player.create_game()

    player.guess(game["id"], "slate")

    assert notices == [game["id"]]


@pytest.mark.parametrize("word", [NOT_A_WORD, "planet", "cran"])
def test_a_refused_guess_is_not_announced(player, notices, word):
    game = player.create_game()

    player.guess(game["id"], word)

    assert notices == []


def test_a_guess_after_the_game_is_over_is_not_announced(player, notices):
    game = player.create_game()
    player.guess(game["id"], "crane")
    notices.clear()

    player.guess(game["id"], "slate")

    assert notices == []


def test_a_guess_by_someone_outside_the_game_is_not_announced(player, other_player, notices):
    game = player.create_game()

    other_player.guess(game["id"], "slate")

    assert notices == []


def test_a_new_player_is_announced_once(player, other_player, notices):
    game = player.create_game()

    other_player.join(game["id"])

    assert notices == [game["id"]]


def test_opening_a_game_you_are_already_in_is_not_announced(player, other_player, notices):
    # the frontend calls "join" every time a game is opened; that must not ping everyone
    game = player.create_game()
    other_player.join(game["id"])
    notices.clear()

    player.join(game["id"])
    other_player.join(game["id"])

    assert notices == []


def test_being_refused_from_a_full_game_is_not_announced(make_player, notices):
    owner, second, third, fourth = (make_player() for _ in range(4))
    game = owner.create_game()
    second.join(game["id"])
    third.join(game["id"])
    notices.clear()

    fourth.join(game["id"])

    assert notices == []


def test_creating_a_game_announces_nothing(player, notices):
    player.create_game()

    assert notices == []
