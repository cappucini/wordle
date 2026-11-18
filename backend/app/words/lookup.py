from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import WordRow


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
    return session.execute(select(WordRow.id).where(WordRow.text == word)).first() is not None
