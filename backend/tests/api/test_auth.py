"""Accounts and sign-ins: POST /users, POST /sessions, GET /users/me, DELETE /sessions/current."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.support import API, CSRF_HEADER, PASSWORD, SESSION_COOKIE, put_session_cookie

NOT_AUTHENTICATED = {"code": "NOT_AUTHENTICATED", "detail": "Sign in to continue"}
INVALID_CREDENTIALS = {"code": "INVALID_CREDENTIALS", "detail": "Wrong username or password"}


def set_session_expiry(db, when: datetime) -> None:
    from app.db import AuthSessionRow

    for row in db.query(AuthSessionRow).all():
        row.expires_at = when
    db.commit()


# ---------- sign up ----------


def test_sign_up_creates_the_account_and_signs_in(client):
    response = client.post(f"{API}/users", json={"username": "erica", "password": PASSWORD})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"user", "csrf_token"}
    assert set(body["user"]) == {"id", "username"}
    assert body["user"]["username"] == "erica"
    assert isinstance(body["csrf_token"], str) and len(body["csrf_token"]) >= 43
    assert SESSION_COOKIE in response.cookies

    # the cookie alone is enough to be recognised afterwards
    me = client.get(f"{API}/users/me")
    assert me.status_code == 200
    assert me.json() == body


def test_sign_up_stores_the_username_trimmed_and_lowercased(client):
    response = client.post(
        f"{API}/users", json={"username": "  Erica_1 ", "password": PASSWORD}
    )

    assert response.status_code == 201
    assert response.json()["user"]["username"] == "erica_1"


@pytest.mark.parametrize("second_spelling", ["erica", "ERICA", " Erica "])
def test_sign_up_with_a_taken_username_is_refused(client, new_client, second_spelling):
    client.post(f"{API}/users", json={"username": "erica", "password": PASSWORD})

    response = new_client().post(
        f"{API}/users", json={"username": second_spelling, "password": "another password"}
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "USERNAME_TAKEN",
        "detail": "The username 'erica' is already taken",
    }
    assert SESSION_COOKIE not in response.cookies


@pytest.mark.parametrize(
    "body, field",
    [
        pytest.param({"username": "ab", "password": PASSWORD}, "username", id="username too short"),
        pytest.param({"username": "a" * 21, "password": PASSWORD}, "username", id="username too long"),
        pytest.param({"username": "eri ca", "password": PASSWORD}, "username", id="username with a space"),
        pytest.param({"username": "erica!", "password": PASSWORD}, "username", id="username with punctuation"),
        pytest.param({"username": "erica", "password": "short"}, "password", id="password too short"),
        pytest.param({"username": "erica", "password": "p" * 129}, "password", id="password too long"),
        pytest.param({"username": "erica", "password": " " * 8}, "password", id="password of only spaces"),
        pytest.param({"username": "erica"}, "password", id="password missing"),
        pytest.param({"password": PASSWORD}, "username", id="username missing"),
        pytest.param(
            {"username": "erica", "password": PASSWORD, "is_admin": True}, "is_admin",
            id="unknown field",
        ),
    ],
)
def test_sign_up_with_an_invalid_body_is_refused(client, body, field):
    response = client.post(f"{API}/users", json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    # the detail names the field that is wrong
    assert response.json()["detail"].startswith(f"{field}: ")
    assert SESSION_COOKIE not in response.cookies


def test_request_body_that_is_not_json_is_refused(client):
    response = client.post(
        f"{API}/users", content="{not json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["detail"].startswith("body: ")


# ---------- log in ----------


def test_log_in_with_the_right_password(player, client):
    response = client.post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"] == {"id": player.id, "username": player.username}
    assert SESSION_COOKIE in response.cookies
    # a new sign-in is a new session, with its own CSRF token
    assert body["csrf_token"] != player.csrf_token

    assert client.get(f"{API}/users/me").json() == body


def test_log_in_ignores_the_case_of_the_username(player, client):
    response = client.post(
        f"{API}/sessions",
        json={"username": player.username.upper(), "password": player.password},
    )

    assert response.status_code == 201
    assert response.json()["user"]["id"] == player.id


def test_log_in_with_the_wrong_password_is_refused(player, client):
    response = client.post(
        f"{API}/sessions", json={"username": player.username, "password": "wrong password"}
    )

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS
    assert SESSION_COOKIE not in response.cookies
    assert client.get(f"{API}/users/me").status_code == 401


def test_log_in_with_an_unknown_username_is_refused(client):
    response = client.post(
        f"{API}/sessions", json={"username": "nobody", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS


def test_passwords_are_case_sensitive(make_player, client):
    player = make_player(password="Correct Horse")

    response = client.post(
        f"{API}/sessions", json={"username": player.username, "password": "correct horse"}
    )

    assert response.status_code == 401
    assert response.json() == INVALID_CREDENTIALS


def test_log_in_with_a_password_too_short_to_exist_is_an_invalid_request(player, client):
    # the same shape rules apply to both forms; the frontend words this as "wrong password"
    response = client.post(
        f"{API}/sessions", json={"username": player.username, "password": "short"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


# ---------- who is signed in ----------


def test_current_user_returns_the_user_and_the_csrf_token(player):
    response = player.get("/users/me")

    assert response.status_code == 200
    assert response.json() == {
        "user": {"id": player.id, "username": player.username},
        "csrf_token": player.csrf_token,
    }


def test_no_session_cookie_is_not_authenticated(client):
    response = client.get(f"{API}/users/me")

    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


def test_unknown_session_cookie_is_not_authenticated(client):
    put_session_cookie(client, "a-token-this-server-never-issued")

    response = client.get(f"{API}/users/me")

    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/games"),
        ("POST", "/games"),
        ("GET", "/games/3f2b8c1e-0000-4000-8000-000000000001"),
        ("POST", "/games/3f2b8c1e-0000-4000-8000-000000000001/players"),
        ("GET", "/games/3f2b8c1e-0000-4000-8000-000000000001/guesses"),
        ("POST", "/games/3f2b8c1e-0000-4000-8000-000000000001/guesses"),
        ("DELETE", "/sessions/current"),
    ],
)
def test_routes_that_need_a_sign_in_refuse_a_visitor(client, method, path):
    response = client.request(method, API + path, json={"word_guessed": "crane"})

    assert response.status_code == 401
    assert response.json() == NOT_AUTHENTICATED


def test_expired_session_is_refused_and_removed(player, db):
    from app.db import AuthSessionRow

    set_session_expiry(db, datetime.now(timezone.utc) - timedelta(seconds=1))

    response = player.get("/users/me")

    assert response.status_code == 401
    assert response.json() == {
        "code": "NOT_AUTHENTICATED",
        "detail": "Your sign-in has expired. Sign in again",
    }
    # the expired row is deleted, so the next attempt is simply an unknown session
    db.expire_all()
    assert db.query(AuthSessionRow).count() == 0
    assert player.get("/users/me").json() == NOT_AUTHENTICATED


def test_expired_session_cannot_change_anything(player, db):
    set_session_expiry(db, datetime.now(timezone.utc) - timedelta(days=1))

    response = player.post("/games", json={"word_length": 5})

    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"


def test_session_that_has_not_expired_yet_still_works(player, db):
    set_session_expiry(db, datetime.now(timezone.utc) + timedelta(minutes=1))

    assert player.get("/users/me").status_code == 200


# ---------- a sign-in is extended while the player keeps using it ----------


def session_expiry(db):
    from app.db import AuthSessionRow

    db.expire_all()
    return db.query(AuthSessionRow).one().expires_at


def test_session_used_after_a_day_is_extended_to_seven_days_from_now(player, db):
    # signed in two days ago: five of the seven days are left
    set_session_expiry(db, datetime.now(timezone.utc) + timedelta(days=5))

    response = player.get("/users/me")

    assert response.status_code == 200
    remaining = session_expiry(db) - datetime.now(timezone.utc)
    assert abs(remaining - timedelta(days=7)) < timedelta(seconds=5)
    # the browser's copy of the cookie is renewed to match
    assert "wordle_session=" in response.headers["set-cookie"]
    assert "Max-Age=604800" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_extended_session_keeps_the_same_token_and_csrf_token(player, db):
    token_before = player.session_token
    set_session_expiry(db, datetime.now(timezone.utc) + timedelta(days=5))

    body = player.get("/users/me").json()

    assert player.session_token == token_before
    assert body["csrf_token"] == player.csrf_token
    assert player.post("/games", json={"word_length": 5}).status_code == 201


def test_any_signed_in_request_extends_the_session(player, db):
    set_session_expiry(db, datetime.now(timezone.utc) + timedelta(days=3))

    player.get("/games")

    assert session_expiry(db) - datetime.now(timezone.utc) > timedelta(days=6, hours=23)


def session_cookies_set_by(response) -> list[str]:
    return [
        header
        for header in response.headers.get_list("set-cookie")
        if header.startswith("wordle_session=")
    ]


def test_cookie_is_renewed_even_when_the_request_that_extends_the_session_is_refused(player, db):
    # Otherwise the server would extend the sign-in while the browser's cookie kept its
    # old end date, and an active player could still be signed out on day seven.
    set_session_expiry(db, datetime.now(timezone.utc) + timedelta(days=3))

    response = player.post("/games", json={"word_length": 99})  # refused: no such length

    assert response.status_code == 422
    assert session_expiry(db) - datetime.now(timezone.utc) > timedelta(days=6, hours=23)
    [cookie] = session_cookies_set_by(response)
    assert "Max-Age=604800" in cookie
    assert "HttpOnly" in cookie


def test_logging_out_with_a_session_due_for_renewal_still_clears_the_cookie(player, db):
    set_session_expiry(db, datetime.now(timezone.utc) + timedelta(days=3))

    response = player.delete("/sessions/current")

    assert response.status_code == 204
    [cookie] = session_cookies_set_by(response)  # one instruction to the browser, not two
    assert "Max-Age=0" in cookie
    assert player.get("/users/me").status_code == 401


def test_session_used_again_within_a_day_is_left_alone(player, db):
    # extended (or created) twelve hours ago; no need to write to the database on every request
    almost_new = datetime.now(timezone.utc) + timedelta(days=6, hours=12)
    set_session_expiry(db, almost_new)

    response = player.get("/users/me")

    assert response.status_code == 200
    assert session_expiry(db) == almost_new
    assert "set-cookie" not in response.headers


def test_an_expired_session_is_not_brought_back(player, db):
    set_session_expiry(db, datetime.now(timezone.utc) - timedelta(seconds=1))

    assert player.get("/users/me").status_code == 401
    assert player.get("/users/me").status_code == 401


def test_new_session_lasts_seven_days(player, db):
    from app.db import AuthSessionRow

    session_row = db.query(AuthSessionRow).one()

    lifetime = session_row.expires_at - session_row.created_at
    assert abs(lifetime - timedelta(days=7)) < timedelta(seconds=5)


def test_logging_in_clears_out_that_users_expired_sessions(player, new_client, db):
    from app.db import AuthSessionRow

    # the sign-up session and one more, both long expired
    new_client().post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )
    set_session_expiry(db, datetime.now(timezone.utc) - timedelta(days=30))

    response = new_client().post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )

    assert response.status_code == 201
    db.expire_all()
    # only the session just created is left
    assert db.query(AuthSessionRow).count() == 1


def test_logging_in_keeps_sessions_that_are_still_valid(player, new_client, db):
    from app.db import AuthSessionRow

    new_client().post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )

    assert db.query(AuthSessionRow).count() == 2
    assert player.get("/users/me").status_code == 200


def test_logging_in_leaves_other_users_sessions_alone(player, other_player, new_client, db):
    from app.db import AuthSessionRow, UserRow

    set_session_expiry(db, datetime.now(timezone.utc) - timedelta(days=30))

    new_client().post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )

    db.expire_all()
    other = db.query(UserRow).filter_by(username=other_player.username).one()
    assert db.query(AuthSessionRow).filter_by(user_id=other.id).count() == 1


def test_signing_in_again_in_the_same_browser_ends_the_session_it_replaces(player, new_client):
    copy_of_old_session = player.in_another_browser(new_client())
    assert copy_of_old_session.get("/users/me").status_code == 200

    # the browser still holds the old cookie when it logs in again
    response = player.client.post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )

    assert response.status_code == 201
    assert player.client.get(f"{API}/users/me").status_code == 200  # the new session works
    assert copy_of_old_session.get("/users/me").status_code == 401  # the old one is gone


def test_signing_up_in_a_browser_that_is_signed_in_ends_that_session(player, new_client):
    copy_of_old_session = player.in_another_browser(new_client())

    response = player.client.post(
        f"{API}/users", json={"username": "second_account", "password": PASSWORD}
    )

    assert response.status_code == 201
    assert player.client.get(f"{API}/users/me").json()["user"]["username"] == "second_account"
    assert copy_of_old_session.get("/users/me").status_code == 401


def test_a_failed_log_in_does_not_end_the_session_already_in_the_browser(player):
    response = player.client.post(
        f"{API}/sessions", json={"username": player.username, "password": "wrong password"}
    )

    assert response.status_code == 401
    assert player.get("/users/me").status_code == 200


def test_logging_in_elsewhere_does_not_end_other_sessions(player, new_client):
    # a second device has no cookie to replace, so the first stays signed in
    second_device = new_client()
    second_device.post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )

    assert player.get("/users/me").status_code == 200


# ---------- log out ----------


def test_log_out_ends_the_session(player):
    response = player.delete("/sessions/current")

    assert response.status_code == 204
    assert response.content == b""
    assert player.get("/users/me").status_code == 401


def test_log_out_ends_the_session_on_the_server_not_just_the_cookie(player, new_client):
    # someone who copied the cookie while it was valid...
    copy = player.in_another_browser(new_client())
    assert copy.get("/users/me").status_code == 200

    player.delete("/sessions/current")

    # ...cannot keep using it once the player has logged out
    assert copy.get("/users/me").status_code == 401


def test_log_out_leaves_the_users_other_sessions_signed_in(player, client):
    second = client.post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )
    assert second.status_code == 201

    player.delete("/sessions/current")

    assert client.get(f"{API}/users/me").status_code == 200


def test_user_can_log_in_again_after_logging_out(player, client):
    player.delete("/sessions/current")

    response = client.post(
        f"{API}/sessions", json={"username": player.username, "password": player.password}
    )

    assert response.status_code == 201


# ---------- CSRF token ----------


def test_request_that_changes_something_without_a_csrf_token_is_refused(player):
    response = player.client.post(f"{API}/games", json={"word_length": 5})

    assert response.status_code == 403
    assert response.json() == {
        "code": "CSRF_CHECK_FAILED",
        "detail": "This request is missing its CSRF token",
    }
    assert player.get("/games").json()["items"] == []


def test_request_with_a_wrong_csrf_token_is_refused(player):
    response = player.client.post(
        f"{API}/games", json={"word_length": 5}, headers={CSRF_HEADER: "wrong"}
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": "CSRF_CHECK_FAILED",
        "detail": "This request's CSRF token is not valid",
    }


def test_log_out_without_a_csrf_token_is_refused_and_stays_signed_in(player):
    response = player.client.delete(f"{API}/sessions/current")

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"
    assert player.get("/users/me").status_code == 200


def test_reading_does_not_need_a_csrf_token(player):
    assert player.client.get(f"{API}/games").status_code == 200
