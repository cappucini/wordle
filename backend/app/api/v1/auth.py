import hmac
import os

from fastapi import Cookie, Depends, Header, Response
from sqlalchemy.orm import Session

from app import user_service
from app.db import AuthSessionRow, UserRow, get_session
from app.domain.errors import CsrfCheckFailed, NotAuthenticated
from app.domain.rules import SESSION_DAYS

# How a signed-in browser is recognised:
#
# 1. The session token travels in a cookie marked HttpOnly, so JavaScript on the page cannot
#    read it. A script injected into the page therefore cannot steal the sign-in.
# 2. The browser attaches cookies by itself, to any request for this site, even one started
#    by a different website. So a second secret, the CSRF token, is given to our page, and
#    every request that changes something must carry it in a header. Another website cannot
#    read that value, so it cannot make requests on a signed-in player's behalf.

SESSION_COOKIE = "wordle_session"
CSRF_HEADER = "X-CSRF-Token"

# Browsers only send a "Secure" cookie over HTTPS. Local development uses plain HTTP,
# so this is off by default and must be switched on wherever the site is served over HTTPS.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,  # not readable from JavaScript
        samesite="lax",  # not sent on requests that another site makes in the background
        secure=COOKIE_SECURE,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


def get_token(wordle_session: str | None = Cookie(default=None)) -> str:
    """Reads the session token from the request's cookie."""
    if wordle_session is None:
        raise NotAuthenticated("Sign in to continue")
    return wordle_session


def get_auth_session(
    token: str = Depends(get_token), session: Session = Depends(get_session)
) -> AuthSessionRow:
    return user_service.get_auth_session(session, token)


def get_current_user(
    auth_session: AuthSessionRow = Depends(get_auth_session),
) -> UserRow:
    """The one place that answers "who is making this request?".

    Routes that need a signed-in user ask for it with Depends(get_current_user).
    """
    return auth_session.user


def require_csrf(
    auth_session: AuthSessionRow = Depends(get_auth_session),
    x_csrf_token: str | None = Header(default=None),
) -> None:
    """Routes that change something add this, to refuse requests another site could forge."""
    expected = auth_session.csrf_token
    if expected is None or x_csrf_token is None:
        raise CsrfCheckFailed("This request is missing its CSRF token")
    # compare_digest takes the same time whether or not the values match
    if not hmac.compare_digest(x_csrf_token, expected):
        raise CsrfCheckFailed("This request's CSRF token is not valid")
