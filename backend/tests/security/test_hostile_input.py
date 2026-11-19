"""Input written to cause trouble is refused cleanly: a 4xx with an error code, never a 500,
and never a change to the database's structure."""

import base64
from urllib.parse import quote

import pytest
from sqlalchemy import inspect

from tests.support import API, PASSWORD

HOSTILE_TEXT = [
    pytest.param("' OR '1'='1", id="SQL: always-true condition"),
    pytest.param("'; DROP TABLE users; --", id="SQL: drop table"),
    pytest.param("admin'--", id="SQL: comment out the rest"),
    pytest.param('" OR ""="', id="SQL: double quotes"),
    pytest.param("1; SELECT pg_sleep(10)", id="SQL: stacked query"),
    pytest.param("<script>alert(1)</script>", id="HTML script tag"),
    pytest.param("../../etc/passwd", id="path traversal"),
    pytest.param("crane\x00", id="null byte"),
    pytest.param("%00%27", id="percent-encoded bytes"),
    pytest.param("\u202Eenarc", id="right-to-left override character"),
    pytest.param("a" * 10_000, id="10,000 characters"),
]


def cursor_of(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode()


def assert_refused_cleanly(response, allowed=(401, 404, 422)):
    assert response.status_code in allowed, response.text
    assert set(response.json()) == {"code", "detail"}


def assert_tables_are_intact(db):
    tables = set(inspect(db.get_bind()).get_table_names())
    assert {"users", "auth_sessions", "words", "games", "guesses", "game_players"} <= tables


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_hostile_username_at_sign_up_is_refused(client, db, text):
    response = client.post(f"{API}/users", json={"username": text, "password": PASSWORD})

    assert_refused_cleanly(response)
    assert response.json()["code"] == "INVALID_REQUEST"
    assert_tables_are_intact(db)


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_hostile_username_at_log_in_does_not_sign_anyone_in(player, client, db, text):
    response = client.post(f"{API}/sessions", json={"username": text, "password": PASSWORD})

    assert_refused_cleanly(response)
    assert "set-cookie" not in response.headers
    assert_tables_are_intact(db)


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_hostile_password_at_log_in_does_not_sign_anyone_in(player, client, db, text):
    response = client.post(
        f"{API}/sessions", json={"username": player.username, "password": text}
    )

    assert_refused_cleanly(response)
    assert "set-cookie" not in response.headers
    assert_tables_are_intact(db)


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_hostile_guess_is_refused_and_not_recorded(player, db, text):
    game = player.create_game()

    response = player.guess(game["id"], text)

    assert_refused_cleanly(response)
    assert player.game(game["id"])["guesses"] == []
    assert_tables_are_intact(db)


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_hostile_cursor_is_refused(player, db, text):
    player.create_game()

    for cursor in (text, cursor_of(text), cursor_of(f"{text}|{text}")):
        response = player.get("/games", params={"cursor": cursor})
        assert_refused_cleanly(response)
        assert response.json()["code"] == "INVALID_CURSOR"
    assert_tables_are_intact(db)


@pytest.mark.parametrize(
    "created_at",
    [
        pytest.param("2026-01-01", id="date only, no time zone"),
        pytest.param("2026-01-01T00:00:00", id="no time zone"),
        pytest.param("0001-01-01T00:00:00+00:00", id="earliest date Python allows"),
        pytest.param("9999-12-31T23:59:59.999999+00:00", id="latest date Python allows"),
        pytest.param("0001-01-01T00:00:00+23:59", id="before year 1 once converted to UTC"),
        pytest.param("9999-12-31T23:59:59-23:59", id="after year 9999 once converted to UTC"),
    ],
)
def test_well_formed_cursor_with_an_extreme_date_does_not_crash(player, created_at):
    # A cursor is only base64, so anyone can write one. These parse as valid cursors;
    # the server must answer (with a page or a 422), not fall over.
    game = player.create_game()

    response = player.get(
        "/games", params={"cursor": cursor_of(f"{created_at}|{game['id']}")}
    )

    assert response.status_code in (200, 422), response.text


@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_hostile_game_id_is_refused(player, db, text):
    # percent-encoded, as a browser would send it, so the text arrives as one path segment
    response = player.client.get(f"{API}/games/{quote(text[:200], safe='')}")

    assert response.status_code in (404, 422), response.text
    assert_tables_are_intact(db)


@pytest.mark.parametrize(
    "limit", ["1; DROP TABLE games", "1 OR 1=1", "99999999999999999999", "-1", "1e3"]
)
def test_hostile_limit_is_refused(player, limit):
    response = player.get("/games", params={"limit": limit})

    assert_refused_cleanly(response)
    assert response.json()["code"] == "INVALID_REQUEST"


def test_username_with_sql_in_it_cannot_be_registered_and_then_matched(client, new_client, db):
    # the classic second step of an injection: a stored value later used unsafely
    from app.db import UserRow

    client.post(f"{API}/users", json={"username": "erica", "password": PASSWORD})

    response = new_client().post(
        f"{API}/sessions", json={"username": "erica' --", "password": "anything at all"}
    )

    assert response.status_code == 422
    assert db.query(UserRow).count() == 1


def test_a_very_large_request_body_is_refused_not_stored(player, db):
    from app.db import GuessRow

    game = player.create_game()

    response = player.guess(game["id"], "a" * 1_000_000)

    assert response.status_code == 422
    assert db.query(GuessRow).count() == 0
