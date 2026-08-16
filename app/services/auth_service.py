"""
Sushruta — Authentication Service
====================================

Business logic for doctor registration and authentication.

This service layer:
- Receives validated data from the API layer.
- Applies business rules (uniqueness checks, password hashing).
- Interacts with the database.
- Creates audit logs.
- Raises HTTP exceptions on business rule violations.

Design decisions:
- Service functions accept AsyncSession, not raw connections.
- Each function is independently testable.
- Password is hashed before touching the database.
- Email uniqueness is checked explicitly (not relying on DB constraint
  alone) to return a friendly error message.
"""

import json

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction, create_audit_log
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import Doctor
from app.schemas.auth import DoctorCreate, DoctorResponse, TokenResponse


async def register_doctor(
    db: AsyncSession,
    doctor_data: DoctorCreate,
    ip_address: str | None = None,
) -> DoctorResponse:
    """
    Register a new doctor.

    Flow:
    1. Check email uniqueness (friendly error vs DB constraint error).
    2. Check license number uniqueness.
    3. Hash password with bcrypt.
    4. Insert doctor record.
    5. Create audit log entry.
    6. Commit transaction.
    7. Return DoctorResponse (no password).

    Raises
    ------
    HTTPException 400
        If email or license number is already registered.
    """
    # Step 1: Check email uniqueness
    existing = await db.execute(
        select(Doctor).where(Doctor.email == doctor_data.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A doctor with this email is already registered",
        )

    # Step 2: Check license number uniqueness
    existing_license = await db.execute(
        select(Doctor).where(Doctor.license_number == doctor_data.license_number)
    )
    if existing_license.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A doctor with this license number is already registered",
        )

    # Step 3: Hash password
    hashed = hash_password(doctor_data.password)

    # Step 4: Create doctor record
    doctor = Doctor(
        name=doctor_data.name,
        email=doctor_data.email,
        hashed_password=hashed,
        license_number=doctor_data.license_number,
        specialisation=doctor_data.specialisation,
    )
    db.add(doctor)
    await db.flush()  # Get auto-generated ID before audit log

    # Step 5: Audit log
    await create_audit_log(
        db,
        doctor_id=doctor.id,
        action=AuditAction.DOCTOR_REGISTERED,
        resource_type="doctor",
        resource_id=doctor.id,
        details=json.dumps({"email": doctor.email}),
        ip_address=ip_address,
    )

    # Step 6: Commit
    await db.commit()
    await db.refresh(doctor)

    return DoctorResponse.model_validate(doctor)


async def authenticate_doctor(
    db: AsyncSession,
    email: str,
    password: str,
    ip_address: str | None = None,
) -> TokenResponse:
    """
    Authenticate a doctor and issue a JWT token.

    Flow:
    1. Find doctor by email.
    2. Verify password with bcrypt.
    3. Check account is active.
    4. Create JWT with doctor_id as subject.
    5. Audit log the login.
    6. Return token + doctor profile.

    Raises
    ------
    HTTPException 401
        If email not found or password incorrect.
    HTTPException 403
        If account is deactivated.
    """
    # Step 1: Find by email
    result = await db.execute(
        select(Doctor).where(Doctor.email == email)
    )
    doctor = result.scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Step 2: Verify password
    if not verify_password(password, doctor.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Step 3: Check active
    if not doctor.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been deactivated",
        )

    # Step 4: Create JWT
    access_token = create_access_token(
        data={"sub": str(doctor.id), "email": doctor.email}
    )

    # Step 5: Audit log
    await create_audit_log(
        db,
        doctor_id=doctor.id,
        action=AuditAction.DOCTOR_LOGIN,
        resource_type="doctor",
        resource_id=doctor.id,
        ip_address=ip_address,
    )
    await db.commit()

    # Step 6: Return
    return TokenResponse(
        access_token=access_token,
        doctor=DoctorResponse.model_validate(doctor),
    )


async def get_doctor_profile(doctor: Doctor) -> DoctorResponse:
    """
    Return the current doctor's profile.

    No DB query needed — the doctor object is already loaded
    by the get_current_doctor dependency.
    """
    return DoctorResponse.model_validate(doctor)
