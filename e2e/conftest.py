"""Fixtures for the end-to-end tests: browsers, unique users, and what to save on failure."""

import os
import re
import uuid
from pathlib import Path

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from pages.auth_page import AuthPage
from pages.game_page import GamePage

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
API_URL = os.environ.get("API_URL", "http://localhost:8000/api/v1")
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"

PASSWORD = "correct horse battery"

# The answer to every 5-letter game in the test stack (see backend/tests/words/).
ANSWER = "crane"
# Six valid guesses that are not the answer: enough to lose a game.
WRONG_GUESSES = ["slate", "react", "nacre", "eerie", "elect", "moist"]


def unique_username() -> str:
    """A username no other test (or earlier run) has used. 14 characters; the limit is 20."""
    return "e2e_" + uuid.uuid4().hex[:10]


# ---------- browsers ----------


def start_browser() -> webdriver.Chrome:
    """Starts a headless Chromium with a 1280 x 1000 window."""
    options = Options()
    options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,1000")
    # needed to run Chromium as root inside a container
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # keep everything the page writes to the console, to save if the test fails
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    service = Service(os.environ.get("CHROMEDRIVER", "/usr/bin/chromedriver"))
    return webdriver.Chrome(options=options, service=service)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Records each test's outcome on the test itself, so fixtures can see whether it failed."""
    # a hook wrapper pauses at `yield` while pytest builds the report, then receives it.
    # This runs three times per test; report.when is "setup", "call" or "teardown",
    # so the reports end up as item.report_setup, item.report_call and item.report_teardown
    outcome = yield
    report = outcome.get_result()
    setattr(item, "report_" + report.when, report)


def save_failure_artifacts(driver, test_name: str, browser_number: int) -> None:
    """Saves what the browser looked like and what it logged, for a test that failed."""
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    # a parametrized test has [ ] and commas in its name; keep only what is safe in a file name
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", test_name)
    base = ARTIFACTS_DIR / f"{safe_name}.browser{browser_number}"

    # with_suffix() replaces the last suffix (".browser1"), so each new suffix is added
    # to it: name.browser1.png, name.browser1.console.log, name.browser1.html
    driver.save_screenshot(str(base.with_suffix(base.suffix + ".png")))
    console = driver.get_log("browser")
    lines = [f"URL: {driver.current_url}", ""]
    lines += [f"[{entry['level']}] {entry['message']}" for entry in console]
    if not console:
        lines.append("(the console was empty)")
    base.with_suffix(base.suffix + ".console.log").write_text("\n".join(lines) + "\n")
    base.with_suffix(base.suffix + ".html").write_text(driver.page_source)


@pytest.fixture
def new_browser(request):
    """Starts browsers. Each one is a separate person: its own cookies, its own window.

    When the test fails, every browser it opened gets a screenshot, its console log and
    its page source saved to e2e/artifacts/ before it is closed.
    """
    drivers = []

    def start() -> webdriver.Chrome:
        """Starts one browser, and remembers it so it can be closed after the test."""
        driver = start_browser()
        drivers.append(driver)
        return driver

    # the test runs while the fixture is paused here; what follows is the clean-up
    yield start

    # report_call was put there by pytest_runtest_makereport above. It is missing when
    # the test never ran (for example because another fixture failed first)
    report = getattr(request.node, "report_call", None)
    failed = report is not None and report.failed
    for number, driver in enumerate(drivers, start=1):
        # close the browser even if saving the artifacts goes wrong
        try:
            if failed:
                save_failure_artifacts(driver, request.node.name, number)
        finally:
            driver.quit()


@pytest.fixture
def browser(new_browser):
    """One browser, for tests that drive Selenium directly."""
    return new_browser()


# ---------- a person at a browser ----------


class Visitor:
    """One person with one browser, and the two pages they can be on."""

    def __init__(self, driver):
        """Gives the person a fresh username and a page object for each of the two pages."""
        self.driver = driver
        self.username = unique_username()
        self.password = PASSWORD
        self.auth = AuthPage(driver)
        self.game = GamePage(driver)

    def open(self, url: str = FRONTEND_URL) -> "Visitor":
        """Loads the app (or an invite link) and returns the visitor, so calls can be chained."""
        self.driver.get(url)
        return self

    def sign_up(self, url: str = FRONTEND_URL) -> "Visitor":
        """Opens the app (or an invite link), creates an account, and waits for the game screen."""
        self.open(url)
        self.auth.create_account(self.username, self.password)
        self.game.wait_until_signed_in_as(self.username)
        return self


@pytest.fixture
def new_visitor(new_browser):
    """Makes visitors, each with a browser of their own. For tests with two people."""
    return lambda: Visitor(new_browser())


@pytest.fixture
def visitor(new_visitor):
    """One person at one browser, not yet signed up."""
    return new_visitor()


# ---------- players set up through the API ----------


class ApiPlayer:
    """A player who exists only to set the scene, created through the API rather than
    by clicking through the sign-up form."""

    def __init__(self):
        """Signs up a new user through the API and stays signed in as them."""
        self.username = unique_username()
        # a requests.Session keeps cookies between calls, so the sign-in cookie is sent each time
        self.http = requests.Session()
        response = self.http.post(
            f"{API_URL}/users", json={"username": self.username, "password": PASSWORD}
        )
        assert response.status_code == 201, response.text
        # and from now on every request carries the CSRF token as well
        self.http.headers["X-CSRF-Token"] = response.json()["csrf_token"]

    def create_game(self, word_length: int = 5) -> str:
        """Starts a game and returns its id."""
        response = self.http.post(f"{API_URL}/games", json={"word_length": word_length})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def join(self, game_id: str) -> None:
        """Joins a game. Fails if the server refuses."""
        response = self.http.post(f"{API_URL}/games/{game_id}/players")
        assert response.status_code == 200, response.text


@pytest.fixture
def new_api_player():
    """Makes API-only players. Returns the class itself, so calling `new_api_player()`
    in a test creates one."""
    return ApiPlayer
