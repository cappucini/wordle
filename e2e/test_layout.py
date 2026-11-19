"""Layout checks: things that only go wrong on a real screen.

The journeys in test_journeys.py check that the game works. These check that it fits: at
desktop, small-laptop and phone widths, nothing runs off the page, overlaps its neighbour
or ends up where the player cannot see it. Each test here guards a bug that was found by
looking at the page and that no other layer of tests can see, because the cause is in CSS.

Sizes are (width, height) of the browser window in pixels.
"""

import uuid

import pytest

from conftest import ANSWER, FRONTEND_URL, WRONG_GUESSES
from pages.game_page import Box

DESKTOP = (1280, 800)
SMALL_LAPTOP = (1100, 800)
PHONE = (390, 844)
SMALL_PHONE = (320, 640)

# a valid 8-letter guess that is not the answer (see backend/tests/words/)
WRONG_8 = "notebook"


def long_username() -> str:
    """Twenty characters, the longest a username can be, and different every time."""
    return "x" + uuid.uuid4().hex[:19]


def resize(visitor, size) -> None:
    """Sets the visitor's browser window to a (width, height) size."""
    # the * unpacks the pair into the two arguments set_window_size takes
    visitor.driver.set_window_size(*size)


# parametrize runs the test once for each size in the list
@pytest.mark.parametrize("size", [DESKTOP, SMALL_LAPTOP, PHONE, SMALL_PHONE])
def test_nothing_sticks_out_sideways(visitor, size):
    resize(visitor, size)

    visitor.open()
    visitor.auth.wait_until_shown()
    assert visitor.game.sideways_overflow() == 0, "the sign-in page is wider than the window"

    visitor.auth.create_account(visitor.username, visitor.password)
    visitor.game.wait_until_signed_in_as(visitor.username)
    assert visitor.game.sideways_overflow() == 0, "the empty game screen is wider than the window"

    game = visitor.game.start_new_game(word_length=8)
    game.guess(WRONG_8)
    assert game.sideways_overflow() == 0, "the game screen is wider than the window"


def test_the_board_is_on_screen_for_a_player_with_many_games(visitor):
    # "Your games" sits above the board on a wide screen. Left to grow it pushed the board
    # off the bottom; it now scrolls inside its own panel.
    resize(visitor, DESKTOP)
    visitor.sign_up()
    game = visitor.game
    for _ in range(12):
        game.start_new_game(word_length=5)
    game.wait_until(lambda: len(game.listed_games()) == 10, "ten games are listed")

    _, window_height = game.window_size()
    board = game.board_box()
    # a 5-letter board has six rows
    one_tile = board.height / 6

    assert board.top + one_tile <= window_height, (
        f"the first row of the board is below the window: {board}, window is {window_height}px tall"
    )
    scroll = game.games_list_scroll()
    assert scroll["holds"] > scroll["shows"], "the games list should scroll inside its panel"


def test_the_open_game_stays_in_view_in_a_long_games_list(visitor):
    resize(visitor, DESKTOP)
    visitor.sign_up()
    game = visitor.game
    for _ in range(10):
        game.start_new_game(word_length=5)
    game.wait_until(lambda: len(game.listed_games()) == 10, "ten games are listed")
    address_of_newest = visitor.driver.current_url

    game.open_listed_game(9)  # the oldest: the last row, out of sight until scrolled to
    game.wait_until(lambda: visitor.driver.current_url != address_of_newest, "another game is open")
    game.wait_until(lambda: game.games_list_scroll()["open_game_in_view"], "the open game is in view")

    # and coming back to it by reloading the page finds it in view too
    visitor.driver.refresh()
    game.wait_until_board_is_shown()
    game.wait_until(lambda: len(game.listed_games()) == 10, "ten games are listed")
    game.wait_until(lambda: game.games_list_scroll()["open_game_in_view"], "the open game is in view")


