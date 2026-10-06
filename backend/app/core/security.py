"""Password hashing and JWT issuing/validation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

# bcrypt is used directly rather than through passlib: passlib is unmaintained
# and breaks against bcrypt >= 4.1.
BCRYPT_MAX_BYTES = 72

ACCESS = "access"
REFRESH = "refresh"


def _prepare(password: str) -> bytes:
    """bcrypt silently ignores anything past 72 bytes, so truncate explicitly."""
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash in the row; treat as a failed login rather than a 500.
        return False


def _encode(subject: str, role: str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, role: str) -> str:
    return _encode(subject, role, ACCESS, timedelta(minutes=settings.access_token_ttl_minutes))


def create_refresh_token(subject: str, role: str) -> str:
    return _encode(subject, role, REFRESH, timedelta(days=settings.refresh_token_ttl_days))


def decode_token(token: str, expected_type: str = ACCESS) -> dict[str, Any]:
    """Raises jwt exceptions on an invalid, expired or wrong-type token."""
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected a {expected_type} token")
    return payload
