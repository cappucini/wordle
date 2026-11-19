"""app/security.py: password hashing and sign-in tokens."""

import re

import pytest

from app.security import hash_password, hash_token, new_token, verify_password

PASSWORD = "correct horse battery staple"


# ---------- passwords ----------


def test_correct_password_verifies():
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


@pytest.mark.parametrize(
    "attempt",
    [
        pytest.param("wrong password", id="different password"),
        pytest.param("", id="empty"),
        pytest.param(PASSWORD.upper(), id="different case"),
        pytest.param(PASSWORD + " ", id="trailing space"),
        pytest.param(PASSWORD[:-1], id="one character short"),
    ],
)
def test_wrong_password_does_not_verify(attempt):
    assert verify_password(attempt, hash_password(PASSWORD)) is False


def test_hash_has_the_stored_format():
    # scheme $ 16-byte salt as hex $ 32-byte key as hex
    assert re.fullmatch(r"scrypt\$[0-9a-f]{32}\$[0-9a-f]{64}", hash_password(PASSWORD))


def test_hash_fits_the_database_column():
    # users.password_hash is String(200)
    assert len(hash_password("p" * 128)) <= 200


def test_hash_does_not_contain_the_password():
    assert PASSWORD not in hash_password(PASSWORD)


def test_same_password_hashes_differently_each_time():
    # a fresh random salt per hash, so equal passwords are not visible in the database
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)

    assert first != second
    assert verify_password(PASSWORD, first)
    assert verify_password(PASSWORD, second)


def test_passwords_with_non_ascii_characters_work():
    password = "pässwörd \U0001f511"
    assert verify_password(password, hash_password(password))
    assert not verify_password("passwrd", hash_password(password))


@pytest.mark.parametrize(
    "stored_hash",
    [
        pytest.param("", id="empty"),
        pytest.param("not a hash", id="no separators"),
        pytest.param("scrypt$abcd", id="too few parts"),
        pytest.param("scrypt$00$00$00", id="too many parts"),
        pytest.param("scrypt$zz$zz", id="salt and key are not hex"),
        pytest.param("bcrypt$00$00", id="unknown scheme"),
        pytest.param(PASSWORD, id="the password itself stored unhashed"),
    ],
)
def test_malformed_stored_hash_is_refused_without_an_error(stored_hash):
    assert verify_password(PASSWORD, stored_hash) is False


def test_tampered_hash_does_not_verify():
    scheme, salt, key = hash_password(PASSWORD).split("$")
    flipped = "0" if key[0] != "0" else "1"

    assert verify_password(PASSWORD, f"{scheme}${salt}${flipped}{key[1:]}") is False


# ---------- tokens ----------


def test_tokens_are_long_and_safe_to_put_in_a_cookie():
    token = new_token()

    # 32 random bytes are 43 characters in URL-safe base64
    assert len(token) >= 43
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)


def test_tokens_do_not_repeat():
    tokens = {new_token() for _ in range(1000)}
    assert len(tokens) == 1000


def test_hash_token_is_sha256_hex():
    # a published SHA-256 test vector, so this fails if the algorithm is ever swapped
    assert (
        hash_token("abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_hash_token_is_stable_and_fits_the_database_column():
    token = new_token()

    # the same token must always find the same auth_sessions row (token_hash is String(64))
    assert hash_token(token) == hash_token(token)
    assert len(hash_token(token)) == 64
    assert hash_token(token) != token


def test_different_tokens_hash_differently():
    assert hash_token(new_token()) != hash_token(new_token())
