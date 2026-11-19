"""The route that tells the frontend the game's limits (word lengths, extra guesses, players)."""

from fastapi import APIRouter
from app.domain.rules import (
    DEFAULT_WORD_LENGTH,
    EXTRA_GUESSES,
    MAX_PLAYERS_PER_GAME,
    MAX_WORD_LENGTH,
    MIN_WORD_LENGTH,
)

# create a container for routes
router = APIRouter(prefix="/api/v1/config", tags=["config"])


# Register GET request to /api/v1/config
@router.get("")
def read_configuration():
    """The game's limits (word lengths, extra guesses, players per game) for the frontend."""
    return {
        "min_word_length": MIN_WORD_LENGTH,
        "max_word_length": MAX_WORD_LENGTH,
        "default_word_length": DEFAULT_WORD_LENGTH,
        "extra_guesses": EXTRA_GUESSES,
        "max_players_per_game": MAX_PLAYERS_PER_GAME,
    }
