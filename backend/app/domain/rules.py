from enum import Enum

# Word length limits and turn allowance
MIN_WORD_LENGTH = 5
MAX_WORD_LENGTH = 8
DEFAULT_WORD_LENGTH = 5
EXTRA_GUESSES = 1  # a game allows word_length + EXTRA_GUESSES guesses


class LetterResult(str, Enum):
    correct = "correct"  # right letter, right position
    present = "present"  # letter is in the answer, wrong position
    absent = "absent"    # letter is not in the answer


class GameStatus(str, Enum):
    in_progress = "in_progress"
    won = "won"
    lost = "lost"


def max_guesses_for(word_length: int) -> int:
    return word_length + EXTRA_GUESSES


def next_status(guesses_used: int, max_guesses: int, guessed_correctly: bool) -> GameStatus:
    if guessed_correctly:
        return GameStatus.won
    if guesses_used >= max_guesses:
        return GameStatus.lost
    return GameStatus.in_progress
