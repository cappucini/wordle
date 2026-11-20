"""Cursor pagination for the games list.

A cursor marks a position in the list: "continue after this game". It is built from the last
game on a page (its created_at and id, the two columns the list is sorted by) and handed to the
client as an opaque string. The client sends it back unchanged to get the next page.

Compared with limit/offset, a cursor never skips or repeats a game when new games are created
between two requests, and stays fast however far into the list the client has paged.
"""

# base64: turns any bytes into plain letters and digits (and back again)
import base64
# datetime: the type of a game's created_at
from datetime import datetime
# UUID: the type of a game's id
from uuid import UUID


class InvalidCursor(Exception):
    """The ?cursor= value could not be read. main.py answers 422 INVALID_CURSOR."""

    # Lives in this file, not in app/domain/errors.py, because a cursor is about the web
    # (how a list is sent a page at a time), not about the rules of the game.
    # `pass`: the class needs nothing of its own; its name is what main.py looks for.
    pass


# How the two functions below are used (see read_games in games.py):
#   1. The page asks for GET /games. The route returns the newest games and, if there are
#      older ones, a next_cursor made by encode_cursor from the last game on the page.
#   2. The page asks for GET /games?cursor=<that string>. The route hands the string to
#      decode_cursor and gets the (created_at, id) back.
#   3. game_service.list_games uses that pair to fetch only games older than it.


def encode_cursor(created_at: datetime, game_id: UUID) -> str:
    """Packs a game's created_at and id into one string that is safe to put in a URL."""
    # Join the two values into one piece of text with a | between them, for example
    #   "2026-11-19T14:03:27.512345+00:00|3f2b8c1e-..."
    # isoformat() writes the time in the standard form that fromisoformat() reads back.
    # Neither a time nor an id can contain a |, so it is safe to split on later.
    raw = f"{created_at.isoformat()}|{game_id}"
    # Encode that text as base64. The plain text has characters (+ and :) that mean
    # something else inside a URL; the urlsafe kind of base64 uses only characters that
    # do not. It also tells the client this is a token to send back, not to read or edit.
    # It is not a secret: anyone can decode it, and it holds nothing private.
    # base64 works on bytes, not text: encode() the text to bytes going in,
    # and decode() the result back to text coming out
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Turns a cursor back into (created_at, id). Raises InvalidCursor if it cannot be read."""
    # The cursor comes from the URL, so it may be anything at all: one this server made,
    # or something typed in by hand. Each step below can fail on a made-up value, and
    # every one of those failures is a ValueError (or a kind of ValueError).
    try:
        # undo encode_cursor: text -> bytes -> base64-decoded bytes -> the original text
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        # split at the | into exactly two parts; any other number of parts cannot be
        # unpacked into two names, which raises ValueError
        created_at_text, id_text = raw.split("|")
        # turn each part back into its real type; both refuse text in the wrong form
        return datetime.fromisoformat(created_at_text), UUID(id_text)
    except ValueError:
        # covers bad base64, a missing separator, a bad date and a bad UUID.
        # `from None` leaves the original ValueError out of the traceback.
        raise InvalidCursor("The cursor is not valid") from None
