import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


@asynccontextmanager
async def lifespan(app: FastAPI):
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

# Handler that manages what happens if words table is empty, words are cleared by hands while server is running (TRUNCATE Words);
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

# Additional handler that replaes built-in validation error response with my own
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

@app.exception_handler(GameNotFound)
def handle_game_not_found(request: Request, exc: GameNotFound):
    return JSONResponse(
        status_code=404, content={"code": "GAME_NOT_FOUND", "detail": str(exc)}
    )


@app.exception_handler(GameOver)
def handle_game_over(request: Request, exc: GameOver):
    return JSONResponse(
        status_code=409, content={"code": "GAME_OVER", "detail": str(exc)}
    )


@app.exception_handler(InvalidGuess)
def handle_invalid_guess(request: Request, exc: InvalidGuess):
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
    return JSONResponse(
        status_code=401, content={"code": "INVALID_CREDENTIALS", "detail": str(exc)}
    )


@app.exception_handler(UsernameTaken)
def handle_username_taken(request: Request, exc: UsernameTaken):
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
async def report_unexpected_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "detail": "Something went wrong on the server"},
        )


# Let the frontend's address call the API. The list of addresses is in app/api/v1/origins.py.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
