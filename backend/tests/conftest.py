"""Fixtures for the test layers that use the database (API, security, concurrency).

The unit tests never ask for these fixtures, so they never touch a database.

How the test database is prepared
---------------------------------
1. Once per run (`database`): check the database is a test one, drop and recreate every
   table, and load the small word lists from tests/words/.
2. Before every test (`clean_database`): empty the user and game tables, and forget the
   log-in and sign-up attempts counted so far. The words stay.
   Each test therefore starts from the same state, whatever ran before it.
"""

import itertools
import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from tests.support import API, PASSWORD, Player

TEST_WORDS_DIR = Path(__file__).parent / "words"

# everything except `words`; emptied before each test
TABLES_TO_EMPTY = "game_players, guesses, games, auth_sessions, users"


def _require_test_database() -> None:
    """Stops the run unless DATABASE_URL names a database ending in "_test".

    These tests drop tables and delete rows. This is what keeps them away from the
    development database even if someone points DATABASE_URL at the wrong place.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.exit("DATABASE_URL is not set. Run the tests with `make test-api`.", returncode=2)
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.exit(
            f"Refusing to run: database '{name}' is not a test database "
            "(its name must end in '_test').",
            returncode=2,
        )


@pytest.fixture(scope="session")
def database():
    _require_test_database()

    # imported here, after the check, so nothing connects before it
    from app.db import Base, SessionLocal, engine
    from app.words import seed

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    # The application's own seeding code, pointed at the test word lists.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(seed, "DATA_DIR", TEST_WORDS_DIR)
        with SessionLocal() as session:
            seed.seed_words_if_empty(session)

    yield engine
    engine.dispose()


@pytest.fixture
def clean_database(database):
    with database.begin() as connection:
        connection.execute(text(f"TRUNCATE {TABLES_TO_EMPTY} RESTART IDENTITY CASCADE"))
    # the log-in and sign-up limits count attempts in memory; start each test from zero,
    # or one test's failed log-ins would lock out the next
    from app.api.v1 import rate_limits

    for limiter in rate_limits.ALL_LIMITERS:
        limiter.reset()


@pytest.fixture
def db(clean_database):
    """A database session, for the few things a test cannot do through the API
    (such as making a sign-in expire)."""
    from app.db import SessionLocal

    with SessionLocal() as session:
        yield session


@pytest.fixture
def new_client(clean_database):
    """Makes HTTP clients. Each has its own cookies, like a separate browser."""
    from fastapi.testclient import TestClient

    from main import app

    clients = []

    def make() -> TestClient:
        client = TestClient(app)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


@pytest.fixture
def client(new_client):
    """A client that is not signed in."""
    return new_client()


@pytest.fixture
def make_player(new_client):
    """Creates an account through the API and returns it signed in."""
    numbers = itertools.count(1)

    def make(username: str | None = None, password: str = PASSWORD) -> Player:
        username = username or f"player_{next(numbers)}"
        client = new_client()
        response = client.post(
            f"{API}/users", json={"username": username, "password": password}
        )
        assert response.status_code == 201, response.text
        return Player(client, username, password, response.json())

    return make


@pytest.fixture
def player(make_player):
    return make_player()


@pytest.fixture
def other_player(make_player):
    return make_player()
