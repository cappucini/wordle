# Defines backend errors of what kind of problems can go wrong.
# This is used by the main.py handler, which is reflected in the error code of api.js
class GameNotFound(Exception):
    """No game has the id that was asked for."""

    pass


class GameOver(Exception):
    """The game is already won or lost, so it takes no more guesses and no new players."""

    pass


class InvalidGuess(Exception):
    """The guessed word is the wrong length, or is not in the word list."""

    pass


class NoWordsAvailable(Exception):
    """No answer words of the requested length are loaded, so a game cannot be started."""

    pass


# --- accounts and multiplayer ---


class NotAuthenticated(Exception):
    """No valid sign-in was sent with the request."""


class InvalidCredentials(Exception):
    """Wrong username or password."""


class UsernameTaken(Exception):
    """Someone tried to sign up with a username another account already has."""

    pass


class NotAPlayer(Exception):
    """The signed-in user is not one of this game's players."""


class GameFull(Exception):
    """The game already has as many players as one game may have."""

    pass


class CsrfCheckFailed(Exception):
    """A request that changes something arrived without the session's CSRF token."""


class TooManyAttempts(Exception):
    """Too many log-in or sign-up attempts recently. Carries how long to wait."""

    def __init__(self, retry_after_seconds: int) -> None:
        """Keeps the wait in seconds, and words the message in whole minutes."""
        self.retry_after_seconds = retry_after_seconds
        # // rounds down, so dividing the negated number and negating again rounds up
        minutes = max(1, -(-retry_after_seconds // 60))  # rounded up
        unit = "minute" if minutes == 1 else "minutes"
        # Exception keeps the message; str(exc) gives it back for the response
        super().__init__(f"Too many attempts. Try again in {minutes} {unit}")
