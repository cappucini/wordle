
# path to get all games 

# path to get specific game
# games/:id 

from fastapi import APIRouter, HTTPException
from uuid import UUID
from app.api.v1.schemas import CreateGameRequest, CreateGuessRequest, GuessCreatedResponse
# create a countainer for routes
router = APIRouter(prefix="/api/v1/games", tags=["games"])

@router.get("")
def read_games():
    return []

@router.get("/{game_id}")
def get_game(game_id: UUID):
    raise HTTPException(status_code=404, detail="Game not found")

@router.post("", status_code=201)
def create_game(body: CreateGameRequest):
    return {"word_length": body.word_length, "max_guesses": body.word_length+1}

@router.get("/{game_id}/guesses")
def read_guesses(game_id: UUID):
    raise HTTPException(status_code=404, detail="Game not found")

@router.post("/{game_id}/guesses", status_code=201, response_model=GuessCreatedResponse)
def submit_guess(game_id: UUID, body: CreateGuessRequest):
    raise HTTPException(status_code=404, detail="Game not found")


