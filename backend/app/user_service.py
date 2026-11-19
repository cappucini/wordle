"""Accounts and sign-ins: the logic behind the routes in app/api/v1/users.py.

How the two files work together
-------------------------------
# users.py, a separate file, is the HTTP layer. It contains the route handlers, which receive the requests
# the frontend sends, call a function here, and build the response.

This file, user_service.py, knows nothing about HTTP: it never sees a request, a cookie or a status
code. It takes plain values, talks to the database, and returns plain values or raises one
of the errors from app/domain/errors.py (main.py turns those into 401 and 409 responses).

    Route in users.py                 calls here              then users.py...
    --------------------------------  ----------------------  ---------------------------------
    POST   /api/v1/users              register()              puts the session token in a
                                                              cookie, returns user + CSRF token
    POST   /api/v1/sessions           login()                 same as above
    DELETE /api/v1/sessions/current   logout()                clears the cookie, returns 204
    GET    /api/v1/users/me           get_auth_session() *    returns user + CSRF token

    * through the get_auth_session dependency in app/api/v1/auth.py. That dependency reads
      the token from the cookie and passes it to get_auth_session() below. Every game route
      uses it too, which is how each request finds out who is signed in.

register() and login() return three things, and users.py sends each to a different place:
  - the user        -> the JSON response body
  - the session token -> an HttpOnly cookie (set_session_cookie in auth.py)
  - the CSRF token  -> the JSON response body, for the page to send back in a header
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import AuthSessionRow, UserRow
from app.domain.errors import InvalidCredentials, NotAuthenticated, UsernameTaken
from app.domain.rules import SESSION_DAYS, SESSION_RENEW_AFTER_DAYS
from app.security import hash_password, hash_token, new_token, verify_password

# Checked when the username doesn't exist, so a wrong username takes as long to reject
# as a wrong password and the response time doesn't reveal which usernames are real.
_DUMMY_HASH = hash_password("not a real password")


# Called by: the `register` route (POST /api/v1/users).
# users.py has already validated the username and password shapes with CredentialsRequest,
# and lowercased the username, before this runs.
def register(
    session: Session, username: str, password: str
) -> tuple[UserRow, str, str]:
    """Create an account and sign it in.

    Returns the user, the session token (for the cookie) and the CSRF token (for the page).
    """
    # raised errors travel up through users.py untouched; main.py answers 409 USERNAME_TAKEN
    if _find_user(session, username) is not None:
        raise UsernameTaken(f"The username '{username}' is already taken")

    # only the hash is stored; the password itself is never written anywhere
    user = UserRow(username=username, password_hash=hash_password(password))
    # we tell the session we want it saved
    session.add(user)
    try:
        # try to send the insert
        session.flush()
    except IntegrityError:
        # two people registered the same name at the same moment; the database's
        # unique rule on username let only one through
        session.rollback()
        raise UsernameTaken(f"The username '{username}' is already taken") from None

    # a new account is signed in straight away, so the route can set the cookie at once
    token, csrf_token = _start_session(session, user)
    session.commit()
    return user, token, csrf_token


# Called by: the `login` route (POST /api/v1/sessions).
def login(session: Session, username: str, password: str) -> tuple[UserRow, str, str]:
    """Check a username and password, and start a new sign-in.

    Returns the same three values as register(), which users.py handles the same way.
    """
    user = _find_user(session, username)
    stored_hash = user.password_hash if user is not None else _DUMMY_HASH
    password_matches = verify_password(password, stored_hash)
    if user is None or not password_matches:
        # one message for both cases, so it doesn't reveal whether the username exists.
        # main.py answers 401 INVALID_CREDENTIALS
        raise InvalidCredentials("Wrong username or password")

    # Tidy up while we are here: this user's sign-ins that have already expired can never be
    # used again. Without this they would stay in the table for good, since an expired
    # session is otherwise only removed when someone tries to use it.
    session.execute(
        delete(AuthSessionRow).where(
            AuthSessionRow.user_id == user.id,
            AuthSessionRow.expires_at <= datetime.now(timezone.utc),
        )
    )
    token, csrf_token = _start_session(session, user)
    session.commit()
    return user, token, csrf_token


# Called by: the `logout` route (DELETE /api/v1/sessions/current).
# users.py gets `token` from the request's cookie (get_token in auth.py) and passes it in.
# Deleting the row is what ends the sign-in; users.py then also clears the cookie.
def logout(session: Session, token: str) -> None:
    session.execute(
        delete(AuthSessionRow).where(AuthSessionRow.token_hash == hash_token(token))
    )
    session.commit()


# Called by: the get_auth_session dependency in auth.py, on every request that needs a
# signed-in user. That covers GET /api/v1/users/me in users.py and all the game routes.
# The row it returns gives the caller both the user (auth_session.user) and the CSRF token
# to compare against (auth_session.csrf_token, used by require_csrf in auth.py).
def get_auth_session(session: Session, token: str) -> AuthSessionRow:
    """The sign-in a session token belongs to. Raises NotAuthenticated if it isn't valid."""
    # sessions are looked up by the token's hash, because only the hash is stored
    auth_session = session.get(AuthSessionRow, hash_token(token))
    if auth_session is None:
        raise NotAuthenticated("Sign in to continue")
    if auth_session.expires_at <= datetime.now(timezone.utc):
        # an expired sign-in is removed the first time someone tries to use it
        session.delete(auth_session)
        session.commit()
        raise NotAuthenticated("Your sign-in has expired. Sign in again")
    return auth_session


# Called by: the get_auth_session dependency in auth.py, straight after the function above.
def renew_session_if_due(session: Session, auth_session: AuthSessionRow) -> bool:
    """Push a sign-in that is being used out to the full SESSION_DAYS from now.

    A player who keeps playing stays signed in; one who stops is signed out SESSION_DAYS
    after their last visit. Returns True if the expiry was moved, so the caller can renew
    the browser's cookie to match. Does nothing if it was already extended (or created)
    within the last SESSION_RENEW_AFTER_DAYS.
    """
    now = datetime.now(timezone.utc)
    full_length = timedelta(days=SESSION_DAYS)
    time_since_last_extended = full_length - (auth_session.expires_at - now)
    if time_since_last_extended < timedelta(days=SESSION_RENEW_AFTER_DAYS):
        return False
    auth_session.expires_at = now + full_length
    session.commit()
    return True


# --- helpers used only inside this file (the leading underscore marks them as private) ---

# Run DB query on DB and give back the results as user row, taking the first one if it exists
def _find_user(session: Session, username: str) -> UserRow | None:
    return session.scalars(select(UserRow).where(UserRow.username == username)).first()


# Used by register() and login(). Adds the session row but does not commit:
# the caller commits, so the user and their first session are saved together or not at all.
def _start_session(session: Session, user: UserRow) -> tuple[str, str]:
    token = new_token()  # goes in the HttpOnly cookie; the page never sees it
    csrf_token = new_token()  # given to the page, which sends it back in a header
    session.add(
        AuthSessionRow(
            token_hash=hash_token(token),
            user=user,
            expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS),
            csrf_token=csrf_token,
        )
    )
    return token, csrf_token
