"""Who may see or change a game, and the answer staying secret until the game is over."""

import pytest

from tests.support import ANSWERS, NOT_A_WORD, WRONG_5

ANSWER = ANSWERS[5]


# ---------- a game belongs to its players ----------


@pytest.mark.parametrize(
    "request_as_outsider",
    [
        pytest.param(lambda outsider, game_id: outsider.get(f"/games/{game_id}"), id="read the game"),
        pytest.param(
            lambda outsider, game_id: outsider.get(f"/games/{game_id}/guesses"),
            id="read its guesses",
        ),
        pytest.param(lambda outsider, game_id: outsider.guess(game_id, "react"), id="guess in it"),
    ],
)
def test_outsider_gets_nothing_from_a_game_they_have_not_joined(
    player, other_player, request_as_outsider
):
    game = player.create_game()
    player.guess(game["id"], "slate")

    response = request_as_outsider(other_player, game["id"])

    assert response.status_code == 403
    assert response.json()["code"] == "NOT_A_PLAYER"
    # the refusal says nothing about the game: not its guesses, players or answer
    assert "slate" not in response.text
    assert player.username not in response.text
    assert ANSWER not in response.text
    # and nothing changed
    assert [guess["word"] for guess in player.game(game["id"])["guesses"]] == ["slate"]


def test_being_refused_from_a_full_game_reveals_nothing_about_it(make_player):
    owner, second, third, outsider = (make_player() for _ in range(4))
    game = owner.create_game()
    second.join(game["id"])
    third.join(game["id"])
    owner.guess(game["id"], "slate")

    response = outsider.join(game["id"])

    assert response.status_code == 409
    assert set(response.json()) == {"code", "detail"}
    assert "slate" not in response.text
    assert owner.username not in response.text


def test_games_list_never_shows_another_users_game(player, other_player):
    for _ in range(3):
        other_player.create_game()

    assert player.get("/games").json()["items"] == []
    assert player.get("/games", params={"limit": 100}).json()["items"] == []


@pytest.mark.parametrize(
    "extra", [{"user_id": "x"}, {"guessed_by": "someone_else"}, {"number": 99}]
)
def test_a_guess_cannot_be_attributed_to_someone_else(player, other_player, extra):
    game = player.create_game()
    other_player.join(game["id"])
    extra = {key: other_player.id if value == "x" else value for key, value in extra.items()}

    response = player.post(
        f"/games/{game['id']}/guesses", json={"word_guessed": "slate", **extra}
    )

    # unknown fields are refused outright; who guessed comes from the session, nothing else
    assert response.status_code == 422
    assert player.game(game["id"])["guesses"] == []


def test_a_game_cannot_be_created_in_someone_elses_name(player, other_player):
    response = player.post("/games", json={"word_length": 5, "owner_id": other_player.id})

    assert response.status_code == 422
    assert other_player.get("/games").json()["items"] == []


# ---------- the answer stays secret while a game is in progress ----------


def assert_answer_is_hidden(response):
    assert response.status_code < 400, response.text
    assert ANSWER not in response.text, f"the answer leaked in: {response.text}"


def test_no_response_reveals_the_answer_before_the_game_ends(player, other_player):
    created = player.post("/games", json={"word_length": 5})
    assert_answer_is_hidden(created)
    game_id = created.json()["id"]

    assert_answer_is_hidden(other_player.join(game_id))

    # every guess but the last, alternating between the two players
    for index, word in enumerate(WRONG_5[:-1]):
        guesser = player if index % 2 == 0 else other_player
        assert_answer_is_hidden(guesser.guess(game_id, word))
        assert_answer_is_hidden(player.get(f"/games/{game_id}"))
        assert_answer_is_hidden(other_player.get(f"/games/{game_id}"))
        assert_answer_is_hidden(player.get(f"/games/{game_id}/guesses"))
        assert_answer_is_hidden(player.get("/games"))
        assert_answer_is_hidden(other_player.get("/games"))

    # one turn left, and it is still hidden
    assert player.game(game_id)["guesses_remaining"] == 1
    assert player.game(game_id)["answer"] is None


@pytest.mark.parametrize(
    "bad_guess",
    [NOT_A_WORD, "planet", "cran", "cran3"],
    ids=["not a word", "wrong length for the game", "too short", "has a digit"],
)
def test_error_responses_do_not_reveal_the_answer(player, bad_guess):
    game = player.create_game()

    response = player.guess(game["id"], bad_guess)

    assert response.status_code == 422
    assert ANSWER not in response.text


def test_the_answer_is_revealed_only_to_the_games_players(player, other_player):
    game = player.create_game()
    player.guess(game["id"], ANSWER)

    assert player.game(game["id"])["answer"] == ANSWER
    outsider_view = other_player.get(f"/games/{game['id']}")
    assert outsider_view.status_code == 403
    assert ANSWER not in outsider_view.text
