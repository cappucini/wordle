from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import WordRow
from app.domain.errors import NoWordsAvailable


# The two questions the game asks of the word lists (loaded into the `words` table by seed.py):
#   - random_answer: pick a game's answer, from the smaller list of answer words only
#   - is_valid: may this word be guessed? Any word on the accepted-guesses list may, which
#     includes plurals and obscure words that are never chosen as an answer.


def random_answer(session: Session, length: int) -> str:
    query = (
        select(WordRow.text)
        .where(WordRow.length == length, WordRow.is_answer.is_(True))
        .order_by(func.random())
        .limit(1)
    )
    answer = session.execute(query).scalar_one_or_none()
    if answer is None:
        raise NoWordsAvailable(f"No {length}-letter answer words are loaded")
    return answer


def is_valid(session: Session, word: str) -> bool:
    return (
        session.execute(select(WordRow.id).where(WordRow.text == word)).first()
        is not None
    )
