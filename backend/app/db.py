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

from app.domain.rules import GameStatus

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    games: Mapped[list["GameRow"]] = relationship(
        back_populates="owner", order_by="GameRow.created_at"
    )


class WordRow(Base):
    __tablename__ = "words"
    __table_args__ = (Index("ix_words_length_is_answer", "length", "is_answer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(8), unique=True)
    length: Mapped[int] = mapped_column(Integer)
    is_answer: Mapped[bool] = mapped_column(Boolean, default=False)


class GameRow(Base):
    __tablename__ = "games"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    answer: Mapped[str] = mapped_column(String(8))
    word_length: Mapped[int] = mapped_column(Integer)
    max_guesses: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), default=GameStatus.in_progress.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    owner: Mapped["UserRow | None"] = relationship(back_populates="games")  # new
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
    word: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class GamePlayerRow(Base):
    __tablename__ = "game_players"

    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(20), default=GameStatus.in_progress.value
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def create_tables() -> None:
    Base.metadata.create_all(engine)


def get_session():
    with SessionLocal() as session:
        yield session
