"""Guessing: POST /games/{id}/guesses and GET /games/{id}/guesses.

The answer to every 5-letter game is "crane" (see tests/words/).
"""

from uuid import uuid4

import pytest

from tests.support import ANSWERS, NOT_A_WORD, WRONG, WRONG_5

GAME_OVER = {"code": "GAME_OVER", "detail": "This game is already over"}


# ---------- a valid guess ----------


def test_valid_guess_is_scored_letter_by_letter(player):
    game = player.create_game()

    response = player.guess(game["id"], "react")

    assert response.status_code == 201
    assert response.json() == {
        "number": 1,
        "word": "react",
        # r, e and c are in "crane" but elsewhere; a is in place; t is not in it
        "results": ["present", "present", "correct", "present", "absent"],
        "guessed_by": player.username,
        "game_status": "in_progress",
        "guesses_remaining": 5,
        "answer": None,
    }


@pytest.mark.parametrize("typed", ["REACT", "ReAcT", "  react  "])
def test_guess_is_trimmed_and_lowercased(player, typed):
    game = player.create_game()

    response = player.guess(game["id"], typed)

    assert response.status_code == 201
    assert response.json()["word"] == "react"


def test_guesses_are_saved_on_the_game_in_order(player):
    game = player.create_game()
    player.guess(game["id"], "slate")
    player.guess(game["id"], "react")

    game = player.game(game["id"])

    assert [(guess["number"], guess["word"]) for guess in game["guesses"]] == [
        (1, "slate"),
        (2, "react"),
    ]
    assert game["guesses_remaining"] == 4
    assert game["status"] == "in_progress"


def test_guesses_list_matches_the_game(player):
    game = player.create_game()
    player.guess(game["id"], "slate")
    player.guess(game["id"], "react")

    response = player.get(f"/games/{game['id']}/guesses")

    assert response.status_code == 200
    assert response.json() == player.game(game["id"])["guesses"]
    assert response.json()[0] == {
        "number": 1,
        "word": "slate",
        "results": ["absent", "absent", "correct", "absent", "correct"],
        "guessed_by": player.username,
    }


# ---------- an invalid guess ----------


@pytest.mark.parametrize(
    "word",
    [
        pytest.param("cran", id="shorter than any game allows"),
        pytest.param("absolutes", id="longer than any game allows"),
        pytest.param("cran3", id="digit"),
        pytest.param("cra ne", id="space inside"),
        pytest.param("", id="empty"),
        pytest.param(None, id="null"),
    ],
)
def test_guess_that_could_never_be_a_word_is_an_invalid_request(player, word):
    game = player.create_game()

    response = player.guess(game["id"], word)

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["detail"].startswith("word_guessed: ")


@pytest.mark.parametrize(
    "game_length, word",
    [
        pytest.param(6, "crane", id="too short for a 6-letter game"),
        pytest.param(5, "planet", id="too long for a 5-letter game"),
        pytest.param(8, "kitchen", id="one letter short of an 8-letter game"),
    ],
)
def test_guess_of_the_wrong_length_for_this_game_is_an_invalid_guess(player, game_length, word):
    game = player.create_game(game_length)

    response = player.guess(game["id"], word)

    assert response.status_code == 422
    assert response.json() == {
        "code": "INVALID_GUESS",
        "detail": f"Guess must be {game_length} letters",
    }


def test_guess_that_is_not_in_the_word_list_is_an_invalid_guess(player):
    game = player.create_game()

    response = player.guess(game["id"], NOT_A_WORD)

    assert response.status_code == 422
    assert response.json() == {
        "code": "INVALID_GUESS",
        "detail": "'zzzzz' is not in the word list",
    }


def test_invalid_guesses_do_not_use_up_a_turn(player):
    game = player.create_game()

    player.guess(game["id"], NOT_A_WORD)
    player.guess(game["id"], "planet")
    player.guess(game["id"], "cran")

    game = player.game(game["id"])
    assert game["guesses"] == []
    assert game["guesses_remaining"] == 6
    assert game["status"] == "in_progress"


def test_guess_in_a_game_that_does_not_exist(player):
    game_id = str(uuid4())

    response = player.guess(game_id, "crane")

    assert response.status_code == 404
    assert response.json() == {"code": "GAME_NOT_FOUND", "detail": f"Game {game_id} not found"}


def test_guess_needs_the_word_guessed_field(player):
    game = player.create_game()

    response = player.post(f"/games/{game['id']}/guesses", json={"word": "crane"})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


# ---------- winning ----------


def test_guessing_the_answer_wins_and_reveals_it(player):
    game = player.create_game()

    response = player.guess(game["id"], "crane")

    assert response.status_code == 201
    assert response.json() == {
        "number": 1,
        "word": "crane",
        "results": ["correct"] * 5,
        "guessed_by": player.username,
        "game_status": "won",
        "guesses_remaining": 5,
        "answer": "crane",
    }
    game = player.game(game["id"])
    assert game["status"] == "won"
    assert game["answer"] == "crane"


@pytest.mark.parametrize("word_length", [5, 6, 7, 8])
def test_every_word_length_can_be_won(player, word_length):
    game = player.create_game(word_length)

    response = player.guess(game["id"], ANSWERS[word_length])

    assert response.json()["game_status"] == "won"
    assert response.json()["results"] == ["correct"] * word_length


def test_guessing_the_answer_on_the_last_turn_is_a_win(player):
    game = player.create_game()
    for word in WRONG_5[:5]:
        assert player.guess(game["id"], word).json()["game_status"] == "in_progress"

    response = player.guess(game["id"], "crane")

    assert response.json()["number"] == 6
    assert response.json()["game_status"] == "won"
    assert response.json()["guesses_remaining"] == 0


# ---------- losing ----------


def test_running_out_of_guesses_loses_and_reveals_the_answer(player):
    game = player.create_game()

    responses = [player.guess(game["id"], word) for word in WRONG_5]

    # the answer stays hidden for every guess before the last
    for response in responses[:-1]:
        assert response.status_code == 201
        assert response.json()["game_status"] == "in_progress"
        assert response.json()["answer"] is None
        assert "crane" not in response.text

    last = responses[-1].json()
    assert last["number"] == 6
    assert last["game_status"] == "lost"
    assert last["guesses_remaining"] == 0
    assert last["answer"] == "crane"

    game = player.game(game["id"])
    assert game["status"] == "lost"
    assert game["answer"] == "crane"
    assert len(game["guesses"]) == 6


@pytest.mark.parametrize("word_length", [6, 7, 8])
def test_longer_games_are_lost_after_one_more_guess_than_letters(player, word_length):
    game = player.create_game(word_length)

    statuses = [
        player.guess(game["id"], WRONG[word_length]).json()["game_status"]
        for _ in range(word_length + 1)
    ]

    assert statuses == ["in_progress"] * word_length + ["lost"]


# ---------- after the game is over ----------


def test_guess_after_winning_is_refused(player):
    game = player.create_game()
    player.guess(game["id"], "crane")

    response = player.guess(game["id"], "slate")

    assert response.status_code == 409
    assert response.json() == GAME_OVER
    assert len(player.game(game["id"])["guesses"]) == 1


def test_guess_after_losing_is_refused(player):
    game = player.create_game()
    for word in WRONG_5:
        player.guess(game["id"], word)

    response = player.guess(game["id"], "crane")

    assert response.status_code == 409
    assert response.json() == GAME_OVER
    assert player.game(game["id"])["status"] == "lost"
