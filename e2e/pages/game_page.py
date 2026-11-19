"""The game screen (frontend/src/GameScreen.jsx and its components).

Every selector for the game screen lives in this file. They use what the app already
exposes for accessibility: labelled sections, button text, the status line, and each
tile's spoken label ("c, correct position"). No test-only attributes were needed.
"""

import math

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from pages.base import Page

# how a tile's spoken label ends, and the result that means
LABEL_ENDINGS = {
    ", correct position": "correct",
    ", in the word but in a different position": "present",
    ", not in the word": "absent",
}


class Tile:
    """One square on the board: its letter ("" when empty) and its result (None until scored)."""

    def __init__(self, label: str):
        """Works out the letter and result from the tile's spoken label."""
        self.letter = ""
        self.result = None
        if label == "empty":
            return
        for ending, result in LABEL_ENDINGS.items():
            if label.endswith(ending):
                # cut the ending off the label; what is left is the letter
                self.letter = label[: -len(ending)]
                self.result = result
                return
        self.letter = label  # typed, but not submitted yet


class GamePage(Page):
    """The game screen: the board, the keyboard, the players and "Your games".

    Tests call these methods instead of looking for elements themselves. The second half
    measures where things are on screen, for test_layout.py.
    """
    # ---- selectors ----

    def _tiles(self) -> list[Tile]:
        """Every square on the board, in reading order."""
        # each tile is drawn as role="img" with its letter and result in aria-label
        elements = self.driver.find_elements("css selector", '[role="img"]')
        return [Tile(element.get_attribute("aria-label")) for element in elements]

    def _section(self, name: str):
        """The sections with this accessible name: a list, empty when there is none."""
        return self.driver.find_elements("css selector", f'section[aria-label="{name}"]')

    def _key(self, name: str):
        """A key of the on-screen keyboard, such as "q" or "Enter"."""
        return self.driver.find_element("css selector", f'button[aria-label="{name}"]')

    # ---- signed in / signed out ----

    def signed_in_as(self) -> str | None:
        """The username in the "Signed in as" line, or None when nobody is signed in."""
        names = self.driver.find_elements(
            # XPath: the <strong> directly inside the <p> whose text starts with "Signed in as"
            "xpath", '//p[starts-with(normalize-space(), "Signed in as")]/strong'
        )
        return names[0].text if names else None

    def wait_until_signed_in_as(self, username: str) -> "GamePage":
        """Waits until the game screen is loaded and shows this username."""
        self.wait_until(lambda: self.signed_in_as() == username, f"signed in as {username}")
        # the "New game" button appears once the game's rules have loaded
        self.wait_until(lambda: self.has_button("New game"), "the game screen has loaded")
        return self

    def sign_out(self) -> None:
        """Clicks "Sign out". Does not wait for the sign-in form."""
        self.button("Sign out").click()

    # ---- starting and opening games ----

    def start_new_game(self, word_length: int = 5) -> "GamePage":
        """Picks a word length, starts a game, and waits for its board and its address."""
        # XPath: inside the group labelled "Word length", the button whose text is the number
        self.driver.find_element(
            "xpath",
            f'//*[@role="group" and @aria-label="Word length"]//button[normalize-space()="{word_length}"]',
        ).click()
        self.button("New game").click()
        self.wait_until_board_is_shown(word_length)
        self.wait_until(lambda: "game=" in self.driver.current_url, "the game is in the address bar")
        return self

    def wait_until_board_is_shown(self, word_length: int = 5) -> "GamePage":
        """Waits until a board with the right number of tiles for this word length is shown."""
        # a game allows one more guess than the word has letters, so n columns by n + 1 rows
        expected = word_length * (word_length + 1)
        self.wait_until(
            lambda: len(self._tiles()) == expected, f"a {word_length}-letter board is shown"
        )
        return self

    def has_board(self) -> bool:
        """Whether any board is on the page. Does not wait."""
        return len(self._tiles()) > 0

    def invite_link(self) -> str:
        """The address of the game on screen: sharing it is how a player invites others."""
        return self.driver.current_url

    # ---- the board ----

    def rows(self) -> list[list[Tile]]:
        """The board as a list of rows, each a list of tiles. Empty when there is no board."""
        tiles = self._tiles()
        if not tiles:
            return []
        # a board for an n-letter word has n + 1 rows, so n * (n + 1) tiles
        # solving n * (n + 1) = tiles for n gives n = (sqrt(4 * tiles + 1) - 1) / 2
        word_length = int((math.isqrt(4 * len(tiles) + 1) - 1) / 2)
        # cut the flat list of tiles into rows of word_length
        return [tiles[start : start + word_length] for start in range(0, len(tiles), word_length)]

    def guesses(self) -> list[str]:
        """The words already guessed, in order."""
        return [
            "".join(tile.letter for tile in row)
            for row in self.rows()
            # only rows where every tile is scored; this skips empty rows and the one being typed
            if all(tile.result is not None for tile in row)
        ]

    def results_of_guess(self, number: int) -> list[str]:
        """The result of each letter of the guess with this number (the first guess is 1)."""
        return [tile.result for tile in self.rows()[number - 1]]

    def letters_being_typed(self) -> str:
        """The letters in the current row that have not been submitted yet. "" when none."""
        # the first row that is not fully scored is the one being typed into
        for row in self.rows():
            if any(tile.result is None for tile in row):
                return "".join(tile.letter for tile in row)
        return ""

    def guesser_names(self) -> list[str]:
        """In a shared game, the name shown beside each guess, in order."""
        # CSS: ^= matches elements whose title starts with this text
        labels = self.driver.find_elements("css selector", '[title^="Guessed by "]')
        return [label.get_attribute("title").removeprefix("Guessed by ") for label in labels]

    # ---- playing ----

    def type_word(self, word: str) -> None:
        """Types on the physical keyboard, as a player at a desk does."""
        # ActionChains sends the keys to the page as a whole, not to one element, because
        # the game listens for key presses on the window
        ActionChains(self.driver).send_keys(word).perform()
        self.wait_until(lambda: self.letters_being_typed() == word, f'"{word}" is typed in the row')

    def press_enter(self) -> None:
        """Presses Enter on the physical keyboard. Does not wait for the result."""
        ActionChains(self.driver).send_keys(Keys.ENTER).perform()

    def click_keys(self, word: str) -> None:
        """Types with the on-screen keyboard, as a player on a phone does."""
        for letter in word:
            self._key(letter).click()
        self.wait_until(lambda: self.letters_being_typed() == word, f'"{word}" is typed in the row')

    def guess(self, word: str) -> None:
        """Types a word, submits it, and waits until the board shows it scored."""
        already = len(self.guesses())
        self.type_word(word)
        self.press_enter()
        self.wait_until_guess_count_is(already + 1)

    def wait_until_guess_count_is(self, count: int) -> None:
        """Waits until the board shows this many scored guesses."""
        self.wait_until(lambda: len(self.guesses()) == count, f"the board shows {count} guesses")

    # ---- messages and results ----

    def status_message(self) -> str:
        """The line under the controls: usually why a guess was refused. Empty when all is well."""
        return self.driver.find_element("css selector", '[role="status"]').text

    def wait_for_status_message(self) -> str:
        """Waits until the status line says something, and returns what it says."""
        # wait_until returns the condition's value, and an empty string counts as "not yet"
        return self.wait_until(self.status_message, "a message is shown")

    def result_banner(self) -> str:
        """The line shown when the game ends. Empty while it is in progress."""
        banners = self.driver.find_elements(
            "xpath",
            '//p[starts-with(normalize-space(), "You got it in") '
            'or starts-with(normalize-space(), "Out of guesses")]',
        )
        return banners[0].text if banners else ""

    def wait_for_result_banner(self) -> str:
        """Waits until the game has ended, and returns the line that says how."""
        return self.wait_until(self.result_banner, "the game's result is shown")

    def keyboard_is_disabled(self) -> bool:
        """Whether the on-screen keyboard is switched off, as it is once the game is over."""
        return not self._key("Enter").is_enabled()

    # ---- players ----

    def players(self) -> list[str]:
        """The names in the players list, with "(you)" beside your own."""
        sections = self._section("Players")
        if not sections:
            return []
        return [item.text for item in sections[0].find_elements("tag name", "li")]

    def wait_until_player_count_is(self, count: int) -> None:
        """Waits until the players list has this many names."""
        self.wait_until(lambda: len(self.players()) == count, f"{count} players are listed")

    # ---- "Your games" ----

    def listed_games(self) -> list[str]:
        """Each line of "Your games" as text, for example "5 letters won 2 of 6 guesses"."""
        sections = self._section("Your games")
        if not sections:
            return []
        return [
            # split() then join() turns line breaks and runs of spaces into single spaces
            " ".join(item.text.split()) for item in sections[0].find_elements("tag name", "li")
        ]

    # ---- the rules panel ----

    def open_rules_with_shortcut(self) -> None:
        """Presses "?" and waits for the rules panel to open."""
        ActionChains(self.driver).send_keys("?").perform()
        self.wait_until(lambda: self.rules_panel_box() is not None, "the rules panel is open")

    def close_rules(self) -> None:
        """Presses Escape and waits for the rules panel to go away."""
        ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
        self.wait_until(lambda: self.rules_panel_box() is None, "the rules panel is closed")

    def rules_panel_box(self) -> "Box | None":
        """Where the rules panel is, or None when it is closed."""
        return self._box('section[aria-label="How to play"]')

    # ---- measuring the layout ----
    # Used by test_layout.py. Positions are in the window's own coordinates: (0, 0) is the
    # top-left corner of what is visible, so a box inside the window is on screen.

    def _box(self, css: str) -> "Box | None":
        """Where the first element matching this CSS selector is, or None when there is none."""
        # The JavaScript runs in the page. `arguments[0]` is the first value passed after
        # the script (here `css`), and what the script returns comes back as Python values.
        # getBoundingClientRect() gives the element's edges in window coordinates.
        rect = self.driver.execute_script(
            "const e = document.querySelector(arguments[0]);"
            "if (e === null) return null;"
            "const r = e.getBoundingClientRect();"
            "return [r.left, r.top, r.right, r.bottom];",
            css,
        )
        return None if rect is None else Box(*rect)

    def window_size(self) -> tuple[int, int]:
        """The width and height of the visible page, without the browser's own frame."""
        width, height = self.driver.execute_script(
            "return [document.documentElement.clientWidth, window.innerHeight]"
        )
        return width, height

    def sideways_overflow(self) -> int:
        """How many pixels wider the page is than the window. 0 when nothing sticks out."""
        return self.driver.execute_script(
            # scrollWidth is how wide the content is; clientWidth is how much of it fits
            "return Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth)"
        )

    def scroll_to_bottom(self) -> int:
        """Scrolls as far down as the page goes, and returns how far that was."""
        return self.driver.execute_script(
            "window.scrollTo(0, document.documentElement.scrollHeight); return Math.round(window.scrollY)"
        )

    def board_box(self) -> "Box":
        """From the first tile's top-left corner to the last tile's bottom-right."""
        left, top, right, bottom = self.driver.execute_script(
            "const tiles = [...document.querySelectorAll('[role=\"img\"]')];"
            # at(-1) is the last item of a JavaScript array
            "const first = tiles[0].getBoundingClientRect(), last = tiles.at(-1).getBoundingClientRect();"
            "return [first.left, first.top, last.right, last.bottom];"
        )
        return Box(left, top, right, bottom)

    def key_box(self, name: str) -> "Box":
        """Where a key of the on-screen keyboard is."""
        return self._box(f'button[aria-label="{name}"]')

    def key_label_fits(self, name: str) -> bool:
        """False when a key is too narrow for the word written on it."""
        return self.driver.execute_script(
            # a label that needs more room than its key has makes scrollWidth the larger
            "const key = document.querySelector(arguments[0]); return key.scrollWidth <= key.clientWidth;",
            f'button[aria-label="{name}"]',
        )

    def players_panel_box(self) -> "Box":
        """Where the players panel is."""
        return self._box('section[aria-label="Players"]')

    def copy_link_button_box(self) -> "Box":
        """Where the "Copy invite link" button is: the first button in the players panel."""
        return self._box('section[aria-label="Players"] button')

    def make_copying_fail(self) -> None:
        """Makes the browser refuse to copy, as it does when clipboard access is blocked."""
        self.driver.execute_script(
            # replace the browser's copy function with one that always fails
            "navigator.clipboard.writeText = () => Promise.reject(new Error('blocked'))"
        )

    def title_box(self) -> "Box":
        """The title's letters, from the first to the last (not the full-width heading)."""
        left, top, right, bottom = self.driver.execute_script(
            "const letters = [...document.querySelectorAll('h1 span')];"
            "const first = letters[0].getBoundingClientRect(), last = letters.at(-1).getBoundingClientRect();"
            "return [first.left, first.top, last.right, last.bottom];"
        )
        return Box(left, top, right, bottom)

    def signed_in_name_box(self) -> "Box":
        """Where the username in the "Signed in as" line is."""
        return self._box("p > strong")

    # ---- "Your games", measured ----

    def open_listed_game(self, position: int) -> None:
        """Opens a game from "Your games" by its place in the list (the newest is 0)."""
        buttons = self._section("Your games")[0].find_elements("css selector", "li button")
        buttons[position].click()

    def games_list_scroll(self) -> dict:
        """How the games list is scrolling: whether there is more than fits, and whether
        the open game is inside the part that shows."""
        return self.driver.execute_script(
            # clientHeight is the part of the list that shows; scrollHeight is all of it.
            # The open game is the row marked aria-current="true"; it is in view when its
            # top and bottom are both inside the list's box, give or take a pixel.
            "const list = document.querySelector('section[aria-label=\"Your games\"] ul');"
            "const box = list.getBoundingClientRect();"
            "const current = list.querySelector('[aria-current=\"true\"]');"
            "const item = current === null ? null : current.getBoundingClientRect();"
            "return {"
            "  shows: Math.round(list.clientHeight), holds: Math.round(list.scrollHeight),"
            "  open_game_in_view: item !== null && item.top >= box.top - 1 && item.bottom <= box.bottom + 1,"
            "};"
        )

    def small_boards(self) -> list[dict]:
        """For each game in "Your games": the height of its row, and how its small board
        of squares is drawn."""
        return self.driver.execute_script(
            # For each row: measure every square of its small board. `new Set(...)` drops
            # repeats, so `widths` has one entry when all the squares are equally wide.
            # `all_inside` is true when no square pokes out of the board's own box.
            "return [...document.querySelectorAll('section[aria-label=\"Your games\"] li button')].map((row) => {"
            "  const mini = row.querySelector('[data-testid=\"game-mini\"]');"
            "  const box = mini.getBoundingClientRect();"
            "  const squares = [...mini.querySelectorAll('i')].map((square) => square.getBoundingClientRect());"
            "  return {"
            "    row_height: row.getBoundingClientRect().height,"
            "    squares: squares.length,"
            "    widths: [...new Set(squares.map((s) => s.width))],"
            "    heights: [...new Set(squares.map((s) => s.height))],"
            "    all_inside: squares.every((s) => s.left >= box.left - 0.5 && s.right <= box.right + 0.5"
            "      && s.top >= box.top - 0.5 && s.bottom <= box.bottom + 0.5),"
            "  };"
            "});"
        )


class Box:
    """Where something is on screen: its four edges, in pixels from the window's top-left."""

    def __init__(self, left: float, top: float, right: float, bottom: float):
        """Keeps the four edges."""
        self.left, self.top, self.right, self.bottom = left, top, right, bottom

    @property
    def width(self) -> float:
        """How wide the box is, in pixels."""
        return self.right - self.left

    @property
    def height(self) -> float:
        """How tall the box is, in pixels."""
        return self.bottom - self.top

    def is_inside(self, other: "Box", tolerance: float = 1) -> bool:
        """Whether this box lies within `other`, allowing `tolerance` pixels for rounding."""
        return (
            self.left >= other.left - tolerance
            and self.right <= other.right + tolerance
            and self.top >= other.top - tolerance
            and self.bottom <= other.bottom + tolerance
        )

    def __repr__(self) -> str:
        """Shows the four edges as whole pixels, so a failed assertion is easy to read."""
        return f"Box(left={self.left:.0f}, top={self.top:.0f}, right={self.right:.0f}, bottom={self.bottom:.0f})"
