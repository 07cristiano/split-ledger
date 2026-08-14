"""Small password helpers for the local demo application."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        encoded_salt, encoded_hash = stored_hash.split("$", maxsplit=1)
        salt = base64.b64decode(encoded_salt)
        expected = base64.b64decode(encoded_hash)
    except (ValueError, UnicodeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(actual, expected)
