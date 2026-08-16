"""
Sushruta — FastAPI Dependencies
================================

Dependency injection functions used across all protected routes.

The core dependency chain:
  HTTP Request → oauth2_scheme (extract token) → get_current_doctor (validate + query DB) → Route Handler

Design decisions:
- OAuth2PasswordBearer: Standard FastAPI scheme that extracts
  Bearer tokens from the Authorization header automatically.
- get_current_doctor queries the DB on every request. This ensures:
  1. Deactivated doctors are rejected immediately.
  2. Doctor object is always fresh (no stale cache).
  3. The cost is one simple PK query per request — negligible.

Interview note:
- "Why not cache the doctor object?" — In a medical system, account
  deactivation must take effect immediately. Caching would create a
  window where a deactivated doctor could still access data.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.database import get_db
from app.db.models import Doctor

# ── OAuth2 Scheme ────────────────────────────────────────────────
# tokenUrl points to the login endpoint — used by Swagger UI's
# "Authorize" button to fetch tokens interactively.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_doctor(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Doctor:
    """
    Validate JWT token and return the authenticated Doctor object.

    This dependency is injected into every protected route:
        @router.get("/protected")
        async def route(doctor: Doctor = Depends(get_current_doctor)):
            ...

    Flow:
    1. oauth2_scheme extracts Bearer token from Authorization header.
    2. decode_token verifies signature and checks expiry.
    3. Doctor ID extracted from 'sub' claim.
    4. DB query confirms doctor exists and is active.
    5. Doctor ORM object returned for use in the route handler.

    Raises
    ------
    HTTPException 401
        - Token is missing, expired, or has invalid signature.
        - Token payload is missing 'sub' claim.
        - Doctor ID from token doesn't exist in DB.
        - Doctor account has been deactivated (is_active=False).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Step 1: Decode and validate token
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    # Step 2: Extract doctor ID from claims
    doctor_id_str: str | None = payload.get("sub")
    if doctor_id_str is None:
        raise credentials_exception

    try:
        doctor_id = int(doctor_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    # Step 3: Query database for doctor
    result = await db.execute(
        select(Doctor).where(Doctor.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()

    # Step 4: Validate doctor exists and is active
    if doctor is None:
        raise credentials_exception

    if not doctor.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated",
        )

    return doctor
