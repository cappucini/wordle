from pydantic import BaseModel, ConfigDict, Field, field_validator
from enum import Enum

from app.domain.rules import (
    DEFAULT_WORD_LENGTH,
    MAX_WORD_LENGTH,
    MIN_WORD_LENGTH,
    GameStatus,
    LetterResult,
)

# class GameStatus(str, Enum):
#     in_progress = "in_progress"
#     won = "won"
#     lost = "lost"

class LetterResult(str, Enum):
    correct="correct"
    present="present"
    absent="absent"
"""
CreateGameRequest inherits BaseModel with a specific configuration and allowed field.
"""
class CreateGameRequest(BaseModel):
    # forbid extra fields
    model_config=ConfigDict(extra="forbid")
    # the only field allowed is word length
    word_length: int = Field(default=5, ge=5, le=8)

"""
CreateGuessRequest inherits BaseModel with a specific configuration and allowed field.
"""
class CreateGuessRequest(BaseModel):
    #forbid extra fields
    model_config = ConfigDict(extra="forbid")
    # word guessed can have length in range [5,8]
    word_guessed: str = Field(min_length=5, max_length=8)

class GuessCreatedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # guess number
    number: int
    word: str
    results: list[LetterResult]
