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
SCRYPT_N = 2**14  # how much work and memory one hash takes; must be a power of two
SCRYPT_R = 8  # block size; with N it sets the memory used (about 16 MB here)
SCRYPT_P = 1  # how many such rounds are run
KEY_LENGTH = 32  # length of the resulting hash, in bytes


def hash_password(password: str) -> str:
    """Hashes a password with a new random salt.

    Returns "scrypt$<salt>$<hash>" with both parts in hex, so the salt is stored
    alongside the hash it belongs to.
    """
    salt = secrets.token_bytes(16)
    key = _scrypt(password, salt)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """True if the password matches the stored hash. A stored value in the wrong shape
    is answered with False rather than an error."""
    try:
        # split() not giving exactly three parts, and fromhex() on text that is
        # not hex, both raise ValueError
        scheme, salt_hex, key_hex = stored_hash.split("$")
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    # hash the password being tried with the same salt, then compare the two hashes.
    # compare_digest takes the same time whether or not the values match
    return hmac.compare_digest(_scrypt(password, salt), expected_key)


def _scrypt(password: str, salt: bytes) -> bytes:
    """Runs scrypt over the password and salt, with the cost settings above."""
    return hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=KEY_LENGTH
    )


def new_token() -> str:
    """A new random token: 32 random bytes, written with characters safe in cookies and URLs."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """The SHA-256 hash of a token, as 64 hex characters. This is what the database stores."""
    return hashlib.sha256(token.encode()).hexdigest()
