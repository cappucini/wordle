from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.config import router as config_router
from app.api.v1.games import router as games_router

from contextlib import asynccontextmanager
from app.db import create_tables, SessionLocal
from fastapi import Request
from fastapi.responses import JSONResponse
from app.words.seed import seed_words_if_empty

from app.domain.errors import GameNotFound, GameOver, InvalidGuess
from fastapi.exceptions import RequestValidationError

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    with SessionLocal() as session:
        seed_words_if_empty(session)
    yield


app = FastAPI(lifespan=lifespan)
# create_tables()
ROUTERS = [config_router, games_router]
# register router with the app
for router in ROUTERS:
    app.include_router(router)

# Additional handler that replaes built-in validation error response with my own
# every error will have {"code": ..., "detail": "text"} so frontend can parse easier
@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0]
    field = first_error["loc"][-1]          # the field name, such as "word_length"
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


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
