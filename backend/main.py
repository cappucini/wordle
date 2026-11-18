from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.config import router as config_router
from app.api.v1.games import router as games_router

from contextlib import asynccontextmanager
from app.db import create_tables
from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.errors import GameNotFound, GameOver, InvalidGuess

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield

app = FastAPI(lifespan=lifespan)
# create_tables()
ROUTERS = [config_router, games_router]
# register router with the app
for router in ROUTERS:
    app.include_router(router)
@app.exception_handler(GameNotFound)
def handle_game_not_found(request: Request, exc: GameNotFound):
    return JSONResponse(status_code=404, content={"code": "GAME_NOT_FOUND", "detail": str(exc)})


@app.exception_handler(GameOver)
def handle_game_over(request: Request, exc: GameOver):
    return JSONResponse(status_code=409, content={"code": "GAME_OVER", "detail": str(exc)})


@app.exception_handler(InvalidGuess)
def handle_invalid_guess(request: Request, exc: InvalidGuess):
    return JSONResponse(status_code=422, content={"code": "INVALID_GUESS", "detail": str(exc)})

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