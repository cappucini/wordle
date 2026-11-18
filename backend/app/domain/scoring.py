from app.domain.rules import LetterResult


def score(guess: str, answer: str) -> list[LetterResult]:
    # list of empty letter results
    results = [LetterResult.absent] * len(guess)
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