def test_small_boards_are_drawn_in_squares_and_never_change_a_rows_height(visitor):
    resize(visitor, DESKTOP)
    visitor.sign_up()
    game = visitor.game

    game.start_new_game(word_length=8)  # the longest game there is: nine guesses of eight
    for _ in range(9):
        game.guess(WRONG_8)
    game.wait_for_result_banner()

    game.start_new_game(word_length=5)  # an ordinary lost game: six guesses of five
    for word in WRONG_GUESSES:
        game.guess(word)
    game.wait_for_result_banner()

    game.start_new_game(word_length=5)  # won on the first guess
    game.guess(ANSWER)
    game.wait_for_result_banner()

    game.start_new_game(word_length=6)  # not started
    game.wait_until(lambda: len(game.listed_games()) == 4, "four games are listed")

    for size in (DESKTOP, PHONE):
        resize(visitor, size)
        boards = game.small_boards()

        # newest first: not started, won in one guess (1 x 5), lost (6 x 5), lost (9 x 8)
        assert [board["squares"] for board in boards] == [0, 5, 30, 72]
        # a set drops repeats, so one value left means every row is the same height
        assert len({board["row_height"] for board in boards}) == 1, (
            f"at {size}, rows differ in height: {[board['row_height'] for board in boards]}"
        )
        for board in boards:
            if board["squares"] == 0:
                continue
            assert board["all_inside"], f"at {size}, squares spill out of their box: {board}"
            assert len(board["widths"]) == 1 and board["widths"] == board["heights"], (
                f"at {size}, squares are not square: {board}"
            )
            assert board["widths"][0] == int(board["widths"][0]), (
                f"at {size}, squares are not a whole number of pixels: {board}"
            )


def test_the_rules_panel_opens_where_the_player_is_looking(visitor):
    resize(visitor, DESKTOP)
    visitor.sign_up()
    game = visitor.game.start_new_game(word_length=8)
    game.guess(WRONG_8)

    scrolled = game.scroll_to_bottom()
    assert scrolled > 0, "this test needs a page tall enough to scroll"
    game.open_rules_with_shortcut()

    width, height = game.window_size()
    panel = game.rules_panel_box()
    assert panel.is_inside(Box(0, 0, width, height)), f"the panel is partly off screen: {panel}"

    game.close_rules()


@pytest.mark.parametrize("size", [DESKTOP, (1200, 800), SMALL_LAPTOP])
def test_keys_stay_usable_beside_the_widest_board(new_visitor, new_api_player, size):
    # the widest the board gets: eight letters, with a long name beside each guess
    visitor = new_visitor()
    visitor.username = long_username()
    resize(visitor, size)
    visitor.sign_up()
    game = visitor.game.start_new_game(word_length=8)
    # the game's id is what follows "game=" in the address bar
    new_api_player().join(visitor.driver.current_url.split("game=")[1])
    game.guess(WRONG_8)
    game.wait_until_player_count_is(2)

    assert game.key_box("q").width >= 28, f"letter keys are too narrow to press: {game.key_box('q')}"
    assert game.key_label_fits("Enter"), "the word Enter does not fit on its key"


def test_a_failed_copy_keeps_its_message_inside_the_players_panel(visitor):
    resize(visitor, DESKTOP)
    visitor.sign_up()
    game = visitor.game.start_new_game(word_length=5)
    game.make_copying_fail()

    game.button("Copy invite link").click()
    game.wait_until(lambda: game.has_text("Couldn't copy"), "the failure message is shown")

    panel, button = game.players_panel_box(), game.copy_link_button_box()
    assert button.right <= panel.right + 1, f"the message runs past its panel: {button} in {panel}"


@pytest.mark.parametrize("size", [PHONE, SMALL_PHONE])
def test_a_long_name_does_not_run_into_the_title_on_a_phone(new_visitor, size):
    visitor = new_visitor()
    visitor.username = long_username()
    resize(visitor, DESKTOP)  # sign up at a comfortable size, then shrink
    visitor.sign_up()

    resize(visitor, size)

    title, name = visitor.game.title_box(), visitor.game.signed_in_name_box()
    assert name.left >= title.right, f"the name overlaps the title: name {name}, title {title}"
    assert visitor.game.sideways_overflow() == 0


@pytest.mark.parametrize("size", [PHONE, SMALL_PHONE])
def test_the_sign_in_form_is_on_screen_without_scrolling_on_a_phone(visitor, size):
    resize(visitor, size)

    visitor.open()
    visitor.auth.wait_until_shown()

    button, height = visitor.auth.submit_button_box(), visitor.auth.window_height()
    assert button.bottom <= height, f"the Sign in button is below the fold: {button}, window {height} tall"
    # the explanation is still there, under the form
    assert visitor.auth.explanation_box().top >= visitor.auth.form_box().bottom


def test_the_explanation_sits_beside_the_sign_in_form_on_a_desktop(visitor):
    resize(visitor, DESKTOP)

    visitor.open()
    visitor.auth.wait_until_shown()

    explanation, form = visitor.auth.explanation_box(), visitor.auth.form_box()
    assert explanation.right <= form.left, f"explanation {explanation}, form {form}"
