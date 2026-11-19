import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
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

from app.domain.rules import MAX_WORD_LENGTH, GameStatus

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://wordle:wordle@db:5432/wordle"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(30), unique=True)
    # never the password itself: a salted scrypt hash (see app/security.py)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AuthSessionRow(Base):
    """One sign-in. The browser holds the token; only its hash is stored here."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # A second secret for this sign-in. The page must send it back in a header on every
    # request that changes something, which proves the request came from our own page.
    csrf_token: Mapped[str | None] = mapped_column(String(64))

    user: Mapped["UserRow"] = relationship()


class WordRow(Base):
    __tablename__ = "words"
    __table_args__ = (Index("ix_words_length_is_answer", "length", "is_answer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH), unique=True)
    length: Mapped[int] = mapped_column(Integer)
    is_answer: Mapped[bool] = mapped_column(Boolean, default=False)


class GameRow(Base):
    __tablename__ = "games"
    # the games list is sorted and paged by (created_at, id); this index lets the
    # database jump straight to a cursor's position instead of scanning the table
    __table_args__ = (Index("ix_games_created_at_id", "created_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    answer: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH))
    word_length: Mapped[int] = mapped_column(Integer)
    max_guesses: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), default=GameStatus.in_progress.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # who created the game
    owner: Mapped["UserRow | None"] = relationship()
    # everyone playing it, the owner included; goes through the game_players table
    players: Mapped[list["UserRow"]] = relationship(
        secondary="game_players", order_by="GamePlayerRow.joined_at"
    )
    guesses: Mapped[list["GuessRow"]] = relationship(
        order_by="GuessRow.number", cascade="all, delete-orphan"
    )


class GuessRow(Base):
    __tablename__ = "guesses"
    __table_args__ = (
        UniqueConstraint("game_id", "number", name="uq_guesses_game_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"))
    number: Mapped[int] = mapped_column(Integer)
    word: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # who made this guess
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    user: Mapped["UserRow | None"] = relationship()


class GamePlayerRow(Base):
    """Which users are in which game. One row per player per game."""

    __tablename__ = "game_players"

    # both columns together are the primary key, so a user can only be in a game once
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def create_tables() -> None:
    Base.metadata.create_all(engine)


def get_session():
    with SessionLocal() as session:
        yield session
