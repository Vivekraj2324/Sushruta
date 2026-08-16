"""
Sushruta — Patient API Routes
================================

HTTP endpoints for patient CRUD operations.

All routes are protected — require JWT via get_current_doctor.
Data isolation is enforced in the service layer (doctor can only
access their own patients).
"""

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.database import get_db
from app.db.models import Doctor
from app.schemas.patient import (
    PatientCreate,
    PatientListResponse,
    PatientResponse,
    PatientUpdate,
    ReferralRequest,
)
from app.ai.agents.summariser import PatientSummaryResponse
from app.ai.agents.referral_writer import ReferralLetterResponse
from app.services import patient_service

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post(
    "",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new patient",
    description="Register a new patient under the authenticated doctor.",
)
async def create_patient(
    patient_data: PatientCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """Create a new patient. The patient is automatically assigned to the logged-in doctor."""
    return await patient_service.create_patient(
        db=db,
        patient_data=patient_data,
        doctor=doctor,
        ip_address=request.client.host if request.client else None,
    )


@router.get(
    "",
    response_model=PatientListResponse,
    summary="List patients",
    description="List all active patients for the authenticated doctor with pagination.",
)
async def list_patients(
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(default=None, description="Search by patient name"),
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """List all active patients with optional name search and pagination."""
    return await patient_service.list_patients(
        db=db,
        doctor=doctor,
        page=page,
        limit=limit,
        search=search,
    )


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    summary="Get patient details",
    description="Retrieve a specific patient's details. Must belong to the authenticated doctor.",
)
async def get_patient(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """Get a patient by ID. Returns 404 if not found or not yours."""
    return await patient_service.get_patient(
        db=db,
        patient_id=patient_id,
        doctor=doctor,
    )


@router.patch(
    "/{patient_id}",
    response_model=PatientResponse,
    summary="Update patient",
    description="Partially update a patient's information. Only send fields to update.",
)
async def update_patient(
    patient_id: int,
    update_data: PatientUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """Update a patient. Only provided fields are modified (PATCH semantics)."""
    return await patient_service.update_patient(
        db=db,
        patient_id=patient_id,
        update_data=update_data,
        doctor=doctor,
        ip_address=request.client.host if request.client else None,
    )


@router.delete(
    "/{patient_id}",
    summary="Delete patient (soft)",
    description="Deactivate a patient record. Data is retained for compliance.",
)
async def delete_patient(
    patient_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """Soft-delete a patient. Sets is_active=False. Record is never hard-deleted."""
    return await patient_service.delete_patient(
        db=db,
        patient_id=patient_id,
        doctor=doctor,
        ip_address=request.client.host if request.client else None,
    )


@router.get(
    "/{patient_id}/summary",
    response_model=PatientSummaryResponse,
    summary="Generate patient clinical summary",
    description="Retrieves the patient's records and clinical notes, compiling them into a structured medical summary.",
)
async def get_patient_summary(
    patient_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    ip_address = request.client.host if request.client else None
    return await patient_service.generate_patient_summary_service(
        db=db,
        patient_id=patient_id,
        doctor=doctor,
        ip_address=ip_address,
    )


@router.post(
    "/{patient_id}/referral",
    response_model=ReferralLetterResponse,
    summary="Generate clinical referral letter",
    description="Generates a formal, clinical referral letter to a target specialist based on patient notes.",
)
async def generate_referral(
    patient_id: int,
    payload: ReferralRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    ip_address = request.client.host if request.client else None
    return await patient_service.generate_referral_letter_service(
        db=db,
        patient_id=patient_id,
        target_specialist=payload.target_specialist,
        referral_reason=payload.referral_reason,
        doctor=doctor,
        ip_address=ip_address,
    )
