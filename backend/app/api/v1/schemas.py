"""The shapes of the API's requests and responses: what the frontend must send, what it gets
back, and the checks applied to incoming data (username, password, word length, guess).
"""

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
    # extra="forbid": a body with any field not listed here is refused with a 422
    model_config = ConfigDict(extra="forbid")

    # Field(...) adds rules that pydantic checks before the route runs
    username: str = Field(
        min_length=MIN_USERNAME_LENGTH,
        max_length=MAX_USERNAME_LENGTH,
        pattern=USERNAME_PATTERN,
    )
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    # usernames are not case-sensitive: "Erica" and "erica" are the same account.
    # mode="before" runs this ahead of the Field rules above, so they check the tidied
    # value. At that point the value may not be text at all, hence the isinstance check.
    @field_validator("username", mode="before")
    @classmethod
    def normalise_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    # eight spaces are eight characters, but not a password.
    # A validator returns the value to keep, or raises ValueError to refuse the request.
    @field_validator("password")
    @classmethod
    def password_is_not_blank(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("must not be only spaces")
        return value


# What other people may see about a user. The password hash is never included.
class UserResponse(BaseModel):
    id: UUID
    username: str

    # the return type is in quotes because the class is still being defined at this point
    @classmethod
    def from_row(cls, user) -> "UserResponse":
        """Builds the response from a UserRow, copying only the fields listed above."""
        return cls(id=user.id, username=user.username)


class AuthResponse(BaseModel):
    """The answer to signing up, logging in and GET /users/me: the user and the CSRF token."""

    user: UserResponse
    # The session itself is in an HttpOnly cookie, never in a response body.
    # This is the CSRF token: the page sends it back in the X-CSRF-Token header
    # on every request that changes something.
    csrf_token: str | None = None


class CreateGameRequest(BaseModel):
    """The body of POST /games. word_length may be left out; if given it must be in range."""

    model_config = ConfigDict(extra="forbid")

    word_length: int = Field(
        default=DEFAULT_WORD_LENGTH, ge=MIN_WORD_LENGTH, le=MAX_WORD_LENGTH
    )


class CreateGuessRequest(BaseModel):
    """The body of POST /games/{game_id}/guesses: one word, letters only."""

    # the two str_ settings tidy every text field before it is checked:
    # spaces around the word are removed and it is lowercased
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, str_to_lower=True
    )

    word_guessed: str = Field(
        min_length=MIN_WORD_LENGTH, max_length=MAX_WORD_LENGTH, pattern=WORD_PATTERN
    )


class GuessResponse(BaseModel):
    """One guess as the page sees it: the word, and a result for each of its letters."""

    number: int
    word: str
    results: list[LetterResult]
    guessed_by: str | None = None  # username of the player who made this guess

    @classmethod
    def from_row(cls, guess, answer: str) -> "GuessResponse":
        """Builds the response from a GuessRow. The results are worked out here, not stored."""
        return cls(
            number=guess.number,
            word=guess.word,
            results=score(guess.word, answer),
            guessed_by=guess.user.username if guess.user is not None else None,
        )


class GameResponse(BaseModel):
    """A game as the page sees it. The answer is left out until the game is over."""

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
        """Builds the response from a GameRow, with its players and its scored guesses."""
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
    """One page of the games list, and the cursor for the page after it."""

    items: list[GameResponse]
    # send this back as ?cursor= to get the next page; null when there are no more games
    next_cursor: str | None = None


class GuessCreatedResponse(GuessResponse):
    """The answer to a new guess: the scored guess, plus the state it left the game in.

    It inherits from GuessResponse, so it has all of that class's fields as well.
    """

    game_status: GameStatus
    guesses_remaining: int
    answer: str | None = None

    @classmethod
    def from_rows(cls, guess, game) -> "GuessCreatedResponse":
        """Builds the response from the saved GuessRow and the GameRow it belongs to."""
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
