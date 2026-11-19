"""app/domain/rules.py: the game's limits, and when a game is won or lost."""

import re

import pytest

from app.domain import rules
from app.domain.rules import GameStatus, LetterResult, max_guesses_for, next_status


def test_limits_have_not_changed_by_accident():
    # These numbers are the game's rules. A change here should be a decision, not a slip:
    # if you meant to change one, update this test in the same commit.
    assert rules.MIN_WORD_LENGTH == 5
    assert rules.MAX_WORD_LENGTH == 8
    assert rules.DEFAULT_WORD_LENGTH == 5
    assert rules.EXTRA_GUESSES == 1
    assert rules.MAX_PLAYERS_PER_GAME == 3
    assert rules.MIN_USERNAME_LENGTH == 3
    assert rules.MAX_USERNAME_LENGTH == 20
    assert rules.MIN_PASSWORD_LENGTH == 8
    assert rules.MAX_PASSWORD_LENGTH == 128
    assert rules.SESSION_DAYS == 7


def test_default_word_length_is_within_the_allowed_range():
    assert rules.MIN_WORD_LENGTH <= rules.DEFAULT_WORD_LENGTH <= rules.MAX_WORD_LENGTH


@pytest.mark.parametrize(
    "word_length, expected", [(5, 6), (6, 7), (7, 8), (8, 9)]
)
def test_a_game_allows_one_more_guess_than_the_word_has_letters(word_length, expected):
    assert max_guesses_for(word_length) == expected


@pytest.mark.parametrize(
    # each pytest.param gives the four arguments in this order; `id` names the case
    "guesses_used, max_guesses, guessed_correctly, expected",
    [
        pytest.param(1, 6, True, GameStatus.won, id="correct on the first guess"),
        pytest.param(3, 6, True, GameStatus.won, id="correct midway"),
        pytest.param(6, 6, True, GameStatus.won, id="correct on the last guess is a win, not a loss"),
        pytest.param(1, 6, False, GameStatus.in_progress, id="wrong with guesses left"),
        pytest.param(5, 6, False, GameStatus.in_progress, id="wrong with one guess left"),
        pytest.param(6, 6, False, GameStatus.lost, id="wrong on the last guess"),
        pytest.param(7, 6, False, GameStatus.lost, id="past the limit is still lost"),
        pytest.param(9, 9, False, GameStatus.lost, id="8-letter game, wrong on guess 9"),
        pytest.param(8, 9, False, GameStatus.in_progress, id="8-letter game, wrong on guess 8"),
    ],
)
def test_next_status(guesses_used, max_guesses, guessed_correctly, expected):
    assert next_status(guesses_used, max_guesses, guessed_correctly) == expected


def test_status_and_result_values_are_the_api_strings():
    # stored in the database and sent to the frontend; renaming one breaks both
    # looping over an Enum class gives its members in the order they are defined
    assert [status.value for status in GameStatus] == ["in_progress", "won", "lost"]
    assert [result.value for result in LetterResult] == ["correct", "present", "absent"]


@pytest.mark.parametrize("word", ["crane", "CRANE", "CrAnE", "a"])
def test_word_pattern_accepts_letters(word):
    assert re.fullmatch(rules.WORD_PATTERN, word)


@pytest.mark.parametrize(
    "word", ["", "cran3", "cra ne", "cra-ne", "crane!", "crané", " crane"]
)
def test_word_pattern_rejects_anything_else(word):
    assert not re.fullmatch(rules.WORD_PATTERN, word)


@pytest.mark.parametrize("username", ["erica", "erica_2", "123", "___", "a1_b2"])
def test_username_pattern_accepts_lowercase_digits_and_underscores(username):
    assert re.fullmatch(rules.USERNAME_PATTERN, username)


@pytest.mark.parametrize(
    "username", ["", "Erica", "eri ca", "eri-ca", "erica!", "erica@x.com", "érica"]
)
def test_username_pattern_rejects_anything_else(username):
    assert not re.fullmatch(rules.USERNAME_PATTERN, username)
