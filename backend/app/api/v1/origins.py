"""The addresses the frontend is served from, and so the only websites allowed to use this API
from a browser.

Used in two places: the CORS settings in main.py (for ordinary requests), and the WebSocket
route in game_socket.py (browsers do not apply CORS to WebSockets, so that route checks the
Origin header itself).
"""

import os

# Vite serves the frontend on port 5173, and moves to 5174 when 5173 is already in use;
# the page can also be opened as 127.0.0.1 instead of localhost. All four are allowed by default.
# Set CORS_ORIGINS (comma-separated) to allow a different frontend address.
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:5174,http://127.0.0.1:5174"
)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
