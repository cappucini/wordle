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
