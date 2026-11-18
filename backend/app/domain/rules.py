from enum import Enum

# Word length limits and turn allowance
MIN_WORD_LENGTH = 5
MAX_WORD_LENGTH = 8
DEFAULT_WORD_LENGTH = 5
EXTRA_GUESSES = 1  # a game allows word_length + EXTRA_GUESSES guesses
MAX_PLAYERS_PER_GAME = 3  # a game is shared by at most this many players
WORD_PATTERN = r"^[A-Za-z]+$"  # letters only; no digits, spaces or symbols

# Accounts
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 20
USERNAME_PATTERN = r"^[a-z0-9_]+$"  # lowercase letters, digits and underscores
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
SESSION_DAYS = 7  # how long a sign-in stays valid


class LetterResult(str, Enum):
    correct = "correct"  # right letter, right position
    present = "present"  # letter is in the answer, wrong position
    absent = "absent"  # letter is not in the answer


class GameStatus(str, Enum):
    in_progress = "in_progress"
    won = "won"
    lost = "lost"


def max_guesses_for(word_length: int) -> int:
    return word_length + EXTRA_GUESSES


def next_status(
    guesses_used: int, max_guesses: int, guessed_correctly: bool
) -> GameStatus:
    if guessed_correctly:
        return GameStatus.won
    if guesses_used >= max_guesses:
        return GameStatus.lost
    return GameStatus.in_progress
