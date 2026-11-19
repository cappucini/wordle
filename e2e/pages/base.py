"""What every page object shares: the browser, and waiting.

Nothing here (or anywhere in the end-to-end tests) sleeps for a fixed time. Every wait is
for a condition, and gives up with a readable message after WAIT_SECONDS.
"""

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

# Long enough for a live update to arrive, or for the 5-second fallback check, with room to spare.
WAIT_SECONDS = 10


class Page:
    """The base of the page objects. Holds the browser, and the waits and lookups both pages use."""
    def __init__(self, driver: WebDriver):
        """Keeps the browser this page is shown in."""
        self.driver = driver

    def wait_until(self, condition, description: str):
        """Waits until `condition()` returns something truthy, and returns it.

        React may redraw an element between finding it and reading it; that is not a
        failure, so the condition is simply tried again.
        """
        wait = WebDriverWait(
            self.driver,
            WAIT_SECONDS,
            poll_frequency=0.1,
            ignored_exceptions=[StaleElementReferenceException],
        )
        # WebDriverWait calls its function with the driver; the condition here takes no
        # arguments, so the lambda throws the driver away
        return wait.until(lambda _driver: condition(), f"Timed out waiting until {description}")

    def button(self, text: str):
        """A button, found by the text a person reads on it."""
        # XPath: any <button> whose text, with spaces trimmed from both ends, is exactly `text`
        return self.driver.find_element("xpath", f'//button[normalize-space()="{text}"]')

    def has_button(self, text: str) -> bool:
        """Whether a button with this text is on the page. Does not wait."""
        # find_elements (plural) returns an empty list instead of raising when nothing matches
        return len(self.driver.find_elements("xpath", f'//button[normalize-space()="{text}"]')) > 0

    def has_text(self, text: str) -> bool:
        """Whether this text is visible anywhere on the page. Does not wait."""
        return text in self.driver.find_element("tag name", "body").text
