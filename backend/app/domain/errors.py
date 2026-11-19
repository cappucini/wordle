# Defines backend errors of what kind of problems can go wrong.
# This is used by the main.py handler , which is reflected in the error code of api.js
class GameNotFound(Exception):
    pass


class GameOver(Exception):
    pass


class InvalidGuess(Exception):
    pass


class NoWordsAvailable(Exception):
    pass


# --- accounts and multiplayer ---


class NotAuthenticated(Exception):
    """No valid sign-in was sent with the request."""


class InvalidCredentials(Exception):
    """Wrong username or password."""


class UsernameTaken(Exception):
    pass


class NotAPlayer(Exception):
    """The signed-in user is not one of this game's players."""


class GameFull(Exception):
    pass


class CsrfCheckFailed(Exception):
    """A request that changes something arrived without the session's CSRF token."""


class TooManyAttempts(Exception):
    """Too many log-in or sign-up attempts recently. Carries how long to wait."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        minutes = max(1, -(-retry_after_seconds // 60))  # rounded up
        unit = "minute" if minutes == 1 else "minutes"
        super().__init__(f"Too many attempts. Try again in {minutes} {unit}")
