"""Shared games: POST /games/{id}/players, the player limit, and who may guess."""

from uuid import uuid4

import pytest

from tests.support import API, WRONG_5

NOT_A_PLAYER = {"code": "NOT_A_PLAYER", "detail": "You are not a player in this game"}


def as_player(player) -> dict:
    """A player in the shape the API uses in a game's `players` list."""
    return {"id": player.id, "username": player.username}


# ---------- joining ----------


def test_joining_adds_you_to_the_games_players(player, other_player):
    game = player.create_game()

    response = other_player.join(game["id"])

    assert response.status_code == 200
    joined = response.json()
    assert joined["id"] == game["id"]
    # in the order they joined, the creator first
    assert joined["players"] == [as_player(player), as_player(other_player)]
    assert joined["owner_id"] == player.id
    assert joined["answer"] is None


def test_joining_twice_changes_nothing(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    response = other_player.join(game["id"])

    assert response.status_code == 200
    assert response.json()["players"] == [as_player(player), as_player(other_player)]


def test_owner_joining_their_own_game_changes_nothing(player):
    game = player.create_game()

    response = player.join(game["id"])

    assert response.status_code == 200
    assert response.json()["players"] == [as_player(player)]


def test_joined_game_shows_the_guesses_already_made(player, other_player):
    game = player.create_game()
    player.guess(game["id"], "slate")

    joined = other_player.join(game["id"]).json()

    assert [guess["word"] for guess in joined["guesses"]] == ["slate"]
    assert joined["guesses_remaining"] == 5


def test_join_a_game_that_does_not_exist(player):
    game_id = str(uuid4())

    response = player.join(game_id)

    assert response.status_code == 404
    assert response.json() == {"code": "GAME_NOT_FOUND", "detail": f"Game {game_id} not found"}


def test_join_with_an_id_that_is_not_a_uuid(player):
    response = player.join("not-a-uuid")

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_join_without_a_csrf_token_is_refused(player, other_player):
    game = player.create_game()

    response = other_player.client.post(f"{API}/games/{game['id']}/players")

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"
    assert player.game(game["id"])["players"] == [as_player(player)]


@pytest.mark.parametrize("ending", ["won", "lost"])
def test_joining_a_finished_game_is_refused(player, other_player, ending):
    game = player.create_game()
    # one right guess to win, or six wrong ones to lose
    for word in ["crane"] if ending == "won" else WRONG_5:
        player.guess(game["id"], word)

    response = other_player.join(game["id"])

    assert response.status_code == 409
    assert response.json() == {"code": "GAME_OVER", "detail": "This game is already over"}
    # they were not added, and learned nothing about how it went
    assert "crane" not in response.text
    assert len(player.game(game["id"])["players"]) == 1
    assert other_player.get(f"/games/{game['id']}").status_code == 403
    assert other_player.get("/games").json()["items"] == []


def test_players_already_in_a_finished_game_can_still_open_it(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])
    player.guess(game["id"], "crane")

    # the frontend opens a game by "joining" it, so this must keep working after it ends
    for someone in (player, other_player):
        response = someone.join(game["id"])
        assert response.status_code == 200
        assert response.json()["status"] == "won"
        assert response.json()["answer"] == "crane"


# ---------- the player limit ----------


def test_a_game_takes_three_players(make_player):
    owner, second, third = make_player(), make_player(), make_player()
    game = owner.create_game()

    assert second.join(game["id"]).status_code == 200
    response = third.join(game["id"])

    assert response.status_code == 200
    assert response.json()["players"] == [as_player(owner), as_player(second), as_player(third)]


def test_fourth_player_is_refused(make_player):
    # a generator that makes four players, unpacked into four names
    owner, second, third, fourth = (make_player() for _ in range(4))
    game = owner.create_game()
    second.join(game["id"])
    third.join(game["id"])

    response = fourth.join(game["id"])

    assert response.status_code == 409
    assert response.json() == {
        "code": "GAME_FULL",
        "detail": "This game already has 3 players",
    }
    assert len(owner.game(game["id"])["players"]) == 3
    # and being refused does not let them in by another route
    assert fourth.get(f"/games/{game['id']}").status_code == 403


def test_player_already_in_a_full_game_can_still_open_it(make_player):
    owner, second, third = make_player(), make_player(), make_player()
    game = owner.create_game()
    second.join(game["id"])
    third.join(game["id"])

    # the frontend calls "join" every time a game is opened, so this must keep working
    assert second.join(game["id"]).status_code == 200


# ---------- a game you have not joined ----------


def test_reading_a_game_you_have_not_joined_is_refused(player, other_player):
    game = player.create_game()

    response = other_player.get(f"/games/{game['id']}")

    assert response.status_code == 403
    assert response.json() == NOT_A_PLAYER


def test_reading_the_guesses_of_a_game_you_have_not_joined_is_refused(player, other_player):
    game = player.create_game()
    player.guess(game["id"], "slate")

    response = other_player.get(f"/games/{game['id']}/guesses")

    assert response.status_code == 403
    assert response.json() == NOT_A_PLAYER


def test_guessing_in_a_game_you_have_not_joined_is_refused(player, other_player):
    game = player.create_game()

    response = other_player.guess(game["id"], "crane")

    assert response.status_code == 403
    assert response.json() == NOT_A_PLAYER
    game = player.game(game["id"])
    assert game["guesses"] == []
    assert game["status"] == "in_progress"


# ---------- playing together ----------


def test_players_share_one_board(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    first = player.guess(game["id"], "slate").json()
    second = other_player.guess(game["id"], "react").json()

    # the guesses are numbered across both players
    assert (first["number"], first["guessed_by"]) == (1, player.username)
    assert (second["number"], second["guessed_by"]) == (2, other_player.username)
    # and each player sees the same game
    assert player.game(game["id"]) == other_player.game(game["id"])
    assert [
        (guess["word"], guess["guessed_by"]) for guess in player.game(game["id"])["guesses"]
    ] == [("slate", player.username), ("react", other_player.username)]


def test_players_share_the_guess_limit(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    # six guesses in total, three each, not six each
    for index, word in enumerate(WRONG_5):
        # take turns: the even positions go to the first player
        guesser = player if index % 2 == 0 else other_player
        last = guesser.guess(game["id"], word)

    assert last.json()["game_status"] == "lost"
    assert player.guess(game["id"], "crane").status_code == 409
    assert other_player.guess(game["id"], "crane").status_code == 409


def test_a_win_by_one_player_ends_the_game_for_everyone(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    other_player.guess(game["id"], "crane")

    game = player.game(game["id"])
    assert game["status"] == "won"
    assert game["answer"] == "crane"
    assert game["guesses"][0]["guessed_by"] == other_player.username
    assert player.guess(game["id"], "slate").status_code == 409
