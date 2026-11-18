from fastapi import APIRouter
from app.domain.rules import (
    DEFAULT_WORD_LENGTH,
    EXTRA_GUESSES,
    MAX_WORD_LENGTH,
    MIN_WORD_LENGTH,
)

# create a countainer for routes
router = APIRouter(prefix="/api/v1/config", tags=["config"])


# Register GET request to /api/v1/config
@router.get("")
def read_configuration():
    return {
        "min_word_length": MIN_WORD_LENGTH,
        "max_word_length": MAX_WORD_LENGTH,
        "default_word_length": DEFAULT_WORD_LENGTH,
        "extra_guesses": EXTRA_GUESSES,
    }
