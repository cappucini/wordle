from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import AuthSessionRow, UserRow
from app.domain.errors import InvalidCredentials, NotAuthenticated, UsernameTaken
from app.domain.rules import SESSION_DAYS
from app.security import hash_password, hash_token, new_token, verify_password

# Checked when the username doesn't exist, so a wrong username takes as long to reject
# as a wrong password and the response time doesn't reveal which usernames are real.
_DUMMY_HASH = hash_password("not a real password")


def register(session: Session, username: str, password: str) -> tuple[UserRow, str]:
    """Create an account and sign it in. Returns the user and a sign-in token."""
    if _find_user(session, username) is not None:
        raise UsernameTaken(f"The username '{username}' is already taken")

    user = UserRow(username=username, password_hash=hash_password(password))
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        # two people registered the same name at the same moment; the database's
        # unique rule on username let only one through
        session.rollback()
        raise UsernameTaken(f"The username '{username}' is already taken") from None

    token = _start_session(session, user)
    session.commit()
    return user, token


def login(session: Session, username: str, password: str) -> tuple[UserRow, str]:
    user = _find_user(session, username)
    stored_hash = user.password_hash if user is not None else _DUMMY_HASH
    password_matches = verify_password(password, stored_hash)
    if user is None or not password_matches:
        # one message for both cases, so it doesn't reveal whether the username exists
        raise InvalidCredentials("Wrong username or password")

    token = _start_session(session, user)
    session.commit()
    return user, token


def logout(session: Session, token: str) -> None:
    session.execute(
        delete(AuthSessionRow).where(AuthSessionRow.token_hash == hash_token(token))
    )
    session.commit()


def get_user_for_token(session: Session, token: str) -> UserRow:
    """The user a sign-in token belongs to. Raises NotAuthenticated if it isn't valid."""
    auth_session = session.get(AuthSessionRow, hash_token(token))
    if auth_session is None:
        raise NotAuthenticated("Sign in to continue")
    if auth_session.expires_at <= datetime.now(timezone.utc):
        session.delete(auth_session)
        session.commit()
        raise NotAuthenticated("Your sign-in has expired. Sign in again")
    return auth_session.user


def _find_user(session: Session, username: str) -> UserRow | None:
    return session.scalars(select(UserRow).where(UserRow.username == username)).first()


def _start_session(session: Session, user: UserRow) -> str:
    token = new_token()
    session.add(
        AuthSessionRow(
            token_hash=hash_token(token),
            user=user,
            expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS),
        )
    )
    return token
