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
