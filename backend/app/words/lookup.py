"""What the game asks of the word lists: pick a random answer, and is this guess a real word?"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import WordRow
from app.domain.errors import NoWordsAvailable


# The two questions the game asks of the word lists (loaded into the `words` table by seed.py):
#   - random_answer: pick a game's answer, from the smaller list of answer words only
#   - is_valid: may this word be guessed? Any word on the accepted-guesses list may, which
#     includes plurals and obscure words that are never chosen as an answer.


def random_answer(session: Session, length: int) -> str:
    """Picks one answer word of this length at random. Raises NoWordsAvailable if none exist."""
    query = (
        select(WordRow.text)
        # .is_(True) is how SQLAlchemy writes SQL's "IS TRUE"; conditions separated by
        # a comma must all hold
        .where(WordRow.length == length, WordRow.is_answer.is_(True))
        # the database puts the matching words in a random order, and the first is taken
        .order_by(func.random())
        .limit(1)
    )
    # the word itself if a row came back, or None if no row did
    answer = session.execute(query).scalar_one_or_none()
    if answer is None:
        raise NoWordsAvailable(f"No {length}-letter answer words are loaded")
    return answer


def is_valid(session: Session, word: str) -> bool:
    """True if the word is in the words table, so may be guessed."""
    return (
        session.execute(select(WordRow.id).where(WordRow.text == word)).first()
        is not None
    )
