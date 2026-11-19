"""app/domain/scoring.py: turning a guess and an answer into correct/present/absent."""

import pytest

from app.domain.rules import LetterResult
from app.domain.scoring import score

# One letter per tile, so a whole row reads at a glance in the table below.
SHORTHAND = {
    "C": LetterResult.correct,
    "P": LetterResult.present,
    "A": LetterResult.absent,
}


def row(pattern: str) -> list[LetterResult]:
    return [SHORTHAND[letter] for letter in pattern]


@pytest.mark.parametrize(
    "guess, answer, expected",
    [
        # --- no repeated letters ---
        pytest.param("crane", "crane", "CCCCC", id="exact match is all correct"),
        pytest.param("crane", "moist", "AAAAA", id="no shared letters is all absent"),
        pytest.param("nacre", "crane", "PPPPC", id="anagram: right letters, wrong places"),
        pytest.param("slate", "crane", "AACAC", id="mix of correct and absent"),
        pytest.param("react", "crane", "PPCPA", id="mix of all three results"),
        # --- a letter repeated in the guess, once in the answer ---
        pytest.param(
            "elect", "crane", "PAAPA",
            id="two e's guessed, one in answer: only the first is present",
        ),
        pytest.param(
            "eerie", "crane", "AAPAC",
            id="the correct e uses up the answer's only e, so earlier e's are absent",
        ),
        # --- a letter repeated in the answer, once in the guess ---
        pytest.param(
            "crane", "eerie", "APAAC",
            id="one e guessed, three in answer: just that tile is marked",
        ),
        # --- a letter repeated in both ---
        pytest.param(
            "speed", "erase", "PAPPA",
            id="two e's guessed, two in answer, neither in place: both present",
        ),
        pytest.param(
            "eerie", "erase", "CAPAC",
            id="three e's guessed, two in answer: two correct, the spare is absent",
        ),
        pytest.param(
            "eagle", "geese", "PAPAC",
            id="one e correct and another e present in the same guess",
        ),
        pytest.param(
            "llama", "hello", "PPAAA",
            id="double letter guessed in the wrong places: both present",
        ),
        # --- longer words ---
        pytest.param("notebook", "textbook", "AAPPCCCC", id="8 letters with repeats"),
        pytest.param("absolute", "absolute", "CCCCCCCC", id="8 letters exact match"),
    ],
)
def test_score(guess, answer, expected):
    assert score(guess, answer) == row(expected)


def test_score_returns_one_result_per_letter():
    for word in ["crane", "planet", "kitchen", "absolute"]:
        assert len(score(word, word[::-1])) == len(word)


def test_score_never_marks_more_copies_of_a_letter_than_the_answer_has():
    # "geese" has three e's; "crane" has one. Exactly one e may be marked.
    results = score("geese", "crane")
    marked = [result for result in results if result != LetterResult.absent]
    assert len(marked) == 1


def test_score_results_are_the_api_strings():
    # the API sends these values to the frontend, which uses them as CSS class names
    assert [result.value for result in score("react", "crane")] == [
        "present",
        "present",
        "correct",
        "present",
        "absent",
    ]
