from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.config import router as config_router
from app.api.v1.games import router as games_router

app = FastAPI()
ROUTERS = [config_router, games_router]
# register router with the app
for router in ROUTERS:
    app.include_router(router)

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