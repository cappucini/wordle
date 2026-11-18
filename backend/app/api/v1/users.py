from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import user_service
from app.api.v1.auth import get_current_user, get_token
from app.api.v1.schemas import AuthResponse, CredentialsRequest, UserResponse
from app.db import UserRow, get_session

router = APIRouter(prefix="/api/v1", tags=["users"])


# Create an account. The new user is signed in straight away, so the response
# carries a token as well as the user.
@router.post("/users", status_code=201, response_model=AuthResponse)
def register(body: CredentialsRequest, session: Session = Depends(get_session)):
    user, token = user_service.register(session, body.username, body.password)
    return AuthResponse(user=UserResponse.from_row(user), token=token)


@router.get("/users/me", response_model=UserResponse)
def read_current_user(user: UserRow = Depends(get_current_user)):
    return UserResponse.from_row(user)


# Signing in creates a session, and signing out deletes it,
# so they are POST and DELETE on a "sessions" resource.
@router.post("/sessions", status_code=201, response_model=AuthResponse)
def login(body: CredentialsRequest, session: Session = Depends(get_session)):
    user, token = user_service.login(session, body.username, body.password)
    return AuthResponse(user=UserResponse.from_row(user), token=token)


@router.delete("/sessions/current", status_code=204)
def logout(token: str = Depends(get_token), session: Session = Depends(get_session)):
    user_service.logout(session, token)
    return Response(status_code=204)
