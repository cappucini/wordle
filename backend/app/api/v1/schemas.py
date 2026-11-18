# from pydantic import BaseModel, ConfigDict, Field, field_validator
# from enum import Enum

# from app.domain.rules import (
#     DEFAULT_WORD_LENGTH,
#     MAX_WORD_LENGTH,
#     MIN_WORD_LENGTH,
#     WORD_PATTERN,
#     GameStatus,
#     LetterResult,
# )

# # class GameStatus(str, Enum):
# #     in_progress = "in_progress"
# #     won = "won"
# #     lost = "lost"

# class LetterResult(str, Enum):
#     correct="correct"
#     present="present"
#     absent="absent"
# """
# CreateGameRequest inherits BaseModel with a specific configuration and allowed field.
# """
# class CreateGameRequest(BaseModel):
#     # forbid extra fields
#     model_config=ConfigDict(extra="forbid")
#     # the only field allowed is word length
#     word_length: int = Field(default=5, ge=5, le=8)

# """
# CreateGuessRequest inherits BaseModel with a specific configuration and allowed field.
# """
# class CreateGuessRequest(BaseModel):
#     #forbid extra fields
#     model_config = ConfigDict(extra="forbid")
#     # word guessed can have length in range [5,8]
#     word_guessed: str = Field(min_length=MIN_WORD_LENGTH, max_length=MAX_WORD_LENGTH, pattern=WORD_PATTERN)

# class GuessCreatedResponse(BaseModel):
#     model_config = ConfigDict(from_attributes=True)
#     # guess number
#     number: int
#     word: str
#     results: list[LetterResult]
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.rules import (
    DEFAULT_WORD_LENGTH,
    MAX_WORD_LENGTH,
    MIN_WORD_LENGTH,
    WORD_PATTERN,
    GameStatus,
    LetterResult,
)
from app.domain.scoring import score


class CreateGameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    word_length: int = Field(
        default=DEFAULT_WORD_LENGTH, ge=MIN_WORD_LENGTH, le=MAX_WORD_LENGTH
    )


class CreateGuessRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, str_to_lower=True
    )

    word_guessed: str = Field(
        min_length=MIN_WORD_LENGTH, max_length=MAX_WORD_LENGTH, pattern=WORD_PATTERN
    )


class GuessResponse(BaseModel):
    number: int
    word: str
    results: list[LetterResult]

    @classmethod
    def from_row(cls, guess, answer: str) -> "GuessResponse":
        return cls(
            number=guess.number, word=guess.word, results=score(guess.word, answer)
        )


class GameResponse(BaseModel):
    id: UUID
    word_length: int
    max_guesses: int
    guesses_remaining: int
    status: GameStatus
    guesses: list[GuessResponse]
    answer: str | None = None  # only revealed once the game is over
    created_at: datetime

    @classmethod
    def from_row(cls, game) -> "GameResponse":
        is_over = game.status != GameStatus.in_progress
        return cls(
            id=game.id,
            word_length=game.word_length,
            max_guesses=game.max_guesses,
            guesses_remaining=game.max_guesses - len(game.guesses),
            status=game.status,
            guesses=[
                GuessResponse.from_row(guess, game.answer) for guess in game.guesses
            ],
            answer=game.answer if is_over else None,
            created_at=game.created_at,
        )


class GameListResponse(BaseModel):
    items: list[GameResponse]
    # send this back as ?cursor= to get the next page; null when there are no more games
    next_cursor: str | None = None


class GuessCreatedResponse(GuessResponse):
    game_status: GameStatus
    guesses_remaining: int
    answer: str | None = None

    @classmethod
    def from_rows(cls, guess, game) -> "GuessCreatedResponse":
        is_over = game.status != GameStatus.in_progress
        return cls(
            number=guess.number,
            word=guess.word,
            results=score(guess.word, game.answer),
            game_status=game.status,
            guesses_remaining=game.max_guesses - len(game.guesses),
            answer=game.answer if is_over else None,
        )
