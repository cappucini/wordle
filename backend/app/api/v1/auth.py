"""Sign-in checks shared by the routes: reading and setting the session cookie, finding the
signed-in player for a request, and checking the CSRF token on requests that change data.
"""

import hmac
import os

from fastapi import Cookie, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from app import user_service
from app.db import AuthSessionRow, UserRow, get_session
from app.domain.errors import CsrfCheckFailed, NotAuthenticated
from app.domain.rules import SESSION_DAYS
from app.live import watchers

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
    """Puts the session token in the browser's cookie, to be kept for SESSION_DAYS."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,  # not readable from JavaScript
        samesite="lax",  # not sent on requests that another site makes in the background
        secure=COOKIE_SECURE,
        max_age=SESSION_DAYS * 24 * 60 * 60,  # in seconds
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Tells the browser to delete the session cookie. Used when signing out."""
    response.delete_cookie(key=SESSION_COOKIE, path="/")


def get_token(wordle_session: str | None = Cookie(default=None)) -> str:
    """Reads the session token from the request's cookie."""
    # Cookie(...) makes FastAPI fill this parameter from the cookie with the same name,
    # so the parameter must be spelled like SESSION_COOKIE. No cookie gives None.
    if wordle_session is None:
        raise NotAuthenticated("Sign in to continue")
    return wordle_session


def get_auth_session(
    request: Request,
    # Depends(f) asks FastAPI to call f first and pass its result in as this parameter
    token: str = Depends(get_token),
    session: Session = Depends(get_session),
) -> AuthSessionRow:
    """Finds the sign-in this request belongs to, and keeps it alive while it is in use.

    Raises NotAuthenticated if the cookie is missing, unknown or expired.
    """
    auth_session = user_service.get_auth_session(session, token)
    # A sign-in that is being used is kept alive: once a day its expiry is pushed back out
    # to the full length, and any open live connections are extended to match.
    if user_service.renew_session_if_due(session, auth_session):
        watchers.extend_session(auth_session.token_hash, auth_session.expires_at)
        # The browser's cookie must be renewed too. That is left to renew_session_cookie
        # below, which runs on the way out whatever the route answers.
        # (request.state is a place to keep values for the length of one request)
        request.state.session_token_to_renew = token
    return auth_session


def renew_session_cookie(request: Request, response: Response) -> None:
    """Called by main.py on every response. Re-sends the cookie for a session that was
    extended during this request.

    Done here, on the way out, rather than where the session is extended: a route that
    refuses the request (an invalid guess, say) builds its own error response, and anything
    set earlier would be lost. The server would then have extended the sign-in while the
    browser's cookie kept its old end date.
    """
    # getattr with a default: None when nothing was stored, instead of an error
    token = getattr(request.state, "session_token_to_renew", None)
    if token is None:
        return
    # logging in or out sets or clears the cookie itself; leave that instruction alone
    for header in response.headers.getlist("set-cookie"):
        if header.startswith(SESSION_COOKIE + "="):
            return
    set_session_cookie(response, token)


def get_current_user(
    auth_session: AuthSessionRow = Depends(get_auth_session),
) -> UserRow:
    """The one place that answers "who is making this request?".

    Routes that need a signed-in user ask for it with Depends(get_current_user).
    """
    return auth_session.user


def require_csrf(
    auth_session: AuthSessionRow = Depends(get_auth_session),
    # Header(...) fills this from the X-CSRF-Token header: FastAPI matches the parameter
    # name to the header name, reading underscores as hyphens. No header gives None.
    x_csrf_token: str | None = Header(default=None),
) -> None:
    """Routes that change something add this, to refuse requests another site could forge."""
    expected = auth_session.csrf_token
    if expected is None or x_csrf_token is None:
        raise CsrfCheckFailed("This request is missing its CSRF token")
    # compare_digest takes the same time whether or not the values match, so the time
    # a refusal takes does not hint at how much of a guessed token was right
    # Compared as bytes: compare_digest refuses text containing letters outside plain
    # English (an accented letter, say), and a header can carry anything.
    if not hmac.compare_digest(x_csrf_token.encode(), expected.encode()):
        raise CsrfCheckFailed("This request's CSRF token is not valid")
