"""Symmetric encryption helpers for user-stored secrets (API keys).

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from SECRET_KEY.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from backend.config import SECRET_KEY


def _derive_fernet_key() -> bytes:
    """Derive a 32-byte URL-safe-base64 Fernet key from SECRET_KEY."""
    digest = hashlib.sha256(SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_fernet_key())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return a URL-safe base64 token."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(token: str) -> str:
    """Decrypt a Fernet token back to plaintext. Raises ValueError on failure."""
    try:
        return _fernet.decrypt(token.encode()).decode()
    except (InvalidToken, Exception) as exc:
        raise ValueError("Failed to decrypt stored value") from exc
