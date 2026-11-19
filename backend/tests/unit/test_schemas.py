"""app/api/v1/schemas.py: where the limits in rules.py are enforced on incoming requests,
and where responses decide what to reveal. No database: rows are stood in for by plain objects.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.schemas import (
    CreateGameRequest,
    CreateGuessRequest,
    CredentialsRequest,
    GameResponse,
    GuessCreatedResponse,
    GuessResponse,
)

GOOD_PASSWORD = "correct horse"


# ---------- CreateGameRequest: word length ----------


def test_word_length_defaults_to_five():
    assert CreateGameRequest().word_length == 5


@pytest.mark.parametrize("word_length", [5, 6, 7, 8])
def test_word_length_within_limits_is_accepted(word_length):
    assert CreateGameRequest(word_length=word_length).word_length == word_length


@pytest.mark.parametrize("word_length", [-1, 0, 4, 9, 100])
def test_word_length_outside_limits_is_rejected(word_length):
    with pytest.raises(ValidationError):
        CreateGameRequest(word_length=word_length)


@pytest.mark.parametrize("word_length", [5.5, "five", None])
def test_word_length_that_is_not_a_whole_number_is_rejected(word_length):
    with pytest.raises(ValidationError):
        CreateGameRequest(word_length=word_length)


def test_create_game_rejects_unknown_fields():
    # in particular, a client must not be able to choose the answer
    with pytest.raises(ValidationError):
        CreateGameRequest(word_length=5, answer="crane")


# ---------- CredentialsRequest: username ----------


@pytest.mark.parametrize("username", ["abc", "a" * 20, "erica_2", "123"])
def test_username_within_limits_is_accepted(username):
    body = CredentialsRequest(username=username, password=GOOD_PASSWORD)
    assert body.username == username


@pytest.mark.parametrize(
    "username",
    [
        pytest.param("", id="empty"),
        pytest.param("ab", id="2 characters, one too few"),
        pytest.param("a" * 21, id="21 characters, one too many"),
        pytest.param("eri ca", id="space inside"),
        pytest.param("eri-ca", id="hyphen"),
        pytest.param("erica!", id="punctuation"),
        pytest.param("érica", id="accented letter"),
        pytest.param("  ab  ", id="too short once the spaces are trimmed"),
        pytest.param(None, id="null"),
        pytest.param(12345, id="number"),
    ],
)
def test_username_outside_limits_is_rejected(username):
    with pytest.raises(ValidationError):
        CredentialsRequest(username=username, password=GOOD_PASSWORD)


@pytest.mark.parametrize(
    "typed, stored",
    [("Erica", "erica"), ("ERICA", "erica"), ("  erica  ", "erica"), (" Erica_2 ", "erica_2")],
)
def test_username_is_trimmed_and_lowercased(typed, stored):
    assert CredentialsRequest(username=typed, password=GOOD_PASSWORD).username == stored


# ---------- CredentialsRequest: password ----------


@pytest.mark.parametrize("length", [8, 9, 127, 128])
def test_password_within_limits_is_accepted(length):
    body = CredentialsRequest(username="erica", password="p" * length)
    assert len(body.password) == length


@pytest.mark.parametrize("length", [0, 1, 7, 129, 1000])
def test_password_outside_limits_is_rejected(length):
    with pytest.raises(ValidationError):
        CredentialsRequest(username="erica", password="p" * length)


def test_password_is_kept_exactly_as_typed():
    # unlike the username: case and spaces are part of the password
    password = "  MiXeD Case  "
    assert CredentialsRequest(username="erica", password=password).password == password


def test_credentials_require_both_fields():
    with pytest.raises(ValidationError):
        CredentialsRequest(username="erica")
    with pytest.raises(ValidationError):
        CredentialsRequest(password=GOOD_PASSWORD)


def test_credentials_reject_unknown_fields():
    with pytest.raises(ValidationError):
        CredentialsRequest(username="erica", password=GOOD_PASSWORD, is_admin=True)


# ---------- CreateGuessRequest: the guessed word ----------


@pytest.mark.parametrize("word", ["crane", "planet", "kitchen", "absolute"])
def test_guess_within_limits_is_accepted(word):
    assert CreateGuessRequest(word_guessed=word).word_guessed == word


@pytest.mark.parametrize(
    "word",
    [
        pytest.param("", id="empty"),
        pytest.param("cran", id="4 letters, one too few"),
        pytest.param("absolutes", id="9 letters, one too many"),
        pytest.param("cran3", id="digit"),
        pytest.param("cra ne", id="space inside"),
        pytest.param("cra-ne", id="hyphen"),
        pytest.param("crané", id="accented letter"),
        pytest.param("     ", id="only spaces"),
        pytest.param(None, id="null"),
        pytest.param(12345, id="number"),
    ],
)
def test_guess_outside_limits_is_rejected(word):
    with pytest.raises(ValidationError):
        CreateGuessRequest(word_guessed=word)


@pytest.mark.parametrize(
    "typed, used", [("CRANE", "crane"), ("CrAnE", "crane"), ("  crane  ", "crane")]
)
def test_guess_is_trimmed_and_lowercased(typed, used):
    assert CreateGuessRequest(word_guessed=typed).word_guessed == used


def test_guess_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CreateGuessRequest(word_guessed="crane", number=1)


# ---------- responses: what a game reveals ----------

ERICA = SimpleNamespace(id=uuid4(), username="erica")
SAM = SimpleNamespace(id=uuid4(), username="sam")


def fake_guess(number, word, user=ERICA):
    return SimpleNamespace(number=number, word=word, user=user)


def fake_game(status="in_progress", guesses=(), players=(ERICA,), answer="crane"):
    return SimpleNamespace(
        id=uuid4(),
        owner_id=ERICA.id,
        players=list(players),
        answer=answer,
        word_length=len(answer),
        max_guesses=len(answer) + 1,
        status=status,
        guesses=list(guesses),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_game_in_progress_does_not_reveal_the_answer():
    game = fake_game(guesses=[fake_guess(1, "slate")])

    response = GameResponse.from_row(game)

    assert response.answer is None
    assert "crane" not in response.model_dump_json()


@pytest.mark.parametrize("status", ["won", "lost"])
def test_finished_game_reveals_the_answer(status):
    assert GameResponse.from_row(fake_game(status=status)).answer == "crane"


def test_game_response_counts_guesses_remaining():
    game = fake_game(guesses=[fake_guess(1, "slate"), fake_guess(2, "react")])

    response = GameResponse.from_row(game)

    assert response.max_guesses == 6
    assert response.guesses_remaining == 4


def test_game_response_lists_players_and_the_player_limit():
    response = GameResponse.from_row(fake_game(players=[ERICA, SAM]))

    assert [player.username for player in response.players] == ["erica", "sam"]
    assert response.max_players == 3
    assert response.owner_id == ERICA.id


def test_game_response_scores_each_guess_and_names_who_made_it():
    game = fake_game(guesses=[fake_guess(1, "react", user=SAM)], players=[ERICA, SAM])

    guess = GameResponse.from_row(game).guesses[0]

    assert guess.number == 1
    assert guess.word == "react"
    assert [result.value for result in guess.results] == [
        "present", "present", "correct", "present", "absent",
    ]
    assert guess.guessed_by == "sam"


def test_guess_response_copes_with_a_guess_that_has_no_user():
    # guesses.user_id is nullable in the database
    response = GuessResponse.from_row(fake_guess(1, "slate", user=None), "crane")

    assert response.guessed_by is None


def test_guess_created_response_hides_the_answer_while_the_game_continues():
    guess = fake_guess(1, "slate")
    game = fake_game(guesses=[guess])

    response = GuessCreatedResponse.from_rows(guess, game)

    assert response.game_status == "in_progress"
    assert response.guesses_remaining == 5
    assert response.answer is None


@pytest.mark.parametrize("status", ["won", "lost"])
def test_guess_created_response_reveals_the_answer_when_the_game_ends(status):
    guess = fake_guess(1, "crane" if status == "won" else "slate")
    game = fake_game(status=status, guesses=[guess])

    response = GuessCreatedResponse.from_rows(guess, game)

    assert response.game_status == status
    assert response.answer == "crane"
