"""The backend's starting point: builds the FastAPI app, plugs in the routes, and turns the
game's own errors (game not found, invalid guess, and so on) into JSON error responses.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.auth import renew_session_cookie
from app.api.v1.config import router as config_router
from app.api.v1.game_socket import router as game_socket_router
from app.api.v1.games import router as games_router
from app.api.v1.origins import ALLOWED_ORIGINS
from app.api.v1.pagination import InvalidCursor
from app.api.v1.users import router as users_router
from app.db import SessionLocal, create_tables
from app.domain.errors import (
    CsrfCheckFailed,
    GameFull,
    GameNotFound,
    GameOver,
    InvalidCredentials,
    InvalidGuess,
    NotAPlayer,
    NotAuthenticated,
    NoWordsAvailable,
    TooManyAttempts,
    UsernameTaken,
)
from app.words.seed import seed_words_if_empty

logger = logging.getLogger(__name__)


# @asynccontextmanager turns a function with one `yield` into something FastAPI can
# enter when the server starts and leave when it stops.
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts: creates the tables and loads the word lists.

    The code before the `yield` runs at start-up. Anything after it would run at
    shutdown; there is nothing to do then.
    """
    create_tables()
    with SessionLocal() as session:
        seed_words_if_empty(session)
    yield


app = FastAPI(lifespan=lifespan)
ROUTERS = [config_router, games_router, game_socket_router, users_router]
# register router with the app
for router in ROUTERS:
    # attach API routes defined in router files
    app.include_router(router)

# Then, registers multiple exception handlers of what to do for each error type
# @app.exception_handler(X) means: when a route raises X, call the function below and
# send what it returns as the response.

# Handler that manages what happens if words table is empty, words are cleared by hand while server is running (TRUNCATE Words);
# or answers_N.txt file is empty or missing
@app.exception_handler(NoWordsAvailable)
def handle_no_words(request: Request, exc: NoWordsAvailable):
    return JSONResponse(
        status_code=503, content={"code": "NO_WORDS_AVAILABLE", "detail": str(exc)}
    )

# A ?cursor= value on the games list that this server didn't produce
@app.exception_handler(InvalidCursor)
def handle_invalid_cursor(request: Request, exc: InvalidCursor):
    return JSONResponse(
        status_code=422, content={"code": "INVALID_CURSOR", "detail": str(exc)}
    )

# Additional handler that replaces built-in validation error response with my own
# every error will have {"code": ..., "detail": "text"} so frontend can parse easier
@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0]
    field = first_error["loc"][-1]          # the field name, such as "word_length"
    if not isinstance(field, str):
        # malformed JSON reports a character position here instead of a field name
        field = "body"
    message = first_error["msg"]            # such as "Input should be less than or equal to 8"
    return JSONResponse(
        status_code=422,
        content={"code": "INVALID_REQUEST", "detail": f"{field}: {message}"},
    )

