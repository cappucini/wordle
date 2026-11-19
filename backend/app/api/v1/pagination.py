"""Cursor pagination for the games list.

A cursor marks a position in the list: "continue after this game". It is built from the last
game on a page (its created_at and id, the two columns the list is sorted by) and handed to the
client as an opaque string. The client sends it back unchanged to get the next page.

Compared with limit/offset, a cursor never skips or repeats a game when new games are created
between two requests, and stays fast however far into the list the client has paged.
"""

import base64
from datetime import datetime
from uuid import UUID


class InvalidCursor(Exception):
    """The ?cursor= value could not be read. main.py answers 422 INVALID_CURSOR."""

    pass


def encode_cursor(created_at: datetime, game_id: UUID) -> str:
    """Packs a game's created_at and id into one string that is safe to put in a URL."""
    raw = f"{created_at.isoformat()}|{game_id}"
    # base64 works on bytes, not text: encode() the text to bytes going in,
    # and decode() the result back to text coming out
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Turns a cursor back into (created_at, id). Raises InvalidCursor if it cannot be read."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_text, id_text = raw.split("|")
        return datetime.fromisoformat(created_at_text), UUID(id_text)
    except ValueError:
        # covers bad base64, a missing separator, a bad date and a bad UUID.
        # `from None` leaves the original ValueError out of the traceback.
        raise InvalidCursor("The cursor is not valid") from None
