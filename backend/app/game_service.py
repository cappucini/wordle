"""The game logic behind the routes in app/api/v1/games.py: creating, listing, opening and
joining games, and submitting guesses. Knows nothing about HTTP; it works with the database
and raises the errors in app/domain/errors.py.
"""

# datetime: the type of a game's created_at time, used when paging through the games list
from datetime import datetime
# UUID: the type of a game's id
from uuid import UUID

# select builds a database query; tuple_ lets a query compare two columns together as a pair
from sqlalchemy import select, tuple_
# Session is the open connection to the database that every function here is given;
# selectinload tells a query to fetch related rows (guesses, players) up front
from sqlalchemy.orm import Session, selectinload

# the table classes this file reads and writes (see app/db.py)
from app.db import GamePlayerRow, GameRow, GuessRow, UserRow
# the errors this file can raise; main.py turns each into an HTTP error response
from app.domain.errors import (
    GameFull,  # the game already has its maximum number of players
    GameNotFound,  # no game has this id
    GameOver,  # the game has already been won or lost
    InvalidGuess,  # the guess is the wrong length or not a real word
    NotAPlayer,  # the user is not one of this game's players
)
# the rules of the game, kept as plain Python in one place
from app.domain.rules import (
    MAX_PLAYERS_PER_GAME,  # how many players one game may have (3)
    GameStatus,  # the three states of a game: in progress, won, lost
    max_guesses_for,  # works out how many guesses a word length allows
    next_status,  # works out whether a game is now won, lost or still going
)
# lookup asks the word lists two things: "give me a random answer" and "is this a real word?"
from app.words import lookup

# Every function takes the signed-in user. A game belongs to its players:
# a solo game has one, and a shared game has up to MAX_PLAYERS_PER_GAME.


def create_game(session: Session, user: UserRow, word_length: int) -> GameRow:
    """Starts a game with a random answer of this length, owned by the user.

    Raises NoWordsAvailable if no answer words of that length are loaded.
    """
    # build the new game row in memory; nothing is saved yet
    game = GameRow(
        # pick the secret word at random from the answer words of this length
        answer=lookup.random_answer(session, word_length),
        # remember the length the player chose
        word_length=word_length,
        # the number of guesses allowed: the word length plus one
        max_guesses=max_guesses_for(word_length),
        # the user who started the game owns it
        owner=user,
        players=[user],  # the creator is the first player
    )
    # tell the session about the new row, so it is included in the next save
    session.add(game)
    # save it to the database; this also writes the creator's row in game_players
    session.commit()
    # hand the saved game back to the route, which turns it into the response
    return game


def get_game(session: Session, user: UserRow, game_id: UUID) -> GameRow:
    """Returns the game, but only to one of its players.

    Raises GameNotFound if there is no such game, and NotAPlayer if the user is not in it.
    """
    # session.get looks a row up by its primary key, and returns None if there is none
    game = session.get(GameRow, game_id)
    # no game has this id: stop here with a "not found" error
    if game is None:
        raise GameNotFound(f"Game {game_id} not found")
    # stop with an error if the user is not one of this game's players
    _require_player(game, user)
    # the user is a player, so they may see the game
    return game


