"""
Sushruta — Authentication API Routes
======================================

HTTP endpoints for doctor registration, login, and profile.

Architecture:
- Routes receive HTTP requests and validate inputs via Pydantic.
- Business logic is delegated to auth_service (never in routes).
- JWT dependency is injected via get_current_doctor.
- Routes return Pydantic response schemas (never raw ORM objects).
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.database import get_db
from app.db.models import Doctor
from app.schemas.auth import (
    DoctorCreate,
    DoctorLogin,
    DoctorResponse,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=DoctorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new doctor",
    description="Create a new doctor account with license number verification.",
)
async def register(
    doctor_data: DoctorCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new doctor.

    - Validates email uniqueness.
    - Validates license number uniqueness.
    - Hashes password with bcrypt.
    - Returns doctor profile (no password).
    """
    return await auth_service.register_doctor(
        db=db,
        doctor_data=doctor_data,
        ip_address=request.client.host if request.client else None,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Doctor login",
    description="Authenticate with email and password. Returns JWT access token.",
)
async def login(
    login_data: DoctorLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate a doctor and issue a JWT token.

    - Verifies email and password.
    - Returns access_token + doctor profile.
    - Token expires in ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    return await auth_service.authenticate_doctor(
        db=db,
        email=login_data.email,
        password=login_data.password,
        ip_address=request.client.host if request.client else None,
    )


@router.get(
    "/me",
    response_model=DoctorResponse,
    summary="Get current doctor profile",
    description="Returns the authenticated doctor's profile information.",
)
async def get_me(
    doctor: Doctor = Depends(get_current_doctor),
):
    """
    Get the authenticated doctor's profile.

    Requires a valid JWT token in the Authorization header.
    """
    return await auth_service.get_doctor_profile(doctor)
