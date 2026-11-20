"""The database: the connection to Postgres, and one class per table (users, sign-ins,
words, games, players and guesses).
"""

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.domain.rules import (
    EXTRA_GUESSES,
    MAX_WORD_LENGTH,
    MIN_WORD_LENGTH,
    GameStatus,
)

# The rules of the game are checked by the code in app/game_service.py, which gives players
# a clear error. The rules that one row can be checked against by itself are also enforced by
# the database (the CHECK constraints, required columns and foreign keys in this file), which
# refuses such a row no matter which code tried to save it. The numbers in these constraints
# come from app/domain/rules.py.
_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in GameStatus)

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://wordle:wordle@db:5432/wordle"
)

# the engine holds the pool of connections to the database; there is one per process
engine = create_engine(DATABASE_URL)
# Calling SessionLocal() opens a session: one unit of work with the database.
# expire_on_commit=False keeps a row's loaded values readable after a commit, so a
# route can build its response from the row without another query.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """The parent of every table class below. SQLAlchemy keeps track of its subclasses,
    which is how create_tables knows which tables exist."""

    pass


class UserRow(Base):
    """One account: a row in the users table."""

    __tablename__ = "users"

    # How every column below is written: Mapped[...] is the Python type of the attribute,
    # and mapped_column(...) describes the database column behind it.
    # default=uuid.uuid4 passes the function itself (no brackets): it is called for each
    # new row, so every row gets its own id.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(30), unique=True)
    # never the password itself: a salted scrypt hash (see app/security.py)
    password_hash: Mapped[str] = mapped_column(String(200))
    # the default is a lambda for the same reason: the time is read when a row is
    # created, not once when this file is loaded
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AuthSessionRow(Base):
    """One sign-in. The browser holds the token; only its hash is stored here."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # ForeignKey: the value must be the id of an existing row in users
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # A second secret for this sign-in. The page must send it back in a header on every
    # request that changes something, which proves the request came from our own page.
    csrf_token: Mapped[str] = mapped_column(String(64))

    # not a column: relationship() loads the UserRow that user_id points to
    user: Mapped["UserRow"] = relationship()


class WordRow(Base):
    """One word from the word lists. Every word may be guessed; is_answer marks the ones
    a game may pick as its answer."""

    __tablename__ = "words"
    # one index over both columns, for finding the answer words of a given length
    __table_args__ = (Index("ix_words_length_is_answer", "length", "is_answer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH), unique=True)
    length: Mapped[int] = mapped_column(Integer)
    is_answer: Mapped[bool] = mapped_column(Boolean, default=False)


class GameRow(Base):
    """One game: its answer, its limits and its status, with its players and guesses."""

    __tablename__ = "games"
    # the games list is sorted and paged by (created_at, id); this index lets the
    # database jump straight to a cursor's position instead of scanning the table
    __table_args__ = (
        Index("ix_games_created_at_id", "created_at", "id"),
        # the database refuses a game row that breaks any of these
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_games_status"),
        CheckConstraint(
            f"word_length BETWEEN {MIN_WORD_LENGTH} AND {MAX_WORD_LENGTH}",
            name="ck_games_word_length",
        ),
        CheckConstraint(
            f"max_guesses = word_length + {EXTRA_GUESSES}", name="ck_games_max_guesses"
        ),
        CheckConstraint(
            "char_length(answer) = word_length", name="ck_games_answer_length"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Every column in this file is required (NOT NULL): a type without "| None" makes it so.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    answer: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH))
    word_length: Mapped[int] = mapped_column(Integer)
    max_guesses: Mapped[int] = mapped_column(Integer)
    # stored as text: one of the GameStatus values
    status: Mapped[str] = mapped_column(
        String(20), default=GameStatus.in_progress.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # who created the game
    owner: Mapped["UserRow"] = relationship()
    # everyone playing it, the owner included; goes through the game_players table
    players: Mapped[list["UserRow"]] = relationship(
        secondary="game_players", order_by="GamePlayerRow.joined_at"
    )
    # in the order they were made. The cascade saves new guesses along with the game,
    # and deletes a game's guesses when the game is deleted.
    guesses: Mapped[list["GuessRow"]] = relationship(
        order_by="GuessRow.number", cascade="all, delete-orphan"
    )


class GuessRow(Base):
    """One guess made in a game. `number` is its turn, counted across all the players."""

    __tablename__ = "guesses"
    # the database refuses a second guess with the same number in the same game
    __table_args__ = (
        UniqueConstraint("game_id", "number", name="uq_guesses_game_number"),
        CheckConstraint("number >= 1", name="ck_guesses_number"),
        # whoever made a guess must be one of that game's players: the pair
        # (game_id, user_id) has to exist as a row in game_players
        ForeignKeyConstraint(
            ["game_id", "user_id"],
            ["game_players.game_id", "game_players.user_id"],
            name="fk_guesses_made_by_a_player",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"))
    number: Mapped[int] = mapped_column(Integer)
    word: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # who made this guess
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    user: Mapped["UserRow"] = relationship()


class GamePlayerRow(Base):
    """Which users are in which game. One row per player per game."""

    __tablename__ = "game_players"

    # both columns together are the primary key, so a user can only be in a game once
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    # indexed on its own as well: "Your games" looks rows up by user, and the primary key
    # (which starts with game_id) is no help for that
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def create_tables() -> None:
    """Creates the tables that do not exist yet. Existing tables are left as they are:
    a constraint added to a table class above only reaches a database when its tables
    are created again (see the README)."""
    Base.metadata.create_all(engine)


def get_session():
    """Gives a route its database session: routes ask for it with Depends(get_session).

    The `yield` hands the session over. Once the request is finished, the function
    carries on past the yield and leaves the `with` block, which closes the session.
    """
    with SessionLocal() as session:
        yield session