# Errors the framework raises by itself, before any route runs: an address that does not
# exist (404), a method the address does not accept (405), a body that cannot be read (400).
# Left alone they would carry only "detail"; this gives them a "code" like every other error.
_FRAMEWORK_ERROR_CODES = {400: "BAD_REQUEST", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


@app.exception_handler(StarletteHTTPException)
def handle_framework_error(request: Request, exc: StarletteHTTPException):
    """Answers with the framework's own status, in the {"code", "detail"} shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            # a status not listed above still gets a code, built from its number
            "code": _FRAMEWORK_ERROR_CODES.get(exc.status_code, f"HTTP_{exc.status_code}"),
            "detail": exc.detail,
        },
        # keeps headers the framework set, such as Allow on a 405
        headers=exc.headers,
    )


@app.exception_handler(GameNotFound)
def handle_game_not_found(request: Request, exc: GameNotFound):
    """Answers 404 when no game has the requested id."""
    return JSONResponse(
        status_code=404, content={"code": "GAME_NOT_FOUND", "detail": str(exc)}
    )


@app.exception_handler(GameOver)
def handle_game_over(request: Request, exc: GameOver):
    """Answers 409 for a guess at, or an attempt to join, a game that has finished."""
    return JSONResponse(
        status_code=409, content={"code": "GAME_OVER", "detail": str(exc)}
    )


@app.exception_handler(InvalidGuess)
def handle_invalid_guess(request: Request, exc: InvalidGuess):
    """Answers 422 for a guess of the wrong length or one not in the word list."""
    return JSONResponse(
        status_code=422, content={"code": "INVALID_GUESS", "detail": str(exc)}
    )


# --- accounts and multiplayer ---

# no sign-in token, or one that is unknown or expired
@app.exception_handler(NotAuthenticated)
def handle_not_authenticated(request: Request, exc: NotAuthenticated):
    return JSONResponse(
        status_code=401, content={"code": "NOT_AUTHENTICATED", "detail": str(exc)}
    )


@app.exception_handler(InvalidCredentials)
def handle_invalid_credentials(request: Request, exc: InvalidCredentials):
    """Answers 401 for a log-in with the wrong username or password."""
    return JSONResponse(
        status_code=401, content={"code": "INVALID_CREDENTIALS", "detail": str(exc)}
    )


@app.exception_handler(UsernameTaken)
def handle_username_taken(request: Request, exc: UsernameTaken):
    """Answers 409 for a sign-up with a username that already exists."""
    return JSONResponse(
        status_code=409, content={"code": "USERNAME_TAKEN", "detail": str(exc)}
    )


# signed in, but not one of this game's players
@app.exception_handler(NotAPlayer)
def handle_not_a_player(request: Request, exc: NotAPlayer):
    return JSONResponse(
        status_code=403, content={"code": "NOT_A_PLAYER", "detail": str(exc)}
    )


# a request that changes something, without the session's CSRF token
@app.exception_handler(CsrfCheckFailed)
def handle_csrf_check_failed(request: Request, exc: CsrfCheckFailed):
    return JSONResponse(
        status_code=403, content={"code": "CSRF_CHECK_FAILED", "detail": str(exc)}
    )


# too many log-in or sign-up attempts in the last few minutes
@app.exception_handler(TooManyAttempts)
def handle_too_many_attempts(request: Request, exc: TooManyAttempts):
    return JSONResponse(
        status_code=429,
        content={"code": "TOO_MANY_ATTEMPTS", "detail": str(exc)},
        # the standard header telling a client how many seconds to wait
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


@app.exception_handler(GameFull)
def handle_game_full(request: Request, exc: GameFull):
    """Answers 409 when joining a game that already has the most players allowed."""
    return JSONResponse(
        status_code=409, content={"code": "GAME_FULL", "detail": str(exc)}
    )


# Anything that goes wrong without one of the handlers above: a bug, or the database being
# unreachable. The client gets the same {"code", "detail"} shape as every other error, and
# never the details, which go to the server log instead.
#
# This must be registered before the CORS middleware below. Middleware added later wraps
# what was added earlier, so CORS ends up outside this and adds its headers to the 500 too.
# Without them the browser hides the response, and the page reports that the server
# cannot be reached.
@app.middleware("http")
async def finish_response(request: Request, call_next):
    try:
        # call_next runs the rest of the app (the route and everything it uses)
        # and gives back the response it produced
        response = await call_next(request)
    except Exception:
        # logger.exception writes the message and the full traceback to the server log
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        response = JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "detail": "Something went wrong on the server"},
        )
    # every response passes through here, which makes it the place to renew the cookie
    # of a sign-in that was extended during this request (see renew_session_cookie)
    renew_session_cookie(request, response)
    return response


# Let the frontend's address call the API. The list of addresses is in app/api/v1/origins.py.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,  # lets the browser send the session cookie with its requests
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """A fixed greeting at the site's root address. Shows that the server is answering."""
    return {"message": "Hello World"}


@app.get("/health")
def health_check():
    """Answers that the server is running. It does not check the database."""
    return {"status": "healthy"}
