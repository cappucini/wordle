from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def list_games(session: Session) -> list[GameRow]:
    return list(session.scalars(select(GameRow).order_by(GameRow.created_at.desc())))


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
