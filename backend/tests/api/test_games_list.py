"""The games list and its cursor pagination: GET /games."""

from datetime import datetime, timezone

import pytest

from tests.support import WRONG_5


def ids(games: list[dict]) -> list[str]:
    return [game["id"] for game in games]


def newest_first(games: list[dict]) -> list[str]:
    """The order the API promises: by created_at, then id, both descending."""
    return ids(
        sorted(games, key=lambda game: (game["created_at"], game["id"]), reverse=True)
    )


def all_pages(player, limit: int) -> list[list[dict]]:
    """Follows next_cursor from the first page to the last."""
    pages = []
    cursor = None
    for _ in range(50):  # a safety stop, far more pages than any test creates
        params = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        response = player.get("/games", params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        pages.append(body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages
    raise AssertionError("the cursor never ran out")


# ---------- what is listed ----------


def test_new_user_has_no_games(player):
    response = player.get("/games")

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_list_returns_your_games_in_full(player):
    game = player.create_game()
    player.guess(game["id"], "slate")

    response = player.get("/games")

    assert response.json() == {"items": [player.game(game["id"])], "next_cursor": None}


def test_list_is_newest_first(player):
    games = [player.create_game() for _ in range(4)]

    listed = player.get("/games").json()["items"]

    assert ids(listed) == newest_first(games)
    # the game created last is at the top
    assert listed[0]["id"] == games[-1]["id"]


def test_list_does_not_include_other_users_games(player, other_player):
    mine = player.create_game()
    other_player.create_game()

    assert ids(player.get("/games").json()["items"]) == [mine["id"]]


def test_list_includes_games_you_joined(player, other_player):
    theirs = other_player.create_game()
    player.join(theirs["id"])

    listed = player.get("/games").json()["items"]

    assert ids(listed) == [theirs["id"]]
    assert len(listed[0]["players"]) == 2


def test_list_reveals_the_answer_only_for_finished_games(player):
    won = player.create_game()
    player.guess(won["id"], "crane")
    lost = player.create_game()
    for word in WRONG_5:
        player.guess(lost["id"], word)
    in_progress = player.create_game()

    listed = {game["id"]: game for game in player.get("/games").json()["items"]}

    assert (listed[won["id"]]["status"], listed[won["id"]]["answer"]) == ("won", "crane")
    assert (listed[lost["id"]]["status"], listed[lost["id"]]["answer"]) == ("lost", "crane")
    assert (listed[in_progress["id"]]["status"], listed[in_progress["id"]]["answer"]) == (
        "in_progress",
        None,
    )


# ---------- pagination ----------


def test_pages_cover_every_game_once_in_order(player):
    games = [player.create_game() for _ in range(5)]

    pages = all_pages(player, limit=2)

    assert [len(page) for page in pages] == [2, 2, 1]
    assert ids([game for page in pages for game in page]) == newest_first(games)


def test_last_page_has_no_cursor_when_the_games_divide_evenly(player):
    for _ in range(4):
        player.create_game()

    pages = all_pages(player, limit=2)

    # two full pages, and no empty third page
    assert [len(page) for page in pages] == [2, 2]


def test_page_with_every_game_has_no_cursor(player):
    for _ in range(3):
        player.create_game()

    response = player.get("/games", params={"limit": 3})

    assert len(response.json()["items"]) == 3
    assert response.json()["next_cursor"] is None


def test_default_page_size_is_twenty(player):
    for _ in range(21):
        player.create_game()

    first = player.get("/games").json()

    assert len(first["items"]) == 20
    assert first["next_cursor"] is not None
    second = player.get("/games", params={"cursor": first["next_cursor"]}).json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None


def test_game_created_between_two_pages_is_not_repeated_or_skipped(player):
    games = [player.create_game() for _ in range(4)]
    first = player.get("/games", params={"limit": 2}).json()

    player.create_game()  # arrives at the top of the list after page one was read
    second = player.get("/games", params={"limit": 2, "cursor": first["next_cursor"]}).json()

    assert ids(first["items"]) + ids(second["items"]) == newest_first(games)


def test_games_created_at_the_same_instant_still_page_cleanly(player, db):
    from app.db import GameRow

    games = [player.create_game() for _ in range(5)]
    # give every game the same created_at, so only the id can order them
    same_instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db.query(GameRow).update({GameRow.created_at: same_instant})
    db.commit()

    pages = all_pages(player, limit=2)

    listed = ids([game for page in pages for game in page])
    assert listed == sorted(ids(games), reverse=True)


def test_cursor_only_pages_through_your_own_games(player, other_player):
    for _ in range(3):
        other_player.create_game()
    mine = player.create_game()
    their_cursor = other_player.get("/games", params={"limit": 1}).json()["next_cursor"]

    # using someone else's cursor moves your position; it does not show their games
    response = player.get("/games", params={"cursor": their_cursor})

    assert response.status_code == 200
    assert set(ids(response.json()["items"])) <= {mine["id"]}


@pytest.mark.parametrize(
    "cursor", ["not-a-cursor", "abc", "", "bm8gc2VwYXJhdG9y"]  # the last is "no separator"
)
def test_invalid_cursor_is_refused(player, cursor):
    response = player.get("/games", params={"cursor": cursor})

    assert response.status_code == 422
    assert response.json() == {"code": "INVALID_CURSOR", "detail": "The cursor is not valid"}


@pytest.mark.parametrize("limit", [1, 100])
def test_limit_within_bounds_is_accepted(player, limit):
    player.create_game()

    assert player.get("/games", params={"limit": limit}).status_code == 200


@pytest.mark.parametrize("limit", [0, -1, 101, "many"])
def test_limit_outside_bounds_is_refused(player, limit):
    response = player.get("/games", params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["detail"].startswith("limit: ")
