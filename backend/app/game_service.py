"""The game logic behind the routes in app/api/v1/games.py: creating, listing, opening and
joining games, and submitting guesses. Knows nothing about HTTP; it works with the database
and raises the errors in app/domain/errors.py.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, selectinload

from app.db import GamePlayerRow, GameRow, GuessRow, UserRow
from app.domain.errors import (
    GameFull,
    GameNotFound,
    GameOver,
    InvalidGuess,
    NotAPlayer,
)
from app.domain.rules import (
    MAX_PLAYERS_PER_GAME,
    GameStatus,
    max_guesses_for,
    next_status,
)
from app.words import lookup

# Every function takes the signed-in user. A game belongs to its players:
# a solo game has one, and a shared game has up to MAX_PLAYERS_PER_GAME.


def create_game(session: Session, user: UserRow, word_length: int) -> GameRow:
    """Starts a game with a random answer of this length, owned by the user.

    Raises NoWordsAvailable if no answer words of that length are loaded.
    """
    game = GameRow(
        answer=lookup.random_answer(session, word_length),
        word_length=word_length,
        max_guesses=max_guesses_for(word_length),
        owner=user,
        players=[user],  # the creator is the first player
    )
    session.add(game)
    session.commit()
    return game


def get_game(session: Session, user: UserRow, game_id: UUID) -> GameRow:
    """Returns the game, but only to one of its players.

    Raises GameNotFound if there is no such game, and NotAPlayer if the user is not in it.
    """
    # session.get looks a row up by its primary key, and returns None if there is none
    game = session.get(GameRow, game_id)
    if game is None:
        raise GameNotFound(f"Game {game_id} not found")
    _require_player(game, user)
    return game


def list_games(
    session: Session,
    user: UserRow,
    limit: int = 20,
    after: tuple[datetime, UUID] | None = None,
) -> tuple[list[GameRow], bool]:
    """One page of the games this user plays in, newest first.

    `after` is the (created_at, id) of the last game on the previous page; the page returned
    starts with the next game after it. Returns the games and whether more remain.
    """
    query = (
        select(GameRow)
        # only games where this user has a row in game_players
        .join(GamePlayerRow, GamePlayerRow.game_id == GameRow.id)
        .where(GamePlayerRow.user_id == user.id)
        # load the listed games' guesses and players in a few queries, not one per game
        .options(
            selectinload(GameRow.guesses).selectinload(GuessRow.user),
            selectinload(GameRow.players),
        )
        # id breaks the tie when two games share a created_at, so the order is always the same
        .order_by(GameRow.created_at.desc(), GameRow.id.desc())
        # ask for one extra row: if it comes back, there is another page
        .limit(limit + 1)
    )
    if after is not None:
        # "older than the last game seen": compares (created_at, id) as a pair
        query = query.where(tuple_(GameRow.created_at, GameRow.id) < after)

    # scalars() gives the GameRow objects themselves rather than one-item result rows
    games = list(session.scalars(query))
    has_more = len(games) > limit
    # the extra row was only there to answer "is there more?"; it is not part of the page
    return games[:limit], has_more


def join_game(session: Session, user: UserRow, game_id: UUID) -> tuple[GameRow, bool]:
    """Add the user to a game's players. Joining a game you are already in changes nothing.

    Returns the game, and whether the user was added just now (False if already a player).
    """
    # Lock the game row, so two people joining at the same moment are handled one at a time
    # and the player limit can't be passed. with_for_update is SQL's SELECT ... FOR UPDATE:
    # a second request asking for the same row waits until this one commits.
    game = session.get(GameRow, game_id, with_for_update=True)
    if game is None:
        raise GameNotFound(f"Game {game_id} not found")
    if _is_player(game, user):
        return game, False
    if game.status != GameStatus.in_progress.value:
        # A finished game takes no new players: joining it would only be a way to read
        # its answer. Its own players can still open it (they returned just above).
        raise GameOver("This game is already over")
    if len(game.players) >= MAX_PLAYERS_PER_GAME:
        raise GameFull(f"This game already has {MAX_PLAYERS_PER_GAME} players")

    game.players.append(user)
    session.commit()
    return game, True


def submit_guess(
    session: Session, user: UserRow, game_id: UUID, word: str
) -> tuple[GuessRow, GameRow]:
    """Adds a guess to the game and works out whether the game is now won or lost.

    Returns the new guess and the updated game. Raises GameNotFound, NotAPlayer, GameOver
    if the game has finished, or InvalidGuess if the word is the wrong length or is not
    in the word list.
    """
    # lock the game row so two guesses at the same moment are handled one at a time;
    # with several players this is what keeps the shared guess limit from being passed
    game = session.get(GameRow, game_id, with_for_update=True)
    if game is None:
        raise GameNotFound(f"Game {game_id} not found")
    _require_player(game, user)
    if game.status != GameStatus.in_progress.value:
        raise GameOver("This game is already over")

    word = word.lower()
    if len(word) != game.word_length:
        raise InvalidGuess(f"Guess must be {game.word_length} letters")
    if not lookup.is_valid(session, word):
        raise InvalidGuess(f"'{word}' is not in the word list")

    # any player may take the next turn; the guesses are numbered across all players
    guess = GuessRow(number=len(game.guesses) + 1, word=word, user=user)
    game.guesses.append(guess)
    game.status = next_status(
        len(game.guesses), game.max_guesses, word == game.answer
    ).value
    session.commit()
    return guess, game


def _is_player(game: GameRow, user: UserRow) -> bool:
    """True if the user is one of the game's players."""
    return any(player.id == user.id for player in game.players)


def _require_player(game: GameRow, user: UserRow) -> None:
    """Raises NotAPlayer unless the user is one of the game's players."""
    if not _is_player(game, user):
        raise NotAPlayer("You are not a player in this game")
