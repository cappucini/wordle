"""Scores one guess against the answer: green, yellow or gray for each letter."""

from app.domain.rules import LetterResult


def score(guess: str, answer: str) -> list[LetterResult]:
    """Scores a guess against the answer: one LetterResult per letter, in order.

    Each letter of the answer can be matched only once. If the answer has one E and the
    guess has two, only one of them is marked, and an E in the right place comes first.
    The two words are expected to be the same length.
    """
    # list of empty letter results
    results = [LetterResult.absent] * len(guess)
    # the answer's letters that have not been matched yet
    remaining = list(answer)

    # Step 1: greens. Same letter in the same position.
    for i in range(len(guess)):
        if guess[i] == answer[i]:
            results[i] = LetterResult.correct
            remaining[i] = None  # cross this letter off

    # Step 2: yellows. The letter is still available somewhere else.
    for i in range(len(guess)):
        if results[i] == LetterResult.correct:
            continue  # already handled
        if guess[i] in remaining:
            results[i] = LetterResult.present
            remaining[remaining.index(guess[i])] = None  # cross one copy off

    return results
