"""app/api/v1/pagination.py: the opaque cursor for the games list."""

import base64
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.api.v1.pagination import InvalidCursor, decode_cursor, encode_cursor

CREATED_AT = datetime(2026, 11, 18, 9, 30, 15, 123456, tzinfo=timezone.utc)
GAME_ID = UUID("3f2b8c1e-0000-4000-8000-000000000001")


def as_cursor(raw: bytes | str) -> str:
    """Wraps text the way a real cursor is wrapped, to test what is inside it."""
    if isinstance(raw, str):
        raw = raw.encode()
    return base64.urlsafe_b64encode(raw).decode()


def test_cursor_round_trip_returns_the_same_position():
    assert decode_cursor(encode_cursor(CREATED_AT, GAME_ID)) == (CREATED_AT, GAME_ID)


def test_cursor_keeps_microseconds():
    # two games created in the same second must still be told apart
    earlier = CREATED_AT
    later = CREATED_AT + timedelta(microseconds=1)

    assert decode_cursor(encode_cursor(earlier, GAME_ID))[0] < decode_cursor(
        encode_cursor(later, GAME_ID)
    )[0]


def test_cursor_keeps_the_time_zone():
    plus_two = timezone(timedelta(hours=2))
    created_at = datetime(2026, 11, 18, 11, 30, tzinfo=plus_two)

    decoded, _ = decode_cursor(encode_cursor(created_at, GAME_ID))

    assert decoded == created_at
    assert decoded.utcoffset() == timedelta(hours=2)


def test_cursor_is_safe_to_put_in_a_url():
    for _ in range(50):
        cursor = encode_cursor(CREATED_AT, uuid4())
        assert re.fullmatch(r"[A-Za-z0-9_=-]+", cursor)


def test_different_positions_give_different_cursors():
    assert encode_cursor(CREATED_AT, GAME_ID) != encode_cursor(CREATED_AT, uuid4())
    assert encode_cursor(CREATED_AT, GAME_ID) != encode_cursor(
        CREATED_AT + timedelta(seconds=1), GAME_ID
    )


@pytest.mark.parametrize(
    "cursor",
    [
        pytest.param("", id="empty"),
        pytest.param("abc", id="base64 with bad padding"),
        pytest.param("!!! not base64 !!!", id="not base64"),
        pytest.param("éè", id="non-ASCII text"),
        pytest.param(as_cursor(b"\xff\xfe\xfd"), id="decodes to bytes that are not text"),
        pytest.param(as_cursor("no separator"), id="no separator"),
        pytest.param(as_cursor(f"{CREATED_AT.isoformat()}|{GAME_ID}|extra"), id="too many parts"),
        pytest.param(as_cursor(f"yesterday|{GAME_ID}"), id="bad date"),
        pytest.param(as_cursor(f"{CREATED_AT.isoformat()}|not-a-uuid"), id="bad game id"),
        pytest.param(as_cursor(f"|{GAME_ID}"), id="missing date"),
        pytest.param(as_cursor(f"{CREATED_AT.isoformat()}|"), id="missing game id"),
        pytest.param(as_cursor("'; DROP TABLE games; --|x"), id="SQL-shaped text"),
    ],
)
def test_cursor_this_server_did_not_produce_raises_invalid_cursor(cursor):
    # InvalidCursor becomes a 422 in main.py; any other exception would be a 500
    with pytest.raises(InvalidCursor):
        decode_cursor(cursor)
