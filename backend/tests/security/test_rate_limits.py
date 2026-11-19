"""Limits on log-in and sign-up attempts, so passwords cannot be guessed without end.

The limits (see app/domain/rules.py):
  - 10 failed log-ins for one username in 5 minutes
  - 30 failed log-ins from one address in 5 minutes
  - 20 accounts created from one address in 5 minutes
"""

import pytest

from tests.support import API, PASSWORD

TOO_MANY = "TOO_MANY_ATTEMPTS"
FIVE_MINUTES = 5 * 60


@pytest.fixture
def clock(monkeypatch):
    """Lets a test move the limiters' clock forward instead of waiting five minutes."""
    from app.api.v1 import rate_limits

    class Clock:
        offset = 0.0

        def advance(self, seconds):
            self.offset += seconds

    moved = Clock()
    for limiter in rate_limits.ALL_LIMITERS:
        real = limiter.clock
        monkeypatch.setattr(limiter, "clock", lambda real=real: real() + moved.offset)
    return moved


def log_in(client, username, password=PASSWORD):
    return client.post(f"{API}/sessions", json={"username": username, "password": password})


def fail_to_log_in(client, username, times):
    for _ in range(times):
        response = log_in(client, username, "wrong password")
        assert response.status_code == 401, response.text


# ---------- failed log-ins for one username ----------


def test_ten_wrong_passwords_are_each_answered_normally(player, client):
    fail_to_log_in(client, player.username, 10)


def test_eleventh_attempt_is_refused_even_with_the_right_password(player, client):
    fail_to_log_in(client, player.username, 10)

    response = log_in(client, player.username, player.password)

    assert response.status_code == 429
    assert response.json()["code"] == TOO_MANY
    assert "set-cookie" not in response.headers
    assert client.get(f"{API}/users/me").status_code == 401


def test_refusal_says_when_to_try_again(player, client):
    fail_to_log_in(client, player.username, 10)

    response = log_in(client, player.username, "wrong password")

    assert response.json() == {
        "code": TOO_MANY,
        "detail": "Too many attempts. Try again in 5 minutes",
    }
    assert 0 < int(response.headers["retry-after"]) <= FIVE_MINUTES


def test_the_limit_is_per_username(player, other_player, client):
    fail_to_log_in(client, player.username, 10)

    assert log_in(client, other_player.username).status_code == 201


def test_someone_already_signed_in_is_not_signed_out_by_the_limit(player, client):
    fail_to_log_in(client, player.username, 10)

    # an attacker can stop new log-ins for five minutes, but not end the player's session
    assert player.get("/users/me").status_code == 200
    assert player.post("/games", json={"word_length": 5}).status_code == 201


def test_log_in_works_again_after_five_minutes(player, client, clock):
    fail_to_log_in(client, player.username, 10)
    assert log_in(client, player.username).status_code == 429

    clock.advance(FIVE_MINUTES)

    assert log_in(client, player.username).status_code == 201


def test_a_successful_log_in_wipes_the_count(player, client):
    fail_to_log_in(client, player.username, 9)
    assert log_in(client, player.username).status_code == 201

    # nine more mistakes are allowed again, not just one
    fail_to_log_in(client, player.username, 9)
    assert log_in(client, player.username).status_code == 201


def test_made_up_usernames_are_limited_the_same_way(client):
    # if only real usernames were limited, the limit would reveal which ones exist
    fail_to_log_in(client, "nobody_here", 10)

    response = log_in(client, "nobody_here", "wrong password")

    assert response.status_code == 429
    assert response.json()["code"] == TOO_MANY


def test_the_username_is_counted_whatever_its_capitals(player, client):
    fail_to_log_in(client, player.username.upper(), 5)
    fail_to_log_in(client, player.username, 5)

    assert log_in(client, player.username).status_code == 429


def test_requests_refused_for_their_shape_do_not_count(player, client):
    for _ in range(15):
        assert log_in(client, player.username, "short").status_code == 422

    assert log_in(client, player.username).status_code == 201


# ---------- failed log-ins from one address ----------


def test_thirty_failures_from_one_address_block_that_address(make_player, client):
    # spread over many usernames, so no single username reaches its own limit
    for number in range(30):
        fail_to_log_in(client, f"guess_{number}", 1)
    player = make_player()

    response = log_in(client, player.username)

    assert response.status_code == 429
    assert response.json()["code"] == TOO_MANY


def test_address_is_allowed_again_after_five_minutes(make_player, client, clock):
    for number in range(30):
        fail_to_log_in(client, f"guess_{number}", 1)
    player = make_player()

    clock.advance(FIVE_MINUTES)

    assert log_in(client, player.username).status_code == 201


# ---------- sign-ups from one address ----------


def sign_up(client_factory, username):
    return client_factory().post(
        f"{API}/users", json={"username": username, "password": PASSWORD}
    )


def test_twenty_accounts_can_be_created_from_one_address(new_client):
    for number in range(20):
        assert sign_up(new_client, f"new_user_{number}").status_code == 201


def test_twenty_first_account_is_refused(new_client, db):
    from app.db import UserRow

    for number in range(20):
        sign_up(new_client, f"new_user_{number}")

    response = sign_up(new_client, "one_too_many")

    assert response.status_code == 429
    assert response.json()["code"] == TOO_MANY
    assert 0 < int(response.headers["retry-after"]) <= FIVE_MINUTES
    assert db.query(UserRow).filter_by(username="one_too_many").count() == 0


def test_sign_ups_that_fail_do_not_count(new_client):
    sign_up(new_client, "erica")
    for _ in range(25):
        assert sign_up(new_client, "erica").status_code == 409  # username taken

    assert sign_up(new_client, "someone_new").status_code == 201


def test_sign_up_works_again_after_five_minutes(new_client, clock):
    for number in range(20):
        sign_up(new_client, f"new_user_{number}")

    clock.advance(FIVE_MINUTES)

    assert sign_up(new_client, "later_user").status_code == 201


def test_the_sign_up_limit_does_not_stop_people_logging_in(player, new_client):
    for number in range(19):  # the player fixture was the first of the twenty
        sign_up(new_client, f"new_user_{number}")
    assert sign_up(new_client, "one_too_many").status_code == 429

    assert log_in(new_client(), player.username).status_code == 201
