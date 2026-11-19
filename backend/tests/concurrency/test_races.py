"""Requests that arrive at the same instant.

Each test lines up several requests, releases them together, and then checks the end state:
the player limit, the guess limit and unique usernames must hold however the requests
happen to interleave.

A race cannot be forced to happen in one particular order, so each test repeats its race
for several rounds. With correct code every round passes. If a lock is removed, a round
fails whenever two requests really do overlap, which the repetition makes very likely.
"""

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from tests.support import API, PASSWORD, WRONG_5

ROUNDS = 5


def at_the_same_time(actions):
    """Runs every action on its own thread, all released at the same moment.

    Returns their results in the order given. An error inside any action (including a
    crash in the server, which the test client re-raises) fails the test.
    """
    start = threading.Barrier(len(actions))

    def run(action):
        start.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        futures = [pool.submit(run, action) for action in actions]
        return [future.result(timeout=30) for future in futures]


def statuses(responses) -> Counter:
    return Counter(response.status_code for response in responses)


def codes(responses, status: int) -> set:
    return {response.json()["code"] for response in responses if response.status_code == status}


# ---------- joining ----------


def test_many_players_joining_at_once_never_exceed_the_player_limit(make_player):
    owner = make_player()
    joiners = [make_player() for _ in range(8)]

    for _ in range(ROUNDS):
        game = owner.create_game()

        responses = at_the_same_time(
            [lambda joiner=joiner: joiner.join(game["id"]) for joiner in joiners]
        )

        # the owner plus exactly two of the eight; everyone else is told the game is full
        assert statuses(responses) == {200: 2, 409: 6}
        assert codes(responses, 409) == {"GAME_FULL"}
        players = owner.game(game["id"])["players"]
        assert len(players) == 3
        assert len({player["id"] for player in players}) == 3


def test_one_player_joining_from_several_tabs_at_once_joins_once(make_player, new_client):
    owner = make_player()
    joiner = make_player()
    tabs = [joiner.in_another_browser(new_client()) for _ in range(6)]

    for _ in range(ROUNDS):
        game = owner.create_game()

        responses = at_the_same_time([lambda tab=tab: tab.join(game["id"]) for tab in tabs])

        assert statuses(responses) == {200: 6}
        players = owner.game(game["id"])["players"]
        assert [player["id"] for player in players] == [owner.id, joiner.id]


# ---------- guessing ----------


def test_guesses_at_once_never_exceed_the_guess_limit(make_player, new_client):
    owner, second, third = make_player(), make_player(), make_player()
    # three players, four tabs each: twelve guesses for a game that allows six
    tabs = [
        player.in_another_browser(new_client())
        for player in (owner, second, third)
        for _ in range(4)
    ]

    for _ in range(ROUNDS):
        game = owner.create_game()
        second.join(game["id"])
        third.join(game["id"])

        responses = at_the_same_time(
            [
                lambda tab=tab, word=WRONG_5[index % 6]: tab.guess(game["id"], word)
                for index, tab in enumerate(tabs)
            ]
        )

        assert statuses(responses) == {201: 6, 409: 6}
        assert codes(responses, 409) == {"GAME_OVER"}
        accepted = [response.json() for response in responses if response.status_code == 201]
        # numbered 1 to 6 with no gaps or repeats, and only the sixth ends the game
        assert sorted(guess["number"] for guess in accepted) == [1, 2, 3, 4, 5, 6]
        assert Counter(guess["game_status"] for guess in accepted) == {
            "in_progress": 5,
            "lost": 1,
        }
        assert next(g for g in accepted if g["number"] == 6)["game_status"] == "lost"

        final = owner.game(game["id"])
        assert final["status"] == "lost"
        assert [guess["number"] for guess in final["guesses"]] == [1, 2, 3, 4, 5, 6]
        assert final["guesses_remaining"] == 0


def test_guesses_at_once_on_the_last_turn_only_one_is_accepted(make_player, new_client):
    owner, second, third = make_player(), make_player(), make_player()
    tabs = [
        player.in_another_browser(new_client())
        for player in (owner, second, third)
        for _ in range(2)
    ]

    for _ in range(ROUNDS):
        game = owner.create_game()
        second.join(game["id"])
        third.join(game["id"])
        for word in WRONG_5[:5]:
            owner.guess(game["id"], word)

        responses = at_the_same_time(
            [lambda tab=tab: tab.guess(game["id"], "moist") for tab in tabs]
        )

        assert statuses(responses) == {201: 1, 409: 5}
        accepted = next(r.json() for r in responses if r.status_code == 201)
        assert (accepted["number"], accepted["game_status"]) == (6, "lost")
        assert len(owner.game(game["id"])["guesses"]) == 6


def test_winning_guesses_at_once_only_one_wins(make_player, new_client):
    owner, second, third = make_player(), make_player(), make_player()
    tabs = [
        player.in_another_browser(new_client())
        for player in (owner, second, third)
        for _ in range(2)
    ]

    for _ in range(ROUNDS):
        game = owner.create_game()
        second.join(game["id"])
        third.join(game["id"])

        responses = at_the_same_time(
            [lambda tab=tab: tab.guess(game["id"], "crane") for tab in tabs]
        )

        assert statuses(responses) == {201: 1, 409: 5}
        assert codes(responses, 409) == {"GAME_OVER"}
        final = owner.game(game["id"])
        assert final["status"] == "won"
        assert len(final["guesses"]) == 1


# ---------- accounts ----------


def test_same_username_signed_up_at_once_creates_one_account(new_client, db):
    from app.db import UserRow

    for round_number in range(ROUNDS):
        username = f"contested_{round_number}"
        browsers = [new_client() for _ in range(6)]

        responses = at_the_same_time(
            [
                lambda browser=browser: browser.post(
                    f"{API}/users", json={"username": username, "password": PASSWORD}
                )
                for browser in browsers
            ]
        )

        assert statuses(responses) == {201: 1, 409: 5}
        assert codes(responses, 409) == {"USERNAME_TAKEN"}
        db.expire_all()
        assert db.query(UserRow).filter_by(username=username).count() == 1
        # the winner is signed in; the others are not
        signed_in = [b for b in browsers if b.get(f"{API}/users/me").status_code == 200]
        assert len(signed_in) == 1


def test_one_user_logging_in_from_several_browsers_at_once(player, new_client):
    browsers = [new_client() for _ in range(6)]

    responses = at_the_same_time(
        [
            lambda browser=browser: browser.post(
                f"{API}/sessions",
                json={"username": player.username, "password": player.password},
            )
            for browser in browsers
        ]
    )

    assert statuses(responses) == {201: 6}
    assert len({response.json()["csrf_token"] for response in responses}) == 6
    for browser in browsers:
        assert browser.get(f"{API}/users/me").json()["user"]["id"] == player.id


# ---------- creating games ----------


def test_games_created_at_once_are_all_created(player, new_client):
    tabs = [player.in_another_browser(new_client()) for _ in range(8)]

    responses = at_the_same_time(
        [lambda tab=tab: tab.post("/games", json={"word_length": 5}) for tab in tabs]
    )

    assert statuses(responses) == {201: 8}
    created = {response.json()["id"] for response in responses}
    assert len(created) == 8
    listed = player.get("/games").json()["items"]
    assert {game["id"] for game in listed} == created
    # the list's order is still well defined when games are created together
    assert listed == sorted(
        listed, key=lambda game: (game["created_at"], game["id"]), reverse=True
    )
