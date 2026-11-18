# # path to get all games

# # path to get specific game
# # games/:id

# from fastapi import APIRouter, HTTPException
# from uuid import UUID
# from app.api.v1.schemas import CreateGameRequest, CreateGuessRequest, GuessCreatedResponse
# # create a countainer for routes
# router = APIRouter(prefix="/api/v1/games", tags=["games"])

# @router.get("")
# def read_games():
#     return []

# @router.get("/{game_id}")
# def get_game(game_id: UUID):
#     raise HTTPException(status_code=404, detail="Game not found")

# @router.post("", status_code=201)
# def create_game(body: CreateGameRequest):
#     return {"word_length": body.word_length, "max_guesses": body.word_length+1}

# @router.get("/{game_id}/guesses")
# def read_guesses(game_id: UUID):
#     raise HTTPException(status_code=404, detail="Game not found")

# @router.post("/{game_id}/guesses", status_code=201, response_model=GuessCreatedResponse)
# def submit_guess(game_id: UUID, body: CreateGuessRequest):
#     raise HTTPException(status_code=404, detail="Game not found")


from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import game_service
from app.api.v1.schemas import (
    CreateGameRequest,
    CreateGuessRequest,
    GameResponse,
    GuessCreatedResponse,
    GuessResponse,
)
from app.db import get_session

router = APIRouter(prefix="/api/v1/games", tags=["games"])


@router.get("", response_model=list[GameResponse])
def read_games(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    # newest first, paged with ?limit= and ?offset= so the response can't grow without bound
    games = game_service.list_games(session, limit=limit, offset=offset)
    return [GameResponse.from_row(game) for game in games]


@router.post("", status_code=201, response_model=GameResponse)
def create_game(body: CreateGameRequest, session: Session = Depends(get_session)):
    return GameResponse.from_row(game_service.create_game(session, body.word_length))


@router.get("/{game_id}", response_model=GameResponse)
def get_game(game_id: UUID, session: Session = Depends(get_session)):
    return GameResponse.from_row(game_service.get_game(session, game_id))


@router.get("/{game_id}/guesses", response_model=list[GuessResponse])
def read_guesses(game_id: UUID, session: Session = Depends(get_session)):
    game = game_service.get_game(session, game_id)
    return [GuessResponse.from_row(guess, game.answer) for guess in game.guesses]


@router.post("/{game_id}/guesses", status_code=201, response_model=GuessCreatedResponse)
def submit_guess(
    game_id: UUID, body: CreateGuessRequest, session: Session = Depends(get_session)
):
    guess, game = game_service.submit_guess(session, game_id, body.word_guessed)
    return GuessCreatedResponse.from_rows(guess, game)
