from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app import user_service
from app.api.v1 import rate_limits
from app.api.v1.auth import (
    SESSION_COOKIE,
    clear_session_cookie,
    get_auth_session,
    get_token,
    require_csrf,
    set_session_cookie,
)
from app.api.v1.schemas import AuthResponse, CredentialsRequest, UserResponse
from app.db import AuthSessionRow, get_session
from app.domain.errors import UsernameTaken
from app.live import watchers
from app.security import hash_token

router = APIRouter(prefix="/api/v1", tags=["users"])

# Signing in answers with two things:
#  - a cookie holding the session token, which the browser keeps and JavaScript cannot read
#  - the CSRF token in the response body, which the page keeps in memory and sends back
#    in a header on every request that changes something


# Create an account. The new user is signed in straight away.
@router.post("/users", status_code=201, response_model=AuthResponse)
def register(
    body: CredentialsRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    address = rate_limits.client_address(request)
    rate_limits.begin_signup(address)
    try:
        user, token, csrf_token = user_service.register(
            session, body.username, body.password
        )
    except UsernameTaken:
        rate_limits.signup_refused(address)
        raise
    rate_limits.signup_succeeded(address)

    _end_replaced_session(request, session, token)
    set_session_cookie(response, token)
    return AuthResponse(user=UserResponse.from_row(user), csrf_token=csrf_token)


# Who is signed in. The page calls this when it loads: it cannot see the cookie, so this is
# how it finds out whether it is signed in, and how it gets the CSRF token back after a refresh.
@router.get("/users/me", response_model=AuthResponse)
def read_current_user(auth_session: AuthSessionRow = Depends(get_auth_session)):
    return AuthResponse(
        user=UserResponse.from_row(auth_session.user),
        csrf_token=auth_session.csrf_token,
    )


# Signing in creates a session, and signing out deletes it,
# so they are POST and DELETE on a "sessions" resource.
@router.post("/sessions", status_code=201, response_model=AuthResponse)
def login(
    body: CredentialsRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    address = rate_limits.client_address(request)
    # Counted before the password is checked: while over the limit, even the right password
    # is refused, so further guesses learn nothing. A wrong password needs nothing more;
    # the attempt is already counted.
    rate_limits.begin_login(body.username, address)
    user, token, csrf_token = user_service.login(session, body.username, body.password)
    rate_limits.login_succeeded(body.username, address)

    _end_replaced_session(request, session, token)
    set_session_cookie(response, token)
    return AuthResponse(user=UserResponse.from_row(user), csrf_token=csrf_token)


# When a browser that is already signed in signs in again (or creates another account), the
# new cookie replaces the old one. End the old session too, rather than leave it valid on
# the server for up to a week with nothing using it. Only the browser holding a session's
# cookie can end it this way, so one device signing in never signs out another.
def _end_replaced_session(request: Request, session: Session, new_token: str) -> None:
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token is None or old_token == new_token:
        return
    user_service.logout(session, old_token)
    watchers.close_session(hash_token(old_token))


@router.delete(
    "/sessions/current", status_code=204, dependencies=[Depends(require_csrf)]
)
def logout(token: str = Depends(get_token), session: Session = Depends(get_session)):
    user_service.logout(session, token)
    # pages this sign-in had open stop being told about their games
    watchers.close_session(hash_token(token))
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
