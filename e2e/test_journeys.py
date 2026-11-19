"""End-to-end tests: one per user journey, in a real browser against the real frontend
and backend. Edge cases belong in the faster layers; these check the pieces work together.

Every test creates its own users and games, so they can run in any order.
The answer to every 5-letter game is "crane" (see backend/tests/words/).
"""

from conftest import ANSWER, FRONTEND_URL, WRONG_GUESSES


def test_sign_up_then_log_out_and_log_back_in(visitor):
    visitor.open()
    visitor.auth.wait_until_shown()

    visitor.auth.create_account(visitor.username, visitor.password)
    visitor.game.wait_until_signed_in_as(visitor.username)

    visitor.game.sign_out()
    visitor.auth.wait_until_shown()
    assert visitor.game.signed_in_as() is None

    visitor.auth.sign_in(visitor.username, visitor.password)
    visitor.game.wait_until_signed_in_as(visitor.username)
    assert not visitor.auth.is_shown()


def test_play_a_game_to_a_win(visitor):
    visitor.sign_up()
    game = visitor.game.start_new_game(word_length=5)
    assert len(game.rows()) == 6

    game.guess("slate")
    assert game.results_of_guess(1) == ["absent", "absent", "correct", "absent", "correct"]
    assert game.result_banner() == ""

    game.guess(ANSWER)

    assert game.wait_for_result_banner() == "You got it in 2 guesses!"
    assert game.results_of_guess(2) == ["correct"] * 5
    assert game.guesses() == ["slate", "crane"]
    assert game.keyboard_is_disabled()
    game.wait_until(
        lambda: game.listed_games() == ["5 letters won 2 of 6 guesses"],
        '"Your games" shows the game as won',
    )


def test_play_a_game_to_a_loss(visitor):
    visitor.sign_up()
    game = visitor.game.start_new_game(word_length=5)

    for word in WRONG_GUESSES:
        assert game.result_banner() == ""  # the answer is not shown before the last guess
        game.guess(word)

    # the page shows the answer in capitals; that is styling, so compare without case
    banner = game.wait_for_result_banner()
    assert banner.lower() == f"out of guesses. the word was {ANSWER}."
    assert game.guesses() == WRONG_GUESSES
    assert game.keyboard_is_disabled()
    game.wait_until(
        lambda: game.listed_games() == ["5 letters lost 6 of 6 guesses"],
        '"Your games" shows the game as lost',
    )


def test_an_invalid_guess_shows_its_message_and_does_not_use_a_turn(visitor):
    visitor.sign_up()
    game = visitor.game.start_new_game(word_length=5)

    game.type_word("zzzzz")
    game.press_enter()

    assert game.wait_for_status_message() == "'zzzzz' is not in the word list"
    # the letters stay in the row to be corrected, and no guess was recorded
    assert game.letters_being_typed() == "zzzzz"
    assert game.guesses() == []
    assert game.result_banner() == ""


def test_two_players_share_a_game_and_each_sees_the_others_guess(new_visitor):
    owner = new_visitor().sign_up()
    owner.game.start_new_game(word_length=5)
    invite_link = owner.game.invite_link()

    # the friend opens the invite link before having an account
    friend = new_visitor().open(invite_link)
    friend.auth.wait_until_shown()
    assert friend.auth.has_invite_notice()
    friend.auth.create_account(friend.username, friend.password)
    friend.game.wait_until_signed_in_as(friend.username)
    friend.game.wait_until_board_is_shown()
    assert friend.game.players() == [owner.username, f"{friend.username} (you)"]

    # the owner's page learns about the friend without a refresh
    owner.game.wait_until_player_count_is(2)
    assert owner.game.players() == [f"{owner.username} (you)", friend.username]

    # the owner guesses; the friend sees it, with the owner's name beside it
    owner.game.guess("slate")
    friend.game.wait_until_guess_count_is(1)
    assert friend.game.guesses() == ["slate"]
    assert friend.game.results_of_guess(1) == ["absent", "absent", "correct", "absent", "correct"]
    assert friend.game.guesser_names() == [owner.username]

    # the friend guesses; the owner sees it, with the friend's name beside it
    friend.game.guess("react")
    owner.game.wait_until_guess_count_is(2)
    assert owner.game.guesses() == ["slate", "react"]
    assert owner.game.guesser_names() == [owner.username, friend.username]


def test_a_refresh_keeps_you_signed_in_and_in_your_game(visitor):
    visitor.sign_up()
    game = visitor.game.start_new_game(word_length=5)
    game.guess("slate")
    address = visitor.driver.current_url

    visitor.driver.refresh()

    game.wait_until_signed_in_as(visitor.username)
    game.wait_until_board_is_shown()
    assert visitor.driver.current_url == address
    assert game.guesses() == ["slate"]
    # and the page can still make changes, which needs the CSRF token it lost in the refresh
    game.guess("react")
    assert game.guesses() == ["slate", "react"]


def test_a_full_game_turns_away_a_fourth_player(visitor, new_api_player):
    # three players fill the game; they are created through the API because how they
    # joined is not what this test is about
    owner, second, third = new_api_player(), new_api_player(), new_api_player()
    game_id = owner.create_game()
    second.join(game_id)
    third.join(game_id)

    # the fourth arrives through the invite link, in the browser
    visitor.sign_up(f"{FRONTEND_URL}/?game={game_id}")

    message = visitor.game.wait_for_status_message()
    assert message == "That game already has the maximum number of players."
    assert not visitor.game.has_board()
    assert visitor.game.players() == []
    # the dead link is taken out of the address bar, and the game is not in their list
    assert "game=" not in visitor.driver.current_url
    assert visitor.game.listed_games() == []