def list_games(
    # the open database session
    session: Session,
    # the signed-in user whose games are wanted
    user: UserRow,
    # how many games to return in one page
    limit: int = 20,
    # where the previous page ended, or None for the first page
    after: tuple[datetime, UUID] | None = None,
) -> tuple[list[GameRow], bool]:
    """One page of the games this user plays in, newest first.

    `after` is the (created_at, id) of the last game on the previous page; the page returned
    starts with the next game after it. Returns the games and whether more remain.
    """
    # Build the query step by step. Nothing is sent to the database until it is run below.
    query = (
        # start from the games table
        select(GameRow)
        # only games where this user has a row in game_players
        .join(GamePlayerRow, GamePlayerRow.game_id == GameRow.id)
        .where(GamePlayerRow.user_id == user.id)
        # load the listed games' guesses and players in a few queries, not one per game
        .options(
            # each game's guesses, and for each guess the user who made it
            selectinload(GameRow.guesses).selectinload(GuessRow.user),
            # each game's players
            selectinload(GameRow.players),
        )
        # newest first.
        # id breaks the tie when two games share a created_at, so the order is always the same
        .order_by(GameRow.created_at.desc(), GameRow.id.desc())
        # ask for one extra row: if it comes back, there is another page
        .limit(limit + 1)
    )
    # for any page after the first, skip everything up to where the last page ended
    if after is not None:
        # "older than the last game seen": compares (created_at, id) as a pair
        query = query.where(tuple_(GameRow.created_at, GameRow.id) < after)

    # run the query.
    # scalars() gives the GameRow objects themselves rather than one-item result rows
    games = list(session.scalars(query))
    # more rows came back than were asked for, so at least one more game exists
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
    # no game has this id: stop here with a "not found" error
    if game is None:
        raise GameNotFound(f"Game {game_id} not found")
    # already a player: nothing to change, so return the game and "not newly joined"
    if _is_player(game, user):
        return game, False
    # the game has been won or lost
    if game.status != GameStatus.in_progress.value:
        # A finished game takes no new players: joining it would only be a way to read
        # its answer. Its own players can still open it (they returned just above).
        raise GameOver("This game is already over")
    # the game already has as many players as one game may have
    if len(game.players) >= MAX_PLAYERS_PER_GAME:
        raise GameFull(f"This game already has {MAX_PLAYERS_PER_GAME} players")

    # all checks passed: add the user to the game's players
    game.players.append(user)
    # save the new player, which also releases the lock on the game row
    session.commit()
    # return the game and "newly joined", so the route can tell the other players' pages
    return game, True


def submit_guess(
    # the open database session, the signed-in user, the game's id and the word they guessed
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
    # no game has this id: stop here with a "not found" error
    if game is None:
        raise GameNotFound(f"Game {game_id} not found")
    # stop with an error if the user is not one of this game's players
    _require_player(game, user)
    # a game that has been won or lost takes no more guesses
    if game.status != GameStatus.in_progress.value:
        raise GameOver("This game is already over")

    # the word lists are all lower case, so compare in lower case
    word = word.lower()
    # the guess must have exactly as many letters as the game's words
    if len(word) != game.word_length:
        raise InvalidGuess(f"Guess must be {game.word_length} letters")
    # the guess must be a real word from the accepted list; a refused guess is not
    # saved, so it does not use up a turn
    if not lookup.is_valid(session, word):
        raise InvalidGuess(f"'{word}' is not in the word list")

    # Build the guess row. Its number is one more than the guesses made so far.
    # any player may take the next turn; the guesses are numbered across all players
    guess = GuessRow(number=len(game.guesses) + 1, word=word, user=user)
    # attach it to the game, so it is saved along with the game
    game.guesses.append(guess)
    # work out the game's status now that this guess is in
    game.status = next_status(
        # guesses used so far, guesses allowed, and whether this guess is the answer
        len(game.guesses), game.max_guesses, word == game.answer
    # .value turns the status into its text ("won", "lost", "in_progress") for the column
    ).value
    # save the guess and the new status together, which also releases the lock
    session.commit()
    # hand both back; the route scores the guess's letters when it builds the response
    return guess, game


def _is_player(game: GameRow, user: UserRow) -> bool:
    """True if the user is one of the game's players."""
    # any(...) is True as soon as one player's id matches the user's id
    return any(player.id == user.id for player in game.players)


def _require_player(game: GameRow, user: UserRow) -> None:
    """Raises NotAPlayer unless the user is one of the game's players."""
    # not in the game: refuse, so only its players can read or play it
    if not _is_player(game, user):
        raise NotAPlayer("You are not a player in this game")
