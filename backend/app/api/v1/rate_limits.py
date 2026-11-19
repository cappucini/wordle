"""The limits on log-in and sign-up attempts, and the calls the routes in users.py make.

Always on
---------
  - Failed log-ins for one username: stops one account's password being guessed.

On only when RATE_LIMIT_BY_ADDRESS=true
---------------------------------------
  - Failed log-ins from one network address: stops one machine guessing across many accounts.
  - Accounts created from one address: stops one machine filling the database with accounts.
  - Sign-ups refused because the username was taken, from one address: stops the sign-up
    form being used to find out which usernames exist.

These three count by the address a request comes from, so they only make sense where the
backend can tell visitors apart. Often it cannot: behind Docker's network (how this project
runs) or behind a reverse proxy, every request appears to come from the same address. Counted
that way, one visitor's wrong passwords would lock out everybody. So they are off by
default, and are for a deployment where each visitor's own address reaches the backend.

Being over a limit answers 429 TOO_MANY_ATTEMPTS (see main.py) until enough time has passed.
The numbers are in app/domain/rules.py; each can be overridden by an environment variable
of the same name (see limit_from_environment below).

How an attempt is counted
-------------------------
Every attempt is counted *before* it is carried out (begin_login, begin_signup), and taken
back afterwards if it turns out not to be the kind being limited. Counting first is what
makes the limits hold when many requests arrive at the same instant.

Thing to know: someone who knows a username can keep it over its limit and so keep that
player from logging in. They cannot end a session the player already has.
"""

import os

from fastapi import Request

from app.domain.errors import TooManyAttempts
from app.domain.rules import (
    MAX_FAILED_LOGINS_PER_ADDRESS,
    MAX_FAILED_LOGINS_PER_USERNAME,
    MAX_REFUSED_SIGNUPS_PER_ADDRESS,
    MAX_SIGNUPS_PER_ADDRESS,
    RATE_LIMIT_WINDOW_SECONDS,
)
from app.rate_limit import AttemptLimiter

def setting_is_on(name: str, environ=os.environ) -> bool:
    return environ.get(name, "false").strip().lower() == "true"


# Whether to count by network address at all. Read once at start-up.
LIMIT_BY_ADDRESS = setting_is_on("RATE_LIMIT_BY_ADDRESS")


def limit_from_environment(name: str, default: int, environ=os.environ) -> int:
    """A limit's number: the environment variable of that name if set, otherwise the default.

    The defaults are what the app runs with. The setting exists for deployments that need
    different numbers, and for the browser tests, which create more accounts from one
    address in a few seconds than any real visitor would. A value that is not a positive
    whole number stops the server from starting, rather than quietly running unlimited.
    """
    raw = environ.get(name)
    if raw is None:
        return default
    if not raw.isdecimal() or int(raw) < 1:
        raise ValueError(f"{name} must be a positive whole number, not {raw!r}")
    return int(raw)


def _limiter(name: str, default: int) -> AttemptLimiter:
    return AttemptLimiter(limit_from_environment(name, default), RATE_LIMIT_WINDOW_SECONDS)


failed_logins_by_username = _limiter(
    "MAX_FAILED_LOGINS_PER_USERNAME", MAX_FAILED_LOGINS_PER_USERNAME
)
failed_logins_by_address = _limiter(
    "MAX_FAILED_LOGINS_PER_ADDRESS", MAX_FAILED_LOGINS_PER_ADDRESS
)
signups_by_address = _limiter("MAX_SIGNUPS_PER_ADDRESS", MAX_SIGNUPS_PER_ADDRESS)
refused_signups_by_address = _limiter(
    "MAX_REFUSED_SIGNUPS_PER_ADDRESS", MAX_REFUSED_SIGNUPS_PER_ADDRESS
)

ALL_LIMITERS = [
    failed_logins_by_username,
    failed_logins_by_address,
    signups_by_address,
    refused_signups_by_address,
]


def client_address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _count_under_both(
    first: AttemptLimiter, first_key: str, second: AttemptLimiter, second_key: str
) -> None:
    """Counts one attempt under two limits, or raises TooManyAttempts and counts under neither."""
    seconds = first.attempt(first_key)
    if seconds > 0:
        raise TooManyAttempts(seconds)
    seconds = second.attempt(second_key)
    if seconds > 0:
        first.forgive(first_key)  # refused by the second limit, so it was not an attempt
        raise TooManyAttempts(seconds)


# ---- log-in ----


def begin_login(username: str, address: str) -> None:
    """Call before checking a password. Raises TooManyAttempts when over a limit.

    Counts this attempt as a failed log-in straight away. If the password turns out to be
    wrong there is nothing more to do; if it is right, call login_succeeded.
    """
    if LIMIT_BY_ADDRESS:
        _count_under_both(
            failed_logins_by_username, username, failed_logins_by_address, address
        )
        return
    seconds = failed_logins_by_username.attempt(username)
    if seconds > 0:
        raise TooManyAttempts(seconds)


def login_succeeded(username: str, address: str) -> None:
    # The right password proves this is the account's owner, so their earlier typos stop
    # counting too. For the address only this one attempt is taken back: one good log-in
    # must not excuse guesses made at other accounts from the same machine.
    failed_logins_by_username.clear(username)
    if LIMIT_BY_ADDRESS:
        failed_logins_by_address.forgive(address)


# ---- sign-up (limited by address only, so these do nothing unless that is switched on) ----


def begin_signup(address: str) -> None:
    """Call before creating an account. Raises TooManyAttempts when over a limit.

    Counts this attempt both as an account created and as a refused sign-up. Afterwards
    call signup_succeeded or signup_refused, which takes back the one that did not happen.
    """
    if LIMIT_BY_ADDRESS:
        _count_under_both(
            signups_by_address, address, refused_signups_by_address, address
        )


def signup_succeeded(address: str) -> None:
    if LIMIT_BY_ADDRESS:
        refused_signups_by_address.forgive(address)


def signup_refused(address: str) -> None:
    if LIMIT_BY_ADDRESS:
        signups_by_address.forgive(address)
