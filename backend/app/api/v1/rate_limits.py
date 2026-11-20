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

# os: for reading environment variables (settings given to the server when it starts)
import os

# Request: FastAPI's object for one incoming request; it knows the sender's address
from fastapi import Request

# the error raised when a limit is reached; it carries how many seconds to wait
from app.domain.errors import TooManyAttempts
# the default numbers: how many attempts each limit allows, and over how long
from app.domain.rules import (
    MAX_FAILED_LOGINS_PER_ADDRESS,  # wrong passwords from one address (30)
    MAX_FAILED_LOGINS_PER_USERNAME,  # wrong passwords for one account (10)
    MAX_REFUSED_SIGNUPS_PER_ADDRESS,  # sign-ups refused as "username taken" (30)
    MAX_SIGNUPS_PER_ADDRESS,  # accounts created from one address (20)
    RATE_LIMIT_WINDOW_SECONDS,  # attempts are counted over the last five minutes
)
# the counter itself: it remembers when each key's attempts happened (app/rate_limit.py)
from app.rate_limit import AttemptLimiter

def setting_is_on(name: str, environ=os.environ) -> bool:
    """True if the environment variable is set to "true", in any letter case. Unset is off.

    `environ` is a parameter so a test can pass its own dictionary.
    """
    # get(name, "false"): the variable's value, or "false" if it is not set at all.
    # strip() removes spaces around it and lower() ignores capitals, so " True " is on.
    # Anything other than "true" (such as "yes" or "1") is off.
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
    # the variable's value as text, or None if it is not set
    raw = environ.get(name)
    # not set: use the number from rules.py
    if raw is None:
        return default
    # isdecimal() is True only for text made of digits, so "ten", "-5", "1.5" and ""
    # are all refused here; `int(raw) < 1` then refuses "0"
    if not raw.isdecimal() or int(raw) < 1:
        # !r prints the value in quotes, so a stray space or an empty value is visible
        raise ValueError(f"{name} must be a positive whole number, not {raw!r}")
    # set and valid: use it in place of the default
    return int(raw)


def _limiter(name: str, default: int) -> AttemptLimiter:
    """Builds a limiter with this limit (or its environment override) and the shared window."""
    # an AttemptLimiter takes "how many attempts" and "within how many seconds"
    return AttemptLimiter(limit_from_environment(name, default), RATE_LIMIT_WINDOW_SECONDS)


# The four counters, made once when the server starts and shared by every request.
# Each keeps its own counts, per "key": the first is keyed by username, the other three
# by network address. In each call the text is the environment variable that can override
# the limit, and the second value is the default from rules.py.

# wrong passwords for one account
failed_logins_by_username = _limiter(
    "MAX_FAILED_LOGINS_PER_USERNAME", MAX_FAILED_LOGINS_PER_USERNAME
)
# wrong passwords from one address, across any accounts
failed_logins_by_address = _limiter(
    "MAX_FAILED_LOGINS_PER_ADDRESS", MAX_FAILED_LOGINS_PER_ADDRESS
)
# accounts created from one address
signups_by_address = _limiter("MAX_SIGNUPS_PER_ADDRESS", MAX_SIGNUPS_PER_ADDRESS)
# sign-ups from one address that were refused because the username was taken
refused_signups_by_address = _limiter(
    "MAX_REFUSED_SIGNUPS_PER_ADDRESS", MAX_REFUSED_SIGNUPS_PER_ADDRESS
)

# All four in one list. The tests use it to empty every counter between one test and the next.
ALL_LIMITERS = [
    failed_logins_by_username,
    failed_logins_by_address,
    signups_by_address,
    refused_signups_by_address,
]


def client_address(request: Request) -> str:
    """The network address the request came from, or "unknown" if the server cannot tell."""
    # request.client is the (host, port) the connection came from; the host is the address.
    # It can be None (some test clients and proxies give none), and then every such request
    # shares the one key "unknown".
    return request.client.host if request.client is not None else "unknown"


def _count_under_both(
    first: AttemptLimiter, first_key: str, second: AttemptLimiter, second_key: str
) -> None:
    """Counts one attempt under two limits, or raises TooManyAttempts and counts under neither."""
    # attempt() checks and counts in one step: it returns 0 and counts the attempt if the
    # key is under its limit, or counts nothing and returns how many seconds to wait
    seconds = first.attempt(first_key)
    if seconds > 0:
        # over the first limit: nothing was counted, so there is nothing to undo
        raise TooManyAttempts(seconds)
    # under the first limit, and now counted there; try the second
    seconds = second.attempt(second_key)
    if seconds > 0:
        # over the second limit: undo the count the first limiter just made
        first.forgive(first_key)  # refused by the second limit, so it was not an attempt
        raise TooManyAttempts(seconds)


# ---- log-in ----


def begin_login(username: str, address: str) -> None:
    """Call before checking a password. Raises TooManyAttempts when over a limit.

    Counts this attempt as a failed log-in straight away. If the password turns out to be
    wrong there is nothing more to do; if it is right, call login_succeeded.
    """
    # counting by address is switched on: this attempt counts against the username and
    # against the address, and being over either limit refuses it
    if LIMIT_BY_ADDRESS:
        _count_under_both(
            failed_logins_by_username, username, failed_logins_by_address, address
        )
        return
    # the default: count against the username only
    seconds = failed_logins_by_username.attempt(username)
    if seconds > 0:
        # this username has used up its attempts; main.py turns the error into a 429
        # that tells the page how many seconds to wait
        raise TooManyAttempts(seconds)


def login_succeeded(username: str, address: str) -> None:
    """Call after a correct password. Takes back what begin_login counted."""
    # The right password proves this is the account's owner, so their earlier typos stop
    # counting too. For the address only this one attempt is taken back: one good log-in
    # must not excuse guesses made at other accounts from the same machine.
    # clear() forgets every attempt counted for this username
    failed_logins_by_username.clear(username)
    if LIMIT_BY_ADDRESS:
        # forgive() takes back only the most recent attempt, the one begin_login counted
        failed_logins_by_address.forgive(address)


# ---- sign-up (limited by address only, so these do nothing unless that is switched on) ----


def begin_signup(address: str) -> None:
    """Call before creating an account. Raises TooManyAttempts when over a limit.

    Counts this attempt both as an account created and as a refused sign-up. Afterwards
    call signup_succeeded or signup_refused, which takes back the one that did not happen.
    """
    # Which of the two this attempt will be is not known until the account has been
    # created or refused, so it is counted as both for now. The same address is the key
    # in both counters.
    if LIMIT_BY_ADDRESS:
        _count_under_both(
            signups_by_address, address, refused_signups_by_address, address
        )


def signup_succeeded(address: str) -> None:
    """Call after an account was created. Takes back the refused sign-up begin_signup counted."""
    # the account was created, so it stays counted as a created account;
    # it was not a refused sign-up, so that count is taken back
    if LIMIT_BY_ADDRESS:
        refused_signups_by_address.forgive(address)


def signup_refused(address: str) -> None:
    """Call when the username was taken. Takes back the created account begin_signup counted."""
    # the other way round: it stays counted as a refused sign-up, and the
    # created-account count is taken back because no account was made
    if LIMIT_BY_ADDRESS:
        signups_by_address.forgive(address)
