"""Requests the page never sends, and two things happening at the same instant.

Each test here guards a case that used to end in a server error (500), an error without
its `code`, or a connection left open after its sign-in had ended.
"""

from datetime import datetime, timedelta, timezone

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.support import API, CSRF_HEADER

GAME_UPDATED = {"type": "game_updated"}
NOT_AUTHENTICATED = 4401


# ---------- a CSRF token with characters outside plain English ----------


def test_csrf_token_with_an_accented_letter_is_refused_not_a_server_error(player):
    # sent as bytes: a header value travels as bytes, and the client would refuse to
    # encode the accented letter itself
    response = player.client.post(
        f"{API}/games",
        json={"word_length": 5},
        headers={CSRF_HEADER: "café".encode("latin-1")},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"


# ---------- errors raised by the framework, not by the game ----------


def test_unknown_address_is_reported_in_the_usual_error_shape(client):
    response = client.get(f"{API}/nope")

    assert response.status_code == 404
    assert response.json() == {"code": "NOT_FOUND", "detail": "Not Found"}


def test_wrong_method_is_reported_in_the_usual_error_shape(client):
    response = client.put(f"{API}/games")

    assert response.status_code == 405
    assert response.json() == {"code": "METHOD_NOT_ALLOWED", "detail": "Method Not Allowed"}
    # the standard header listing the methods the address does accept is kept
    assert "GET" in response.headers["allow"]


def test_body_that_is_not_readable_text_is_reported_in_the_usual_error_shape(player):
    response = player.client.post(
        f"{API}/games",
        # \xff is not valid UTF-8, so the body cannot be read as JSON at all
        content=b'{"word_length": "\xff"}',
        headers={**player.csrf, "Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


# ---------- the live connection ----------


def test_binary_data_on_the_live_connection_is_ignored(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    with player.watch(game["id"]) as socket:
        socket.send_bytes(b"\x00\x01")
        socket.send_text("hello")
        other_player.guess(game["id"], "slate")

        # the connection is still open and still told about the game
        assert socket.receive_json() == GAME_UPDATED


def test_live_connection_is_closed_if_its_sign_in_ended_while_it_was_opening(
    player, monkeypatch
):
    """Logging out at the instant a connection is being opened.

    The connection passes its sign-in check, the log-out then finds no connection to close,
    and only afterwards is the connection listed. It must not stay open.
    """
    from app import user_service
    from app.api.v1 import game_socket
    from app.db import SessionLocal
    from app.live import watchers
    from app.security import hash_token

    game = player.create_game()
    token = player.session_token
    real_check = game_socket._check_access

    def check_then_log_out(*args):
        """Runs the real check, then ends the sign-in before the connection is listed."""
        access = real_check(*args)
        with SessionLocal() as session:
            user_service.logout(session, token)
        watchers.close_session(hash_token(token))
        return access

    monkeypatch.setattr(game_socket, "_check_access", check_then_log_out)

    # the test client raises WebSocketDisconnect when the server closes the socket
    with pytest.raises(WebSocketDisconnect) as closed:
        with player.watch(game["id"]) as socket:
            socket.receive_json()

    assert closed.value.code == NOT_AUTHENTICATED
    assert watchers.count(game["id"]) == 0


# ---------- extending a sign-in that has just been logged out ----------


def test_extending_a_sign_in_that_was_logged_out_meanwhile_means_not_signed_in(player):
    """Two requests with the same cookie at once: one extends the sign-in, one logs it out.

    The first has already read the sign-in when the second deletes it. Saving the new
    expiry then finds no row; that must be reported as "not signed in", not as a crash.
    """
    from app import user_service
    from app.db import AuthSessionRow, SessionLocal
    from app.domain.errors import NotAuthenticated
    from app.security import hash_token

    token = player.session_token
    with SessionLocal() as first_request, SessionLocal() as second_request:
        auth_session = user_service.get_auth_session(first_request, token)
        # old enough to be due for extending: five days left of the seven
        auth_session.expires_at = datetime.now(timezone.utc) + timedelta(days=5)
        first_request.commit()

        user_service.logout(second_request, token)

        with pytest.raises(NotAuthenticated):
            user_service.renew_session_if_due(first_request, auth_session)
        # the database session can still be used afterwards: it was rolled back, not left broken
        assert first_request.get(AuthSessionRow, hash_token(token)) is None
