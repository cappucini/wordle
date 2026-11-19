"""CORS: which websites' pages may call this API from a browser and read the answer.

The session is a cookie, so this matters: a page on another site must not be able to read
a signed-in player's data (or their CSRF token) through the player's own browser.
"""

import pytest

from tests.support import API

FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

# Not the frontend, though several look like it. Each `id` says how that one differs.
OTHER_ORIGINS = [
    pytest.param("https://evil.example", id="another site"),
    pytest.param("http://localhost:3000", id="another port on localhost"),
    pytest.param("https://localhost:5173", id="the frontend's address over https"),
    pytest.param("http://localhost:5173.evil.example", id="the frontend's address as a prefix"),
    pytest.param("null", id="the null origin"),
]


def preflight(client, origin, method="POST"):
    """Sends the OPTIONS request a browser sends first, to ask whether a page on
    `origin` may make the real request."""
    return client.options(
        f"{API}/games",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )


@pytest.mark.parametrize("origin", FRONTEND_ORIGINS)
def test_frontend_origin_is_allowed_with_credentials(client, origin):
    response = preflight(client, origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-csrf-token" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("origin", OTHER_ORIGINS)
def test_other_origin_is_refused_at_preflight(client, origin):
    response = preflight(client, origin)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", OTHER_ORIGINS)
def test_other_origin_cannot_read_a_signed_in_players_data(player, origin):
    # the browser sends the request with the cookie, but without this header it will not
    # hand the response to the other site's page
    response = player.client.get(f"{API}/users/me", headers={"Origin": origin})

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", FRONTEND_ORIGINS)
def test_frontend_origin_can_read_responses(player, origin):
    response = player.client.get(f"{API}/users/me", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_allowed_origin_is_never_a_wildcard(client):
    # "*" together with credentials would let any site read a signed-in player's data
    for origin in FRONTEND_ORIGINS + ["https://evil.example"]:
        response = preflight(client, origin)
        assert response.headers.get("access-control-allow-origin") != "*"
