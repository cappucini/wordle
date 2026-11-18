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
