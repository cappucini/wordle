from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app import user_service
from app.db import UserRow, get_session
from app.domain.errors import NotAuthenticated

BEARER_PREFIX = "Bearer "


def get_token(authorization: str | None = Header(default=None)) -> str:
    """Reads the sign-in token from the request's `Authorization: Bearer <token>` header."""
    if authorization is None or not authorization.startswith(BEARER_PREFIX):
        raise NotAuthenticated("Sign in to continue")
    return authorization[len(BEARER_PREFIX) :].strip()


def get_current_user(
    token: str = Depends(get_token), session: Session = Depends(get_session)
) -> UserRow:
    """The one place that answers "who is making this request?".

    Routes that need a signed-in user ask for it with Depends(get_current_user).
    """
    return user_service.get_user_for_token(session, token)
