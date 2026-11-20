"""The database: the connection to Postgres, and one class per table (users, sign-ins,
words, games, players and guesses).
"""

# os: reads settings from the environment (the database's address)
import os
# uuid: makes the long random ids used for users and games
import uuid
# datetime and timezone: the date-and-time values stored in the "..._at" columns
from datetime import datetime, timezone

# From SQLAlchemy, the library that talks to the database: the column types, the kinds of
# rule a table can carry, and create_engine, which opens the connection.
from sqlalchemy import (
    Boolean,  # column type: true or false
    CheckConstraint,  # rule: a condition every row must satisfy
    DateTime,  # column type: a date and time
    ForeignKey,  # rule: this column's value must exist in another table
    ForeignKeyConstraint,  # the same rule, for a pair of columns together
    Index,  # a lookup aid that makes searches on a column fast
    Integer,  # column type: a whole number
    String,  # column type: text, with a maximum length
    UniqueConstraint,  # rule: no two rows may share these values
    Uuid,  # column type: a UUID
    create_engine,  # opens the connection to the database
)
# The parts of SQLAlchemy that turn a Python class into a table.
from sqlalchemy.orm import (
    DeclarativeBase,  # the parent class a table class inherits from
    Mapped,  # marks an attribute as a column and gives its Python type
    mapped_column,  # describes the database column behind an attribute
    relationship,  # an attribute that loads related rows from another table
    sessionmaker,  # builds the function that opens database sessions
)

# The game's numbers and statuses, so the database rules below use the same values as the code.
from app.domain.rules import (
    EXTRA_GUESSES,  # how many guesses a game gets beyond its word length (1)
    MAX_WORD_LENGTH,  # the longest word a game may use (8)
    MIN_WORD_LENGTH,  # the shortest word a game may use (5)
    GameStatus,  # the three states of a game: in progress, won, lost
)

# The rules of the game are checked by the code in app/game_service.py, which gives players
# a clear error. The rules that one row can be checked against by itself are also enforced by
# the database (the CHECK constraints, required columns and foreign keys in this file), which
# refuses such a row no matter which code tried to save it. The numbers in these constraints
# come from app/domain/rules.py.

# The allowed statuses written as SQL text: 'in_progress', 'won', 'lost'.
# It puts quotes round each status value and joins them with commas, ready to be dropped
# into the "status IN (...)" rule on the games table.
_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in GameStatus)

# Where the database is. Read from the DATABASE_URL setting; the second value is the
# fallback used when that setting is missing. The parts of the address are:
# database type + driver :// user : password @ host : port / database name
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

    # nothing to add: the class only exists to be inherited from
    pass


class UserRow(Base):
    """One account: a row in the users table."""

    # the name of the table in the database
    __tablename__ = "users"

    # How every column below is written: Mapped[...] is the Python type of the attribute,
    # and mapped_column(...) describes the database column behind it.
    # id: the account's unique id. primary_key=True makes it the column that identifies a row.
    # default=uuid.uuid4 passes the function itself (no brackets): it is called for each
    # new row, so every row gets its own id.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # username: text of at most 30 characters. unique=True makes the database refuse a
    # second account with the same name.
    username: Mapped[str] = mapped_column(String(30), unique=True)
    # never the password itself: a salted scrypt hash (see app/security.py)
    password_hash: Mapped[str] = mapped_column(String(200))
    # created_at: when the account was made, stored with its time zone.
    # the default is a lambda for the same reason: the time is read when a row is
    # created, not once when this file is loaded
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AuthSessionRow(Base):
    """One sign-in. The browser holds the token; only its hash is stored here."""

    # the name of the table in the database
    __tablename__ = "auth_sessions"

    # token_hash: the SHA-256 hash of the token in the browser's cookie (64 hex characters).
    # It is the primary key, so a sign-in is looked up directly by it.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # user_id: whose sign-in this is.
    # ForeignKey: the value must be the id of an existing row in users.
    # index=True makes it fast to find all of one user's sign-ins.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # created_at: when the player signed in
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # expires_at: the moment this sign-in stops working. It has no default: the code
    # that creates the sign-in sets it, and pushes it back while the sign-in is in use.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # A second secret for this sign-in. The page must send it back in a header on every
    # request that changes something, which proves the request came from our own page.
    csrf_token: Mapped[str] = mapped_column(String(64))

    # not a column: relationship() loads the UserRow that user_id points to
    user: Mapped["UserRow"] = relationship()


class WordRow(Base):
    """One word from the word lists. Every word may be guessed; is_answer marks the ones
    a game may pick as its answer."""

    # the name of the table in the database
    __tablename__ = "words"
    # __table_args__ holds the table's extra rules and indexes. It must be a tuple, which
    # is why a single item still ends with a comma.
    # one index over both columns, for finding the answer words of a given length
    __table_args__ = (Index("ix_words_length_is_answer", "length", "is_answer"),)

    # id: a whole number the database counts up by itself for each new word
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # text: the word. unique=True means no word is stored twice, and also makes
    # "is this a real word?" a fast lookup.
    text: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH), unique=True)
    # length: how many letters the word has, stored so words can be found by length
    length: Mapped[int] = mapped_column(Integer)
    # is_answer: True if a game may choose this word as its answer. False (the default)
    # for words that are only accepted as guesses.
    is_answer: Mapped[bool] = mapped_column(Boolean, default=False)


