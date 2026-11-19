"""The limits on log-in and sign-up attempts, and the checks the routes in users.py call.

What is limited, and why:

  - Failed log-ins for one username: stops one account's password being guessed.
  - Failed log-ins from one network address: stops one machine guessing across many accounts.
  - Accounts created from one address: stops one machine filling the database with accounts.

Being over a limit answers 429 TOO_MANY_ATTEMPTS (see main.py) until enough time has passed.
The numbers are in app/domain/rules.py.

Things to know:

  - The address is the one the connection comes from. Behind a reverse proxy that is the
    proxy's address for everybody, so the per-address limits would be shared by all users;
    a deployment like that needs the real client address passed through first.
  - Someone who knows a username can keep it over its limit and so keep that player from
    logging in. They cannot end a session the player already has.
"""

from fastapi import Request

from app.domain.errors import TooManyAttempts
from app.domain.rules import (
    MAX_FAILED_LOGINS_PER_ADDRESS,
    MAX_FAILED_LOGINS_PER_USERNAME,
    MAX_SIGNUPS_PER_ADDRESS,
    RATE_LIMIT_WINDOW_SECONDS,
)
from app.rate_limit import AttemptLimiter

failed_logins_by_username = AttemptLimiter(
    MAX_FAILED_LOGINS_PER_USERNAME, RATE_LIMIT_WINDOW_SECONDS
)
failed_logins_by_address = AttemptLimiter(
    MAX_FAILED_LOGINS_PER_ADDRESS, RATE_LIMIT_WINDOW_SECONDS
)
signups_by_address = AttemptLimiter(MAX_SIGNUPS_PER_ADDRESS, RATE_LIMIT_WINDOW_SECONDS)

ALL_LIMITERS = [failed_logins_by_username, failed_logins_by_address, signups_by_address]


def client_address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _require_allowed(limiter: AttemptLimiter, key: str) -> None:
    seconds = limiter.seconds_until_allowed(key)
    if seconds > 0:
        raise TooManyAttempts(seconds)


# ---- log-in ----


def require_login_allowed(username: str, address: str) -> None:
    """Call before checking a password. Raises TooManyAttempts when over a limit."""
    _require_allowed(failed_logins_by_username, username)
    _require_allowed(failed_logins_by_address, address)


def record_failed_login(username: str, address: str) -> None:
    failed_logins_by_username.record(username)
    failed_logins_by_address.record(address)


def record_successful_login(username: str) -> None:
    # The right password proves this is the account's owner, so their earlier typos stop
    # counting. The address's count stays: one good log-in must not excuse guesses at others.
    failed_logins_by_username.clear(username)


# ---- sign-up ----


def require_signup_allowed(address: str) -> None:
    _require_allowed(signups_by_address, address)


def record_signup(address: str) -> None:
    signups_by_address.record(address)
