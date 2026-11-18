"""Password hashing and sign-in tokens, using only Python's standard library.

Passwords are never stored. What is stored is a scrypt hash with a random salt per user,
so two users with the same password get different hashes, and a leaked database does not
reveal the passwords.

A sign-in token is a long random string given to the browser. The database keeps only its
SHA-256 hash, so a leaked database cannot be used to act as a signed-in user either.
"""

import hashlib
import hmac
import secrets

# scrypt cost settings: deliberately slow to make guessing passwords expensive
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LENGTH = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = _scrypt(password, salt)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, salt_hex, key_hex = stored_hash.split("$")
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    # compare_digest takes the same time whether or not the values match
    return hmac.compare_digest(_scrypt(password, salt), expected_key)


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=KEY_LENGTH
    )


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
