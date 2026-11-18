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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.rules import (
    DEFAULT_WORD_LENGTH,
    MAX_PASSWORD_LENGTH,
    MAX_PLAYERS_PER_GAME,
    MAX_USERNAME_LENGTH,
    MAX_WORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    MIN_USERNAME_LENGTH,
    MIN_WORD_LENGTH,
    USERNAME_PATTERN,
    WORD_PATTERN,
    GameStatus,
    LetterResult,
)
from app.domain.scoring import score


# Used for both creating an account and signing in.
class CredentialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        min_length=MIN_USERNAME_LENGTH,
        max_length=MAX_USERNAME_LENGTH,
        pattern=USERNAME_PATTERN,
    )
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    # usernames are not case-sensitive: "Erica" and "erica" are the same account
    @field_validator("username", mode="before")
    @classmethod
    def normalise_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


# What other people may see about a user. The password hash is never included.
class UserResponse(BaseModel):
    id: UUID
    username: str

    @classmethod
    def from_row(cls, user) -> "UserResponse":
        return cls(id=user.id, username=user.username)


class AuthResponse(BaseModel):
    user: UserResponse
    # The session itself is in an HttpOnly cookie, never in a response body.
    # This is the CSRF token: the page sends it back in the X-CSRF-Token header
    # on every request that changes something.
    csrf_token: str | None = None


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
    guessed_by: str | None = None  # username of the player who made this guess

    @classmethod
    def from_row(cls, guess, answer: str) -> "GuessResponse":
        return cls(
            number=guess.number,
            word=guess.word,
            results=score(guess.word, answer),
            guessed_by=guess.user.username if guess.user is not None else None,
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
    owner_id: UUID | None = None
    players: list[UserResponse]  # everyone in the game, in the order they joined
    max_players: int

    @classmethod
    def from_row(cls, game) -> "GameResponse":
        is_over = game.status != GameStatus.in_progress
        return cls(
            owner_id=game.owner_id,
            players=[UserResponse.from_row(player) for player in game.players],
            max_players=MAX_PLAYERS_PER_GAME,
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
            guessed_by=guess.user.username if guess.user is not None else None,
            game_status=game.status,
            guesses_remaining=game.max_guesses - len(game.guesses),
            answer=game.answer if is_over else None,
        )
