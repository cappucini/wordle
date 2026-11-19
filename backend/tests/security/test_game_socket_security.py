"""Who may open the live-update WebSocket, and what it gives away.

The route list test (test_route_protection.py) does not cover this route: WebSocket routes
are not in the OpenAPI description it reads, and they are refused with close codes rather
than HTTP statuses. So its rules are checked here.
"""

from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.support import API, put_session_cookie

# The codes a WebSocket is closed with. 4000 to 4999 are free for an application to
# use; these follow the HTTP statuses 401, 429, 403 and 404. 1008 is a standard code.
NOT_AUTHENTICATED = 4401
TOO_MANY_CONNECTIONS = 4429
NOT_A_PLAYER = 4403
GAME_NOT_FOUND = 4404
POLICY_VIOLATION = 1008


def close_code(connect) -> int:
    """Tries to open and read from the socket; returns the code it was closed with."""
    # the test client raises WebSocketDisconnect when the server closes the socket;
    # pytest.raises catches it and keeps it in `refused.value`
    with pytest.raises(WebSocketDisconnect) as refused:
        with connect() as socket:
            socket.receive_json()
    return refused.value.code


# ---------- signed in, and a player ----------


def test_visitor_who_is_not_signed_in_is_refused(player, client):
    game = player.create_game()

    # passed as a lambda, so that close_code is the one that opens the connection
    code = close_code(lambda: client.websocket_connect(f"{API}/games/{game['id']}/ws"))

    assert code == NOT_AUTHENTICATED


def test_made_up_session_cookie_is_refused(player, client):
    game = player.create_game()
    put_session_cookie(client, "x" * 43)

    code = close_code(lambda: client.websocket_connect(f"{API}/games/{game['id']}/ws"))

    assert code == NOT_AUTHENTICATED


def test_session_cookie_from_before_log_out_is_refused(player, new_client):
    game = player.create_game()
    copy = player.in_another_browser(new_client())
    player.delete("/sessions/current")

    assert close_code(lambda: copy.watch(game["id"])) == NOT_AUTHENTICATED


