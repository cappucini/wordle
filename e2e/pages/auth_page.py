"""The sign-in form (frontend/src/components/AuthForm.jsx).

Every selector for the form lives in this file. Fields are found by their label and buttons
by their text, the way a person finds them.
"""

from pages.base import Page
from pages.game_page import Box

SIGN_IN_HEADING = "Sign in to play"
CREATE_HEADING = "Create an account"


class AuthPage(Page):
    # ---- selectors ----

    def _field(self, label: str):
        return self.driver.find_element(
            "xpath", f'//label[.//span[normalize-space()="{label}"]]//input'
        )

    def _heading(self) -> str:
        headings = self.driver.find_elements("css selector", "form h2")
        return headings[0].text if headings else ""

    # ---- what the page shows ----

    def is_shown(self) -> bool:
        return self._heading() in (SIGN_IN_HEADING, CREATE_HEADING)

    def wait_until_shown(self) -> "AuthPage":
        self.wait_until(self.is_shown, "the sign-in form is shown")
        return self

    def message(self) -> str:
        """The error line under the fields. Empty when there is nothing wrong."""
        return self.driver.find_element("css selector", '[role="alert"]').text

    def has_invite_notice(self) -> bool:
        return self.has_text("You've been invited to a game.")

    # ---- measuring the layout ----
    # Used by test_layout.py. Positions are in the window's own coordinates.

    def _box_of(self, element) -> Box:
        rect = element.rect
        scroll_x, scroll_y = self.driver.execute_script("return [window.scrollX, window.scrollY]")
        left, top = rect["x"] - scroll_x, rect["y"] - scroll_y
        return Box(left, top, left + rect["width"], top + rect["height"])

    def form_box(self) -> Box:
        return self._box_of(self.driver.find_element("css selector", "form"))

    def submit_button_box(self) -> Box:
        return self._box_of(self.button("Sign in"))

    def explanation_box(self) -> Box:
        return self._box_of(
            self.driver.find_element("css selector", 'section[aria-label="How to play"]')
        )

    def window_height(self) -> int:
        return self.driver.execute_script("return window.innerHeight")

    # ---- what a person does ----

    def _fill_in(self, username: str, password: str) -> None:
        self._field("Username").send_keys(username)
        self._field("Password").send_keys(password)

    def sign_in(self, username: str, password: str) -> None:
        self.wait_until_shown()
        self._fill_in(username, password)
        self.button("Sign in").click()

    def create_account(self, username: str, password: str) -> None:
        self.wait_until_shown()
        self.button("New here? Create an account").click()
        self.wait_until(lambda: self._heading() == CREATE_HEADING, "the create-account form is shown")
        self._fill_in(username, password)
        self.button("Create account").click()
