"""Creating and reading a game: POST /games, GET /games/{id}, plus the small public routes."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from tests.support import ANSWERS, API

GAME_FIELDS = {
    "id",
    "word_length",
    "max_guesses",
    "guesses_remaining",
    "status",
    "guesses",
    "answer",
    "created_at",
    "owner_id",
    "players",
    "max_players",
}


# ---------- public routes ----------


def test_config_returns_the_rules(client):
    response = client.get(f"{API}/config")

    assert response.status_code == 200
    assert response.json() == {
        "min_word_length": 5,
        "max_word_length": 8,
        "default_word_length": 5,
        "extra_guesses": 1,
        "max_players_per_game": 3,
    }


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


# ---------- create ----------


def test_create_game_returns_a_new_empty_game(player):
    response = player.post("/games", json={"word_length": 5})

    assert response.status_code == 201
    game = response.json()
    assert set(game) == GAME_FIELDS
    UUID(game["id"])  # raises if it is not a UUID
    datetime.fromisoformat(game["created_at"])
    assert game["word_length"] == 5
    assert game["max_guesses"] == 6
    assert game["guesses_remaining"] == 6
    assert game["status"] == "in_progress"
    assert game["guesses"] == []
    assert game["owner_id"] == player.id
    assert game["players"] == [{"id": player.id, "username": player.username}]
    assert game["max_players"] == 3


def test_create_game_does_not_reveal_the_answer(player):
    response = player.post("/games", json={"word_length": 5})

    assert response.json()["answer"] is None
    assert ANSWERS[5] not in response.text


def test_create_game_without_a_length_uses_five_letters(player):
    response = player.post("/games", json={})

    assert response.status_code == 201
    assert response.json()["word_length"] == 5


@pytest.mark.parametrize("word_length", [5, 6, 7, 8])
def test_create_game_allows_one_more_guess_than_letters(player, word_length):
    game = player.post("/games", json={"word_length": word_length}).json()

    assert game["word_length"] == word_length
    assert game["max_guesses"] == word_length + 1
    assert game["guesses_remaining"] == word_length + 1


@pytest.mark.parametrize("word_length", [4, 9, 0, -5, "five", 5.5, None])
def test_create_game_with_a_length_outside_the_limits_is_refused(player, word_length):
    response = player.post("/games", json={"word_length": word_length})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["detail"].startswith("word_length: ")
    assert player.get("/games").json()["items"] == []


def test_create_game_does_not_let_the_client_choose_the_answer(player):
    response = player.post("/games", json={"word_length": 5, "answer": "slate"})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_each_new_game_is_a_separate_game(player):
    first = player.create_game()
    second = player.create_game()

    assert first["id"] != second["id"]


def test_create_game_when_no_answer_words_are_loaded(player, db):
    from app.db import WordRow

    # take the 5-letter answer out of play for this test only
    answer = db.query(WordRow).filter_by(text=ANSWERS[5]).one()
    answer.is_answer = False
    db.commit()
    try:
        response = player.post("/games", json={"word_length": 5})
    finally:
        answer.is_answer = True
        db.commit()

    assert response.status_code == 503
    assert response.json() == {
        "code": "NO_WORDS_AVAILABLE",
        "detail": "No 5-letter answer words are loaded",
    }


# ---------- read ----------


def test_get_game_returns_the_game(player):
    created = player.create_game(6)

    response = player.get(f"/games/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_game_in_progress_does_not_reveal_the_answer(player):
    game = player.create_game()
    player.guess(game["id"], "slate")

    response = player.get(f"/games/{game['id']}")

    assert response.json()["answer"] is None
    assert ANSWERS[5] not in response.text


def test_get_game_that_does_not_exist(player):
    game_id = str(uuid4())

    response = player.get(f"/games/{game_id}")

    assert response.status_code == 404
    assert response.json() == {
        "code": "GAME_NOT_FOUND",
        "detail": f"Game {game_id} not found",
    }


def test_get_game_with_an_id_that_is_not_a_uuid(player):
    response = player.get("/games/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["detail"].startswith("game_id: ")
