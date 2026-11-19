from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app import user_service
from app.api.v1 import rate_limits
from app.api.v1.auth import (
    clear_session_cookie,
    get_auth_session,
    get_token,
    require_csrf,
    set_session_cookie,
)
from app.api.v1.schemas import AuthResponse, CredentialsRequest, UserResponse
from app.db import AuthSessionRow, get_session
from app.domain.errors import InvalidCredentials

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
    rate_limits.require_signup_allowed(address)

    user, token, csrf_token = user_service.register(
        session, body.username, body.password
    )
    # only accounts actually created count towards the limit
    rate_limits.record_signup(address)
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
    # checked before the password is: while over the limit, even the right password is
    # refused, so further guesses learn nothing
    rate_limits.require_login_allowed(body.username, address)

    try:
        user, token, csrf_token = user_service.login(session, body.username, body.password)
    except InvalidCredentials:
        rate_limits.record_failed_login(body.username, address)
        raise
    rate_limits.record_successful_login(body.username)

    set_session_cookie(response, token)
    return AuthResponse(user=UserResponse.from_row(user), csrf_token=csrf_token)


@router.delete(
    "/sessions/current", status_code=204, dependencies=[Depends(require_csrf)]
)
def logout(token: str = Depends(get_token), session: Session = Depends(get_session)):
    user_service.logout(session, token)
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
