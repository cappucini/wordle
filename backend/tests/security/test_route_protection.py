"""Every route is checked for a sign-in, and every route that changes something for a CSRF token.

The list of routes is read from the application itself, so a route added later is tested
without anyone remembering to add it here. A new route that should be open to visitors
must be added to PUBLIC_ROUTES below, which makes that a deliberate decision.
"""

from uuid import uuid4

import pytest
from main import app
from tests.support import CSRF_HEADER, put_session_cookie

# Routes a visitor may call without signing in.
PUBLIC_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/api/v1/config"),
    ("POST", "/api/v1/users"),  # sign up
    ("POST", "/api/v1/sessions"),  # log in
}

CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Read from the OpenAPI description FastAPI generates (the same list /docs shows),
# which covers every route however it was registered.
ALL_ROUTES = sorted(
    (method.upper(), path)
    for path, operations in app.openapi()["paths"].items()
    for method in operations
)
PROTECTED_ROUTES = [route for route in ALL_ROUTES if route not in PUBLIC_ROUTES]
PROTECTED_CHANGING_ROUTES = [
    route for route in PROTECTED_ROUTES if route[0] in CHANGING_METHODS
]

# a body that satisfies every route that takes one, so a refusal is about who is asking
# and not about the shape of the request
BODY = {"word_guessed": "crane"}


def fill(path: str) -> str:
    return path.replace("{game_id}", str(uuid4()))


def test_the_route_table_was_read():
    # guards the tests below against silently running on an empty list
    assert len(ALL_ROUTES) >= 12
    assert PUBLIC_ROUTES <= set(ALL_ROUTES)
    assert ("POST", "/api/v1/games/{game_id}/guesses") in PROTECTED_CHANGING_ROUTES


@pytest.mark.parametrize("method, path", PROTECTED_ROUTES)
def test_route_refuses_a_visitor_who_is_not_signed_in(client, method, path):
    response = client.request(method, fill(path), json=BODY)

    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"


@pytest.mark.parametrize("method, path", PROTECTED_ROUTES)
def test_route_refuses_a_made_up_session_cookie(client, method, path):
    put_session_cookie(client, "x" * 43)

    response = client.request(method, fill(path), json=BODY)

    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"


@pytest.mark.parametrize("method, path", sorted(PUBLIC_ROUTES))
def test_public_route_does_not_ask_for_a_sign_in(client, method, path):
    response = client.request(method, path, json={"username": "nobody", "password": "x"})

    assert response.json().get("code") != "NOT_AUTHENTICATED"


@pytest.mark.parametrize("method, path", PROTECTED_CHANGING_ROUTES)
def test_changing_route_refuses_a_request_without_a_csrf_token(player, method, path):
    response = player.client.request(method, fill(path), json=BODY)

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"


@pytest.mark.parametrize("method, path", PROTECTED_CHANGING_ROUTES)
@pytest.mark.parametrize("token", ["", "wrong", "x" * 43])
def test_changing_route_refuses_a_wrong_csrf_token(player, method, path, token):
    response = player.client.request(
        method, fill(path), json=BODY, headers={CSRF_HEADER: token}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"


@pytest.mark.parametrize("method, path", PROTECTED_CHANGING_ROUTES)
def test_changing_route_refuses_another_users_csrf_token(player, other_player, method, path):
    # a CSRF token belongs to one session; a valid token from someone else is not enough
    response = player.client.request(
        method, fill(path), json=BODY, headers=other_player.csrf
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"


def test_csrf_token_from_an_earlier_session_stops_working_after_log_out(player, client):
    old_token = player.csrf_token
    player.delete("/sessions/current")
    again = client.post(
        "/api/v1/sessions", json={"username": player.username, "password": player.password}
    )
    assert again.status_code == 201

    response = client.post(
        "/api/v1/games", json={"word_length": 5}, headers={CSRF_HEADER: old_token}
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_CHECK_FAILED"