class GameRow(Base):
    """One game: its answer, its limits and its status, with its players and guesses."""

    # the name of the table in the database
    __tablename__ = "games"
    # the games list is sorted and paged by (created_at, id); this index lets the
    # database jump straight to a cursor's position instead of scanning the table
    __table_args__ = (
        Index("ix_games_created_at_id", "created_at", "id"),
        # the database refuses a game row that breaks any of these
        # the status must be one of the three known values
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_games_status"),
        # the word length must be within the allowed range (5 to 8)
        CheckConstraint(
            f"word_length BETWEEN {MIN_WORD_LENGTH} AND {MAX_WORD_LENGTH}",
            name="ck_games_word_length",
        ),
        # the number of guesses allowed is always the word length plus one
        CheckConstraint(
            f"max_guesses = word_length + {EXTRA_GUESSES}", name="ck_games_max_guesses"
        ),
        # the answer must have exactly as many letters as the game's word length
        CheckConstraint(
            "char_length(answer) = word_length", name="ck_games_answer_length"
        ),
    )

    # id: the game's unique id, which also appears in its link
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Every column in this file is required (NOT NULL): a type without "| None" makes it so.
    # owner_id: the user who created the game. Indexed to find one user's games quickly.
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    # answer: the word the players are trying to guess
    answer: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH))
    # word_length: how many letters the player chose for this game
    word_length: Mapped[int] = mapped_column(Integer)
    # max_guesses: how many guesses the game allows in total
    max_guesses: Mapped[int] = mapped_column(Integer)
    # stored as text: one of the GameStatus values. A new game starts as "in progress".
    status: Mapped[str] = mapped_column(
        String(20), default=GameStatus.in_progress.value
    )
    # created_at: when the game was started
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # The three attributes below are not columns. Each loads related rows when it is read.
    # who created the game
    owner: Mapped["UserRow"] = relationship()
    # everyone playing it, the owner included; goes through the game_players table
    # (secondary names that linking table; order_by lists players in the order they joined)
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

    # the name of the table in the database
    __tablename__ = "guesses"
    # the database refuses a second guess with the same number in the same game
    __table_args__ = (
        UniqueConstraint("game_id", "number", name="uq_guesses_game_number"),
        # guess numbers start at 1; zero or a negative number is refused
        CheckConstraint("number >= 1", name="ck_guesses_number"),
        # whoever made a guess must be one of that game's players: the pair
        # (game_id, user_id) has to exist as a row in game_players
        ForeignKeyConstraint(
            # the two columns in this table...
            ["game_id", "user_id"],
            # ...and the two columns in game_players they must match
            ["game_players.game_id", "game_players.user_id"],
            # the rule's name, shown in the database's error if it is ever broken
            name="fk_guesses_made_by_a_player",
        ),
    )

    # id: a whole number the database counts up by itself for each new guess
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # game_id: the game this guess belongs to; must be the id of an existing game
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"))
    # number: which turn this was (1 for the first guess in the game, 2 for the second...)
    number: Mapped[int] = mapped_column(Integer)
    # word: the word that was guessed
    word: Mapped[str] = mapped_column(String(MAX_WORD_LENGTH))
    # created_at: when the guess was made
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # who made this guess
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    # not a column: loads the UserRow that user_id points to, for showing the guesser's name
    user: Mapped["UserRow"] = relationship()


class GamePlayerRow(Base):
    """Which users are in which game. One row per player per game."""

    # the name of the table in the database
    __tablename__ = "game_players"

    # both columns together are the primary key, so a user can only be in a game once
    game_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("games.id"), primary_key=True)
    # indexed on its own as well: "Your games" looks rows up by user, and the primary key
    # (which starts with game_id) is no help for that
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True, index=True
    )
    # joined_at: when this player joined, used to list players in joining order
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def create_tables() -> None:
    """Creates the tables that do not exist yet. Existing tables are left as they are:
    a constraint added to a table class above only reaches a database when its tables
    are created again (see the README)."""
    # Base.metadata is SQLAlchemy's list of every table class defined above
    Base.metadata.create_all(engine)


def get_session():
    """Gives a route its database session: routes ask for it with Depends(get_session).

    The `yield` hands the session over. Once the request is finished, the function
    carries on past the yield and leaves the `with` block, which closes the session.
    """
    # open a session; the `with` block guarantees it is closed again, even after an error
    with SessionLocal() as session:
        # hand the session to the route and pause here until the request is finished
        yield session
