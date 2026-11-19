"""The HTTP routes for games: list, create, open, join, read guesses and submit a guess.
Each one checks the request, calls app/game_service.py, and shapes the response.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import game_service
from app.api.v1.auth import get_current_user, require_csrf
from app.api.v1.pagination import decode_cursor, encode_cursor
from app.api.v1.schemas import (
    CreateGameRequest,
    CreateGuessRequest,
    GameListResponse,
    GameResponse,
    GuessCreatedResponse,
    GuessResponse,
)
from app.db import UserRow, get_session
from app.live import watchers

router = APIRouter(prefix="/api/v1/games", tags=["games"])

# Every route here needs a signed-in user: Depends(get_current_user) reads the session cookie
# and returns the user, or stops the request with a 401.
# Routes that change something (POST) also require the CSRF token: Depends(require_csrf).
# Routes that change a game also tell the pages watching it: watchers.notify (see app/live.py).


# response_model: FastAPI checks what the route returns against this schema, and sends
# only the fields the schema lists.
@router.get("", response_model=GameListResponse)
def read_games(
    # Query(...) reads ?limit= and ?cursor= from the URL. ge and le are "at least" and
    # "at most": a limit outside 1 to 100 is refused with a 422 before the route runs.
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """The signed-in user's games, newest first, one page at a time.

    The first request has no cursor; each response carries next_cursor, which the client
    sends back as ?cursor=. A cursor that cannot be read raises InvalidCursor.
    """
    after = decode_cursor(cursor) if cursor is not None else None
    games, has_more = game_service.list_games(session, user, limit=limit, after=after)

    next_cursor = None
    if has_more:
        # the next page starts after the last game on this one
        last_game = games[-1]
        next_cursor = encode_cursor(last_game.created_at, last_game.id)

    return GameListResponse(
        items=[GameResponse.from_row(game) for game in games],
        next_cursor=next_cursor,
    )


@router.post(
    "",
    status_code=201,
    response_model=GameResponse,
    # a dependency listed here is run for its check alone; the route does not need
    # its result, so it is not one of the parameters below
    dependencies=[Depends(require_csrf)],
)
def create_game(
    # a parameter typed as a pydantic model is read from the JSON body and validated
    body: CreateGameRequest,
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Starts a new game of the requested word length. The signed-in user is its first player."""
    game = game_service.create_game(session, user, body.word_length)
    return GameResponse.from_row(game)


@router.get("/{game_id}", response_model=GameResponse)
def get_game(
    game_id: UUID,
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Returns one game. Raises GameNotFound, or NotAPlayer if the user is not in it."""
    return GameResponse.from_row(game_service.get_game(session, user, game_id))


# Join a game as a player. Opening a shared game link calls this. It is safe to call
# more than once: joining a game you are already in simply returns the game.
@router.post(
    "/{game_id}/players",
    response_model=GameResponse,
    dependencies=[Depends(require_csrf)],
)
def join_game(
    game_id: UUID,
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Adds the signed-in user to the game's players and returns the game.

    Raises GameFull if there is no room, and GameOver if the game has already finished.
    """
    game, newly_joined = game_service.join_game(session, user, game_id)
    if newly_joined:
        # the players already in the game see the newcomer appear
        watchers.notify(game_id)
    return GameResponse.from_row(game)


@router.get("/{game_id}/guesses", response_model=list[GuessResponse])
def read_guesses(
    game_id: UUID,
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Returns the game's guesses in order, each with its letters scored."""
    game = game_service.get_game(session, user, game_id)
    return [GuessResponse.from_row(guess, game.answer) for guess in game.guesses]


@router.post(
    "/{game_id}/guesses",
    status_code=201,
    response_model=GuessCreatedResponse,
    dependencies=[Depends(require_csrf)],
)
def submit_guess(
    game_id: UUID,
    body: CreateGuessRequest,
    user: UserRow = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Saves a guess and returns it scored, along with the game's new status.

    Raises InvalidGuess for a word that is not accepted, and GameOver once the game
    has finished.
    """
    guess, game = game_service.submit_guess(
        session, user, game_id, body.word_guessed
    )
    # the guess is saved; tell every page that has this game open
    watchers.notify(game_id)
    return GuessCreatedResponse.from_rows(guess, game)
