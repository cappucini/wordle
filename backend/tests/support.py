"""Shared by the test layers that talk to the API: the known words, and a signed-in player."""

from fastapi.testclient import TestClient

# ---- the words in tests/words/ ----
# One answer per length, so the answer to any new game is known in advance.
ANSWERS = {5: "crane", 6: "planet", 7: "kitchen", 8: "absolute"}

# Six different valid 5-letter guesses that are not the answer: enough to lose a game.
WRONG_5 = ["slate", "react", "nacre", "eerie", "elect", "moist"]

# A valid guess that is not the answer, for each length.
WRONG = {5: "slate", 6: "garden", 7: "chicken", 8: "notebook"}

# Five letters, but not in the word list.
NOT_A_WORD = "zzzzz"

PASSWORD = "correct horse battery"

API = "/api/v1"
CSRF_HEADER = "X-CSRF-Token"
SESSION_COOKIE = "wordle_session"


class Player:
    """A signed-in user with their own HTTP client, so each player has their own cookies.

    The helper methods send the CSRF header the way the frontend does. Tests that need to
    leave it out, or send a wrong one, use `player.client` directly.
    """

    def __init__(self, client: TestClient, username: str, password: str, auth_body: dict):
        self.client = client
        self.username = username
        self.password = password
        self.id = auth_body["user"]["id"]
        self.csrf_token = auth_body["csrf_token"]

    @property
    def csrf(self) -> dict:
        return {CSRF_HEADER: self.csrf_token}

    def get(self, path: str, **kwargs):
        return self.client.get(API + path, **kwargs)

    def post(self, path: str, json=None):
        return self.client.post(API + path, json=json, headers=self.csrf)

    def delete(self, path: str):
        return self.client.delete(API + path, headers=self.csrf)

    # ---- shortcuts for arranging a test; they fail loudly if the setup step itself breaks ----

    def create_game(self, word_length: int = 5) -> dict:
        response = self.post("/games", json={"word_length": word_length})
        assert response.status_code == 201, response.text
        return response.json()

    def join(self, game_id: str):
        return self.post(f"/games/{game_id}/players")

    def guess(self, game_id: str, word: str):
        return self.post(f"/games/{game_id}/guesses", json={"word_guessed": word})

    def game(self, game_id: str) -> dict:
        response = self.get(f"/games/{game_id}")
        assert response.status_code == 200, response.text
        return response.json()
