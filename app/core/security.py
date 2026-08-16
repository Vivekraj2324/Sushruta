"""
Sushruta — Security Utilities
==============================

Password hashing and JWT token management.

Password hashing:
- bcrypt library directly — industry standard for password storage.
- Passwords are never stored or logged in plaintext.
- bcrypt automatically handles salting (each hash is unique).
- Using bcrypt directly (not passlib) for compatibility with bcrypt 5.x.

JWT tokens:
- HS256 symmetric signing — simple, fast, sufficient for single-service.
- Token contains: sub (doctor_id), email, exp (expiry), iat (issued at).
- 30-minute expiry balances security with clinical workflow usability.
- No refresh tokens in Phase 1 (added in Phase 4).

Interview note:
- "Why bcrypt over argon2?" — bcrypt is battle-tested, widely supported,
  and has predictable performance. argon2 is newer and more configurable
  but adds complexity. For a medical app, reliability > novelty.
- "Why not passlib?" — passlib's bcrypt wrapper has compatibility issues
  with bcrypt 5.x. Using bcrypt directly is simpler and more reliable.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


# ── Password Hashing ─────────────────────────────────────────────


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    Returns a string like: $2b$12$<salt><hash>
    The salt is embedded in the output — no separate storage needed.
    bcrypt.gensalt() generates a random salt with default cost factor 12.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.

    bcrypt.checkpw uses constant-time comparison to prevent timing attacks.
    Returns True if the password matches, False otherwise.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


# ── JWT Token Management ─────────────────────────────────────────


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Parameters
    ----------
    data : dict
        Claims to encode. Must include "sub" (subject = doctor_id)
        and "email" for downstream use.
    expires_delta : timedelta, optional
        Custom expiry. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns
    -------
    str
        Encoded JWT string.

    Token structure:
        {
            "sub": "123",        # doctor_id as string
            "email": "dr@...",   # for display/logging
            "exp": 1700000000,   # expiry timestamp
            "iat": 1699998200    # issued-at timestamp
        }
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": now,
    })

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    """
    Decode and validate a JWT token.

    Returns the payload dict if valid, None if:
    - Signature is invalid (tampered token)
    - Token has expired
    - Token is malformed

    Security note:
    - python-jose automatically checks expiry (exp claim).
    - Signature verification uses the SECRET_KEY.
    - No additional DB lookup here — that happens in dependencies.py.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        return None
