from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import WordRow
from app.domain.rules import MAX_WORD_LENGTH, MIN_WORD_LENGTH

# The folder holding answers_5.txt, valid_5.txt, and so on.
# The 5-letter files are the original Wordle lists, used exactly as published: its answers,
# and the further words it accepted as guesses. The 6 to 8 letter files are built by
# backend/scripts/build_word_lists.py, because no official lists exist for those lengths.
# Where each comes from is described under "Word Lists" in the README.
DATA_DIR = Path(__file__).parent / "data"


def read_words(path: Path) -> set[str]:
    """Read a text file with one word per line and return the words as a set."""
    words = set()
    for line in path.read_text().splitlines():
        word = line.strip().lower()
        if word != "":
            words.add(word)
    return words


def words_table_is_empty(session: Session) -> bool:
    first_row = session.execute(select(WordRow.id).limit(1)).first()
    return first_row is None


def seed_words_if_empty(session: Session) -> None:
    """Fill the words table from the data files, unless it already has words."""
    if not words_table_is_empty(session):
        return

    for length in range(MIN_WORD_LENGTH, MAX_WORD_LENGTH + 1):
        answer_words = read_words(DATA_DIR / f"answers_{length}.txt")
        guess_words = read_words(DATA_DIR / f"valid_{length}.txt")

        # every answer must also be accepted as a guess
        all_words = guess_words.union(answer_words)

        for word in sorted(all_words):
            row = WordRow(
                text=word,
                length=length,
                is_answer=(word in answer_words),
            )
            session.add(row)

    session.commit()