def test_expired_session_is_refused(player, db):
    from datetime import datetime, timedelta, timezone

    from app.db import AuthSessionRow

    game = player.create_game()
    # make every sign-in in the table end a second ago
    db.query(AuthSessionRow).update(
        {AuthSessionRow.expires_at: datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    db.commit()

    assert close_code(lambda: player.watch(game["id"])) == NOT_AUTHENTICATED


def test_signed_in_user_who_is_not_a_player_is_refused(player, other_player):
    game = player.create_game()

    assert close_code(lambda: other_player.watch(game["id"])) == NOT_A_PLAYER


def test_user_refused_from_a_full_game_cannot_watch_it_either(make_player):
    owner, second, third, fourth = (make_player() for _ in range(4))
    game = owner.create_game()
    second.join(game["id"])
    third.join(game["id"])
    fourth.join(game["id"])  # refused: the game is full

    assert close_code(lambda: fourth.watch(game["id"])) == NOT_A_PLAYER


def test_game_that_does_not_exist_is_refused(player):
    assert close_code(lambda: player.watch(str(uuid4()))) == GAME_NOT_FOUND


def test_game_id_that_is_not_a_uuid_is_refused(player):
    # any refusal will do: this test does not pin down the close code for a malformed id
    with pytest.raises(WebSocketDisconnect):
        with player.watch("not-a-uuid") as socket:
            socket.receive_json()


def test_outsider_is_not_told_about_guesses(player, other_player):
    from uuid import UUID

    from app.live import watchers

    game = player.create_game()

    close_code(lambda: other_player.watch(game["id"]))

    # a refused connection is never added to the game's watchers
    assert watchers.count(UUID(game["id"])) == 0


# ---------- a connection does not outlive its sign-in ----------


def test_logging_out_closes_the_players_open_connection(player, new_client):
    game = player.create_game()
    page = player.in_another_browser(new_client())  # the same sign-in, in another tab

    with pytest.raises(WebSocketDisconnect) as closed:
        with page.watch(game["id"]) as socket:
            player.delete("/sessions/current")
            socket.receive_json()

    assert closed.value.code == NOT_AUTHENTICATED


def test_logging_out_leaves_other_players_connected(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    with other_player.watch(game["id"]) as socket:
        player.delete("/sessions/current")
        other_player.guess(game["id"], "slate")

        assert socket.receive_json() == {"type": "game_updated"}


def test_connection_is_closed_once_its_session_has_expired(player, other_player, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.live import watchers

    game = player.create_game()
    other_player.join(game["id"])

    with pytest.raises(WebSocketDisconnect) as closed:
        with player.watch(game["id"]) as socket:
            # eight days pass; the sign-in lasted seven
            later = datetime.now(timezone.utc) + timedelta(days=8)
            monkeypatch.setattr(watchers, "now", lambda: later)
            other_player.guess(game["id"], "slate")
            socket.receive_json()

    assert closed.value.code == NOT_AUTHENTICATED


# ---------- how many connections one player may hold ----------


def test_a_player_can_hold_ten_connections_and_the_eleventh_is_refused(player):
    game = player.create_game()
    open_sockets = []
    # Ten sockets have to be open at the same time, so each `with` block is entered by
    # hand with __enter__() and left in the `finally` with __exit__().
    try:
        for _ in range(10):
            socket = player.watch(game["id"])
            socket.__enter__()
            open_sockets.append(socket)

        assert close_code(lambda: player.watch(game["id"])) == TOO_MANY_CONNECTIONS
    finally:
        for socket in open_sockets:
            socket.__exit__(None, None, None)

    # and once those are closed there is room again
    with player.watch(game["id"]):
        pass


def test_one_players_connections_do_not_use_up_another_players(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])
    open_sockets = []
    try:
        for _ in range(10):
            socket = player.watch(game["id"])
            socket.__enter__()
            open_sockets.append(socket)

        with other_player.watch(game["id"]):
            pass
    finally:
        for socket in open_sockets:
            socket.__exit__(None, None, None)


# ---------- which website is asking ----------


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
)
def test_the_frontends_own_pages_may_connect(player, other_player, origin):
    game = player.create_game()
    other_player.join(game["id"])

    with player.watch(game["id"], headers={"Origin": origin}) as socket:
        other_player.guess(game["id"], "slate")
        assert socket.receive_json() == {"type": "game_updated"}


@pytest.mark.parametrize(
    "origin",
    [
        pytest.param("https://evil.example", id="another site"),
        pytest.param("http://localhost:3000", id="another port on localhost"),
        pytest.param("https://localhost:5173", id="the frontend's address over https"),
        pytest.param("http://localhost:5173.evil.example", id="the frontend's address as a prefix"),
        pytest.param("null", id="the null origin"),
    ],
)
def test_a_page_on_another_site_cannot_connect_with_a_players_cookie(player, origin):
    # Browsers do not apply CORS to WebSockets and do send the cookie, so the server has
    # to turn these away itself. The player here is signed in and in the game.
    from uuid import UUID

    from app.live import watchers

    game = player.create_game()

    # refused while connecting, so there is nothing to read; if the connection were
    # accepted, no error would be raised and this fails straight away
    with pytest.raises(WebSocketDisconnect) as refused:
        with player.watch(game["id"], headers={"Origin": origin}):
            pass

    assert refused.value.code == POLICY_VIOLATION
    assert watchers.count(UUID(game["id"])) == 0


# ---------- what the socket gives away ----------


def test_the_socket_never_carries_the_answer_or_any_game_data(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    with player.watch(game["id"]) as socket:
        other_player.guess(game["id"], "slate")
        other_player.guess(game["id"], "crane")  # the winning guess

        # read as raw text, to check exactly what was sent and not only how it parses
        messages = [socket.receive_text(), socket.receive_text()]

    for message in messages:
        assert message == '{"type":"game_updated"}'


def test_messages_sent_by_the_page_are_ignored(player, other_player):
    game = player.create_game()
    other_player.join(game["id"])

    with player.watch(game["id"]) as socket:
        socket.send_text('{"type": "guess", "word_guessed": "crane"}')
        socket.send_text("'; DROP TABLE games; --")
        other_player.guess(game["id"], "slate")

        # still connected, and nothing the page sent did anything
        assert socket.receive_json() == {"type": "game_updated"}

    assert [guess["word"] for guess in player.game(game["id"])["guesses"]] == ["slate"]
