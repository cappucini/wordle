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
        self.letter = ""
        self.result = None
        if label == "empty":
            return
        for ending, result in LABEL_ENDINGS.items():
            if label.endswith(ending):
                self.letter = label[: -len(ending)]
                self.result = result
                return
        self.letter = label  # typed, but not submitted yet


class GamePage(Page):
    # ---- selectors ----

    def _tiles(self) -> list[Tile]:
        elements = self.driver.find_elements("css selector", '[role="img"]')
        return [Tile(element.get_attribute("aria-label")) for element in elements]

    def _section(self, name: str):
        return self.driver.find_elements("css selector", f'section[aria-label="{name}"]')

    def _key(self, name: str):
        return self.driver.find_element("css selector", f'button[aria-label="{name}"]')

    # ---- signed in / signed out ----

    def signed_in_as(self) -> str | None:
        names = self.driver.find_elements(
            "xpath", '//p[starts-with(normalize-space(), "Signed in as")]/strong'
        )
        return names[0].text if names else None

    def wait_until_signed_in_as(self, username: str) -> "GamePage":
        self.wait_until(lambda: self.signed_in_as() == username, f"signed in as {username}")
        # the "New game" button appears once the game's rules have loaded
        self.wait_until(lambda: self.has_button("New game"), "the game screen has loaded")
        return self

    def sign_out(self) -> None:
        self.button("Sign out").click()

    # ---- starting and opening games ----

    def start_new_game(self, word_length: int = 5) -> "GamePage":
        self.driver.find_element(
            "xpath",
            f'//*[@role="group" and @aria-label="Word length"]//button[normalize-space()="{word_length}"]',
        ).click()
        self.button("New game").click()
        self.wait_until_board_is_shown(word_length)
        self.wait_until(lambda: "game=" in self.driver.current_url, "the game is in the address bar")
        return self

    def wait_until_board_is_shown(self, word_length: int = 5) -> "GamePage":
        expected = word_length * (word_length + 1)
        self.wait_until(
            lambda: len(self._tiles()) == expected, f"a {word_length}-letter board is shown"
        )
        return self

    def has_board(self) -> bool:
        return len(self._tiles()) > 0

    def invite_link(self) -> str:
        """The address of the game on screen: sharing it is how a player invites others."""
        return self.driver.current_url

    # ---- the board ----

    def rows(self) -> list[list[Tile]]:
        tiles = self._tiles()
        if not tiles:
            return []
        # a board for an n-letter word has n + 1 rows, so n * (n + 1) tiles
        word_length = int((math.isqrt(4 * len(tiles) + 1) - 1) / 2)
        return [tiles[start : start + word_length] for start in range(0, len(tiles), word_length)]

    def guesses(self) -> list[str]:
        """The words already guessed, in order."""
        return [
            "".join(tile.letter for tile in row)
            for row in self.rows()
            if all(tile.result is not None for tile in row)
        ]

    def results_of_guess(self, number: int) -> list[str]:
        """The result of each letter of the guess with this number (the first guess is 1)."""
        return [tile.result for tile in self.rows()[number - 1]]

    def letters_being_typed(self) -> str:
        for row in self.rows():
            if any(tile.result is None for tile in row):
                return "".join(tile.letter for tile in row)
        return ""

    def guesser_names(self) -> list[str]:
        """In a shared game, the name shown beside each guess, in order."""
        labels = self.driver.find_elements("css selector", '[title^="Guessed by "]')
        return [label.get_attribute("title").removeprefix("Guessed by ") for label in labels]

    # ---- playing ----

    def type_word(self, word: str) -> None:
        """Types on the physical keyboard, as a player at a desk does."""
        ActionChains(self.driver).send_keys(word).perform()
        self.wait_until(lambda: self.letters_being_typed() == word, f'"{word}" is typed in the row')

    def press_enter(self) -> None:
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
        self.wait_until(lambda: len(self.guesses()) == count, f"the board shows {count} guesses")

    # ---- messages and results ----

    def status_message(self) -> str:
        """The line under the controls: usually why a guess was refused. Empty when all is well."""
        return self.driver.find_element("css selector", '[role="status"]').text

    def wait_for_status_message(self) -> str:
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
        return self.wait_until(self.result_banner, "the game's result is shown")

    def keyboard_is_disabled(self) -> bool:
        return not self._key("Enter").is_enabled()

    # ---- players ----

    def players(self) -> list[str]:
        """The names in the players list, with "(you)" beside your own."""
        sections = self._section("Players")
        if not sections:
            return []
        return [item.text for item in sections[0].find_elements("tag name", "li")]

    def wait_until_player_count_is(self, count: int) -> None:
        self.wait_until(lambda: len(self.players()) == count, f"{count} players are listed")

    # ---- "Your games" ----

    def listed_games(self) -> list[str]:
        """Each line of "Your games" as text, for example "5 letters won 2 of 6 guesses"."""
        sections = self._section("Your games")
        if not sections:
            return []
        return [
            " ".join(item.text.split()) for item in sections[0].find_elements("tag name", "li")
        ]
