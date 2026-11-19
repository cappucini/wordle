"""The committed word lists in app/words/data, and the function that reads them.

The other test layers load small fixed word lists so they know the answer. That leaves the
real files, the ones production loads, checked only here.
"""

import re

import pytest

from app.domain.rules import MAX_WORD_LENGTH, MIN_WORD_LENGTH
from app.words.seed import DATA_DIR, read_words

LENGTHS = range(MIN_WORD_LENGTH, MAX_WORD_LENGTH + 1)
FILES = [f"{kind}_{length}.txt" for length in LENGTHS for kind in ("answers", "valid")]


def lines_of(file_name: str) -> list[str]:
    return [line for line in (DATA_DIR / file_name).read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("file_name", FILES)
def test_word_file_exists_and_has_words(file_name):
    assert (DATA_DIR / file_name).is_file()
    assert len(lines_of(file_name)) > 0


@pytest.mark.parametrize("file_name", FILES)
def test_every_word_has_the_length_in_the_file_name(file_name):
    length = int(re.search(r"_(\d)\.txt$", file_name).group(1))

    wrong = [word for word in lines_of(file_name) if len(word.strip()) != length]

    assert wrong == []


@pytest.mark.parametrize("file_name", FILES)
def test_every_word_is_lowercase_letters_only(file_name):
    # a guess is lowercased and limited to letters before it is looked up,
    # so a word with anything else in it could never be matched
    wrong = [word for word in lines_of(file_name) if not re.fullmatch(r"[a-z]+", word)]

    assert wrong == []


@pytest.mark.parametrize("file_name", FILES)
def test_no_word_is_listed_twice(file_name):
    words = lines_of(file_name)

    assert len(words) == len(set(words))


@pytest.mark.parametrize("length", LENGTHS)
def test_guess_list_is_larger_than_answer_list(length):
    assert len(lines_of(f"valid_{length}.txt")) > len(lines_of(f"answers_{length}.txt"))


def test_read_words_trims_lowercases_and_skips_blank_lines(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("crane\n  Slate  \n\n   \nREACT\n")

    assert read_words(path) == {"crane", "slate", "react"}


def test_read_words_drops_duplicates(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("crane\nCRANE\ncrane \n")

    assert read_words(path) == {"crane"}


def test_read_words_of_an_empty_file_is_empty(tmp_path):
    path = tmp_path / "words.txt"
    path.write_text("")

    assert read_words(path) == set()


# ---------- the 5-letter lists are the original Wordle lists ----------
# They are copied in exactly as published, not generated and not edited (see the README).
# These checks catch them being regenerated, truncated or "tidied up" by accident.


def test_five_letter_answers_are_the_original_wordle_answers():
    answers = lines_of("answers_5.txt")

    assert len(answers) == 2315
    assert answers[0] == "aback"
    assert answers[-1] == "zonal"
    for word in ["cigar", "crane", "spoon", "towel", "zebra"]:
        assert word in answers


def test_five_letter_guesses_are_the_original_wordle_guesses():
    # the 2,315 answers plus the 10,657 other words the original game accepted
    assert len(lines_of("valid_5.txt")) == 12972


@pytest.mark.parametrize("length", LENGTHS)
def test_every_answer_is_also_an_accepted_guess(length):
    answers = set(lines_of(f"answers_{length}.txt"))
    valid = set(lines_of(f"valid_{length}.txt"))

    assert answers <= valid


@pytest.mark.parametrize("file_name", FILES)
def test_word_file_is_sorted_and_ends_with_a_line_break(file_name):
    # sorted keeps a change to the list readable in a diff; the final line break keeps the
    # last word from being glued to another file's first when files are joined
    text = (DATA_DIR / file_name).read_text()
    words = text.splitlines()

    assert text.endswith("\n")
    assert words == sorted(words)


def test_five_letter_answers_are_left_exactly_as_the_original_game_had_them():
    # The original list has no plurals made by adding "s", but it does include a few
    # irregular ones, and words the New York Times later withdrew. They are kept on purpose:
    # the decision was to use the official list unchanged, not a cleaned-up copy of it.
    answers = lines_of("answers_5.txt")

    for word in ["geese", "teeth", "women", "fungi", "cacti", "radii", "algae"]:
        assert word in answers
    for word in ["slave", "lynch", "wench"]:
        assert word in answers


def test_no_five_letter_answer_is_a_plural_made_by_adding_s():
    # every answer ending in "s" is one of these, and none of them is a plural
    ending_in_s = [word for word in lines_of("answers_5.txt") if word.endswith("s")]
    not_double_s = sorted(word for word in ending_in_s if not word.endswith("ss"))

    assert not_double_s == [
        "basis", "bonus", "chaos", "ethos", "fetus", "ficus", "focus", "humus",
        "locus", "lupus", "minus", "mucus", "rebus", "torus", "virus",
    ]


def test_plurals_are_accepted_as_guesses_but_are_not_answers():
    answers = lines_of("answers_5.txt")
    valid = lines_of("valid_5.txt")

    for word in ["cakes", "boxes", "foxes"]:
        assert word in valid
        assert word not in answers
