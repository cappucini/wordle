from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, selectinload

from app.db import GameRow, GuessRow
from app.domain.errors import GameNotFound, GameOver, InvalidGuess
from app.domain.rules import GameStatus, max_guesses_for, next_status
from app.words import lookup


def create_game(session: Session, word_length: int) -> GameRow:
    game = GameRow(
        answer=lookup.random_answer(session, word_length),
        word_length=word_length,
        max_guesses=max_guesses_for(word_length),
    )
    session.add(game)
    session.commit()
    return game


def get_game(session: Session, game_id: UUID) -> GameRow:
    game = session.get(GameRow, game_id)
    if game is None:
        raise GameNotFound(f"Game {game_id} not found")
    return game


def list_games(
    session: Session,
    limit: int = 20,
    after: tuple[datetime, UUID] | None = None,
) -> tuple[list[GameRow], bool]:
    """One page of games, newest first.

    `after` is the (created_at, id) of the last game on the previous page; the page returned
    starts with the next game after it. Returns the games and whether more remain.
    """
    query = (
        select(GameRow)
        # load every listed game's guesses in one extra query, not one query per game
        .options(selectinload(GameRow.guesses))
        # id breaks the tie when two games share a created_at, so the order is always the same
        .order_by(GameRow.created_at.desc(), GameRow.id.desc())
        # ask for one extra row: if it comes back, there is another page
        .limit(limit + 1)
    )
    if after is not None:
        # "older than the last game seen": compares (created_at, id) as a pair
        query = query.where(tuple_(GameRow.created_at, GameRow.id) < after)

    games = list(session.scalars(query))
    has_more = len(games) > limit
    return games[:limit], has_more


def submit_guess(
    session: Session, game_id: UUID, word: str
) -> tuple[GuessRow, GameRow]:
    # lock the game row so two guesses at the same moment are handled one at a time
    game = session.get(GameRow, game_id, with_for_update=True)
    if game is None:
        raise GameNotFound(f"Game {game_id} not found")
    if game.status != GameStatus.in_progress.value:
        raise GameOver("This game is already over")

    word = word.lower()
    if len(word) != game.word_length:
        raise InvalidGuess(f"Guess must be {game.word_length} letters")
    if not lookup.is_valid(session, word):
        raise InvalidGuess(f"'{word}' is not in the word list")

    guess = GuessRow(number=len(game.guesses) + 1, word=word)
    game.guesses.append(guess)
    game.status = next_status(
        len(game.guesses), game.max_guesses, word == game.answer
    ).value
    session.commit()
    return guess, game
