"""An unexpected crash inside a route: the client still gets an error it can read."""

import pytest

from tests.support import API

FRONTEND = "http://localhost:5173"


@pytest.fixture
def crashing_games_list(monkeypatch):
    """Makes GET /games hit a bug, the way an unforeseen error in production would."""
    from app import game_service

    def crash(*args, **kwargs):
        """Stands in for list_games: accepts any arguments and always raises.

        The message holds a made-up secret, so a test can check it never reaches the client.
        """
        raise RuntimeError("secret internal detail: db password is hunter2")

    # monkeypatch swaps the function in for this test only, and puts the real one back after
    monkeypatch.setattr(game_service, "list_games", crash)


def test_unexpected_crash_is_reported_in_the_usual_error_shape(player, crashing_games_list):
    response = player.get("/games")

    assert response.status_code == 500
    assert response.json() == {
        "code": "INTERNAL_ERROR",
        "detail": "Something went wrong on the server",
    }


def test_unexpected_crash_does_not_reveal_what_went_wrong(player, crashing_games_list):
    response = player.get("/games")

    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_unexpected_crash_can_still_be_read_by_the_frontend(player, crashing_games_list):
    # Without this header the browser hides the response from the page, and the page
    # wrongly reports that the server cannot be reached.
    response = player.client.get(f"{API}/games", headers={"Origin": FRONTEND})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert response.headers["access-control-allow-credentials"] == "true"


def test_server_keeps_working_after_a_crash(player, crashing_games_list):
    player.get("/games")

    assert player.get("/users/me").status_code == 200
    assert player.post("/games", json={"word_length": 5}).status_code == 201


def test_expected_errors_keep_their_own_codes(player):
    # the catch-all must not swallow the errors that already have a status and a code
    response = player.get("/games/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
