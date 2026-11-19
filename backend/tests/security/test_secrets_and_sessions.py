"""What is stored, what is sent back, and how the session cookie is set."""

import hashlib
import re

import pytest

from tests.support import API, PASSWORD, SESSION_COOKIE, put_session_cookie

SEVEN_DAYS_IN_SECONDS = 7 * 24 * 60 * 60


def cookie_attributes(response) -> dict:
    """The session cookie's Set-Cookie header as {attribute: value}, attributes lowercased."""
    header = next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(SESSION_COOKIE + "=")
    )
    attributes = {}
    for part in header.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        attributes[name.lower()] = value
    return attributes


def sign_up(client, username="erica"):
    return client.post(f"{API}/users", json={"username": username, "password": PASSWORD})


def log_in(client, username="erica"):
    return client.post(f"{API}/sessions", json={"username": username, "password": PASSWORD})


# ---------- what the database holds ----------


def test_password_is_stored_as_a_salted_hash_never_as_typed(player, db):
    from app.db import UserRow

    stored = db.query(UserRow).one().password_hash

    assert re.fullmatch(r"scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}", stored)
    assert player.password not in stored


def test_two_users_with_the_same_password_have_different_hashes(make_player, db):
    from app.db import UserRow

    make_player(password=PASSWORD)
    make_player(password=PASSWORD)

    first, second = (user.password_hash for user in db.query(UserRow).all())
    assert first != second


def test_session_token_is_stored_only_as_its_hash(player, db):
    from app.db import AuthSessionRow

    token = player.client.cookies.get(SESSION_COOKIE)

    row = db.query(AuthSessionRow).one()

    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    # the token itself is in no column, so a copy of the database cannot be used to sign in
    assert token not in (row.token_hash, row.csrf_token)


# ---------- what responses contain ----------


def test_no_response_contains_a_password_its_hash_or_the_session_token(
    player, other_player, new_client, db
):
    from app.db import UserRow

    token = player.client.cookies.get(SESSION_COOKIE)
    hashes = [user.password_hash for user in db.query(UserRow).all()]
    game = player.create_game()

    second_browser = new_client()
    responses = [
        log_in(second_browser, player.username),
        player.get("/users/me"),
        player.post("/games", json={"word_length": 5}),
        player.get(f"/games/{game['id']}"),
        other_player.join(game["id"]),
        player.guess(game["id"], "slate"),
        player.get(f"/games/{game['id']}/guesses"),
        player.get("/games"),
    ]
    token_after_log_in = second_browser.cookies.get(SESSION_COOKIE)

    for response in responses:
        assert response.status_code < 400, response.text
        assert PASSWORD not in response.text
        assert "password" not in response.text
        assert token not in response.text
        assert token_after_log_in not in response.text
        for password_hash in hashes:
            assert password_hash not in response.text


def test_users_are_described_by_id_and_username_only(player, other_player):
    game = player.create_game()

    joined = other_player.join(game["id"]).json()

    for listed in joined["players"]:
        assert set(listed) == {"id", "username"}


def test_csrf_token_is_not_the_session_token(player):
    assert player.csrf_token != player.client.cookies.get(SESSION_COOKIE)


# ---------- the session cookie ----------


@pytest.mark.parametrize("action", [sign_up, log_in], ids=["sign up", "log in"])
def test_session_cookie_is_set_with_safe_attributes(client, new_client, action):
    if action is log_in:
        sign_up(new_client())  # the account has to exist first

    cookie = cookie_attributes(action(client))

    assert "httponly" in cookie  # JavaScript on the page cannot read it
    assert cookie["samesite"].lower() == "lax"  # not sent on another site's background requests
    assert cookie["path"] == "/"
    assert int(cookie["max-age"]) == SEVEN_DAYS_IN_SECONDS
    assert "domain" not in cookie  # tied to the exact host that set it


def test_session_cookie_is_marked_secure_when_cookie_secure_is_on(client, monkeypatch):
    from app.api.v1 import auth

    monkeypatch.setattr(auth, "COOKIE_SECURE", True)

    assert "secure" in cookie_attributes(sign_up(client))


def test_session_cookie_is_not_marked_secure_by_default(client):
    # local development runs over plain HTTP, where a Secure cookie would never be sent back
    assert "secure" not in cookie_attributes(sign_up(client))


def test_log_out_tells_the_browser_to_delete_the_cookie(player):
    response = player.delete("/sessions/current")

    cookie = cookie_attributes(response)
    assert cookie["max-age"] == "0"
    assert cookie["path"] == "/"


# ---------- sessions ----------


def test_every_sign_in_gets_a_new_token(client, new_client):
    sign_up(client)
    tokens = {client.cookies.get(SESSION_COOKIE)}
    csrf_tokens = set()

    for _ in range(5):
        browser = new_client()
        csrf_tokens.add(log_in(browser).json()["csrf_token"])
        tokens.add(browser.cookies.get(SESSION_COOKIE))

    assert len(tokens) == 6
    assert len(csrf_tokens) == 5


def test_log_in_does_not_adopt_a_cookie_the_browser_already_had(client, new_client):
    # "session fixation": an attacker plants a cookie value they know, then waits for the
    # victim to sign in. The server must issue its own value and never honour the planted one.
    sign_up(new_client())
    planted = "attacker-chosen-value-0123456789012345678901234"
    put_session_cookie(client, planted)

    response = log_in(client)

    assert response.status_code == 201

    assert client.cookies.get(SESSION_COOKIE) != planted
    attacker = new_client()
    put_session_cookie(attacker, planted)
    assert attacker.get(f"{API}/users/me").status_code == 401


def test_one_users_session_cannot_be_used_as_another_user(player, other_player):
    assert player.get("/users/me").json()["user"]["id"] == player.id
    assert other_player.get("/users/me").json()["user"]["id"] == other_player.id


def test_session_cookie_copied_before_log_out_stops_working_after_it(player, new_client):
    thief = player.in_another_browser(new_client())
    assert thief.get("/users/me").status_code == 200  # the copy works while signed in

    player.delete("/sessions/current")

    assert thief.get("/users/me").status_code == 401
    assert thief.get("/games").status_code == 401
    assert thief.post("/games", json={"word_length": 5}).status_code == 401


# ---------- log in gives nothing away ----------


def test_log_in_answers_the_same_for_an_unknown_user_and_a_wrong_password(player, new_client):
    # otherwise the log-in form could be used to find out which usernames exist
    wrong_password = new_client().post(
        f"{API}/sessions", json={"username": player.username, "password": "wrong password"}
    )
    unknown_user = new_client().post(
        f"{API}/sessions", json={"username": "no_such_user", "password": "wrong password"}
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert "set-cookie" not in wrong_password.headers
    assert "set-cookie" not in unknown_user.headers
