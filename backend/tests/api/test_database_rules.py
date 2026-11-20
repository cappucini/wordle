"""The rules the database enforces by itself: CHECK constraints, required columns and a
foreign key.

The API refuses all of these first, with a clear error (see the other files in this folder).
These tests go around the API and write rows directly, the way a bug or a new code path
might, and check that the database still says no.

Rules that depend on other rows (the player limit, the guess limit, no guesses on a finished
game) are not database rules: the code in app/game_service.py enforces those under a row
lock, and tests/concurrency/ checks that they hold.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def refused(db, row=None, statement=None, values=None) -> bool:
    """True if the database refuses to save the row, or to run the statement."""
    try:
        if row is not None:
            db.add(row)
            db.flush()
        else:
            db.execute(text(statement), values or {})
    except IntegrityError:
        db.rollback()
        return True
    db.rollback()
    return False


def new_guess(game, player, number=1, word="slate"):
    """A guess row for this game, not saved yet. `player` may be None, for no author."""
    from app.db import GuessRow

    return GuessRow(
        game_id=uuid.UUID(game["id"]),
        user_id=uuid.UUID(player.id) if player is not None else None,
        number=number,
        word=word,
    )


# ---- guesses ----


def test_database_accepts_a_guess_from_a_player(player, db):
    game = player.create_game()

    assert not refused(db, new_guess(game, player))


def test_database_refuses_a_guess_from_someone_who_is_not_a_player(player, other_player, db):
    game = player.create_game()

    assert refused(db, new_guess(game, other_player))


def test_database_refuses_a_guess_numbered_below_one(player, db):
    game = player.create_game()

    assert refused(db, new_guess(game, player, number=0))


# ---- required columns ----


def test_database_refuses_a_guess_with_no_author(player, db):
    game = player.create_game()

    assert refused(db, new_guess(game, None))


def test_database_refuses_a_game_with_no_owner(player, db):
    game = player.create_game()

    assert refused(
        db,
        statement="UPDATE games SET owner_id = NULL WHERE id = :id",
        values={"id": game["id"]},
    )


def test_database_refuses_a_sign_in_with_no_csrf_token(player, db):
    assert refused(db, statement="UPDATE auth_sessions SET csrf_token = NULL")


# ---- the game row (CHECK constraints) ----


@pytest.mark.parametrize(
    "change",
    [
        "status = 'paused'",
        "word_length = 4, max_guesses = 5, answer = 'word'",
        "word_length = 9, max_guesses = 10",
        "max_guesses = 99",
        "answer = 'cat'",
    ],
)
def test_database_refuses_a_game_row_that_breaks_a_rule(player, db, change):
    game = player.create_game()

    assert refused(
        db, statement=f"UPDATE games SET {change} WHERE id = :id", values={"id": game["id"]}
    )
