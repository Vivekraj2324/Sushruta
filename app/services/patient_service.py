"""
Sushruta — Patient Service
============================

Business logic for patient CRUD operations.

Data isolation:
- Every query filters by doctor_id to enforce row-level security.
- This is the ONLY place where patient data is accessed.
- A doctor can never see, modify, or delete another doctor's patients.

Soft delete:
- delete_patient sets is_active=False, never removes the row.
- All list/get queries filter is_active=True by default.
- Medical records must be retained for legal compliance.

Pagination:
- list_patients supports page/limit parameters.
- Optional search filter on patient name (case-insensitive LIKE).
"""

import json

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction, create_audit_log
from app.db.models import Doctor, Patient, DocumentChunk, ClinicalNote
from app.schemas.patient import (
    PatientCreate,
    PatientListResponse,
    PatientResponse,
    PatientUpdate,
)


async def create_patient(
    db: AsyncSession,
    patient_data: PatientCreate,
    doctor: Doctor,
    ip_address: str | None = None,
) -> PatientResponse:
    """
    Create a new patient belonging to the authenticated doctor.

    The doctor_id is injected from the JWT — not from the request body.
    This prevents a doctor from creating patients under another doctor's ID.
    """
    patient = Patient(
        doctor_id=doctor.id,
        name=patient_data.name,
        age=patient_data.age,
        gender=patient_data.gender.value,
        blood_group=patient_data.blood_group,
        allergies=patient_data.allergies,
        medical_history=patient_data.medical_history,
    )
    db.add(patient)
    await db.flush()

    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient.id,
        action=AuditAction.PATIENT_CREATED,
        resource_type="patient",
        resource_id=patient.id,
        details=json.dumps({"name": patient.name}),
        ip_address=ip_address,
    )

    await db.commit()
    await db.refresh(patient)
    return PatientResponse.model_validate(patient)


async def list_patients(
    db: AsyncSession,
    doctor: Doctor,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
) -> PatientListResponse:
    """
    List all active patients for the authenticated doctor.

    Supports:
    - Pagination (page + limit)
    - Optional name search (case-insensitive LIKE)
    - Ordered by created_at descending (newest first)
    """
    # Base query: only this doctor's active patients
    base_query = select(Patient).where(
        Patient.doctor_id == doctor.id,
        Patient.is_active == True,  # noqa: E712 — SQLAlchemy requires ==
    )

    # Optional search filter
    if search:
        base_query = base_query.where(
            Patient.name.ilike(f"%{search}%")
        )

    # Count total matching patients
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    offset = (page - 1) * limit
    paginated_query = (
        base_query
        .order_by(Patient.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(paginated_query)
    patients = result.scalars().all()

    return PatientListResponse(
        patients=[PatientResponse.model_validate(p) for p in patients],
        total=total,
        page=page,
        limit=limit,
    )


async def get_patient(
    db: AsyncSession,
    patient_id: int,
    doctor: Doctor,
) -> PatientResponse:
    """
    Get a single patient by ID.

    Enforces ownership: the patient must belong to the authenticated doctor.
    Only returns active patients.

    Raises
    ------
    HTTPException 404
        If patient not found or belongs to another doctor.
    """
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == doctor.id,
            Patient.is_active == True,  # noqa: E712
        )
    )
    patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    return PatientResponse.model_validate(patient)


async def get_patient_model(
    db: AsyncSession,
    patient_id: int,
    doctor: Doctor,
) -> Patient:
    """
    Get the raw Patient ORM object (used internally by other services).

    Same ownership check as get_patient but returns the ORM model
    instead of a Pydantic schema, allowing direct DB mutations.
    """
    result = await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == doctor.id,
            Patient.is_active == True,  # noqa: E712
        )
    )
    patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    return patient


async def update_patient(
    db: AsyncSession,
    patient_id: int,
    update_data: PatientUpdate,
    doctor: Doctor,
    ip_address: str | None = None,
) -> PatientResponse:
    """
    Partially update a patient (PATCH semantics).

    Only fields included in the request body are updated.
    Unset fields (None) are ignored — they don't overwrite existing data.

    Uses exclude_unset=True to distinguish between "field not sent"
    and "field explicitly set to None".
    """
    patient = await get_patient_model(db, patient_id, doctor)

    # Only update fields that were explicitly provided
    update_dict = update_data.model_dump(exclude_unset=True)

    # Convert gender enum to string value if present
    if "gender" in update_dict and update_dict["gender"] is not None:
        update_dict["gender"] = update_dict["gender"].value

    if not update_dict:
        # No fields to update — return current state
        return PatientResponse.model_validate(patient)

    for field, value in update_dict.items():
        setattr(patient, field, value)

    await db.flush()

    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient.id,
        action=AuditAction.PATIENT_UPDATED,
        resource_type="patient",
        resource_id=patient.id,
        details=json.dumps({"updated_fields": list(update_dict.keys())}),
        ip_address=ip_address,
    )

    await db.commit()
    await db.refresh(patient)
    return PatientResponse.model_validate(patient)


async def delete_patient(
    db: AsyncSession,
    patient_id: int,
    doctor: Doctor,
    ip_address: str | None = None,
) -> dict:
    """
    Soft-delete a patient by setting is_active=False.

    The record remains in the database for legal compliance.
    Subsequent queries will not return this patient.

    Returns a confirmation message dict.
    """
    patient = await get_patient_model(db, patient_id, doctor)

    patient.is_active = False
    await db.flush()

    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient.id,
        action=AuditAction.PATIENT_DELETED,
        resource_type="patient",
        resource_id=patient.id,
        details=json.dumps({"name": patient.name}),
        ip_address=ip_address,
    )

    await db.commit()
    return {"message": "Patient deactivated"}


async def generate_patient_summary_service(
    db: AsyncSession,
    patient_id: int,
    doctor: Doctor,
    ip_address: str | None = None,
) -> dict:
    """
    Generate a comprehensive patient summary by retrieving and synthesizing
    their medical history, previous notes, and uploaded records (RAG).
    """
    # 1. Verify patient ownership and get profile
    patient = await get_patient_model(db, patient_id, doctor)

    # 2. Retrieve all document chunks for this patient
    chunk_result = await db.execute(
        select(DocumentChunk.chunk_text).where(
            DocumentChunk.patient_id == patient_id,
            DocumentChunk.doctor_id == doctor.id
        )
    )
    document_excerpts = list(chunk_result.scalars().all())

    # 3. Retrieve all previous clinical notes for this patient
    notes_result = await db.execute(
        select(ClinicalNote.generated_note).where(
            ClinicalNote.patient_id == patient_id,
            ClinicalNote.doctor_id == doctor.id
        ).order_by(ClinicalNote.consultation_date.desc())
    )
    previous_notes = list(notes_result.scalars().all())

    # 4. Invoke agent
    patient_details = {
        "name": patient.name,
        "age": patient.age,
        "gender": patient.gender,
        "blood_group": patient.blood_group,
        "allergies": patient.allergies,
        "medical_history": patient.medical_history
    }
    
    from app.ai.agents.summariser import generate_patient_summary
    summary_data = await generate_patient_summary(
        patient_details=patient_details,
        document_excerpts=document_excerpts,
        previous_notes=previous_notes
    )

    if not summary_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate patient summary using AI."
        )

    # 5. Log audit
    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient_id,
        action=AuditAction.PATIENT_SUMMARY_GENERATED,
        resource_type="patient",
        resource_id=patient_id,
        details=json.dumps({
            "chunks_included": len(document_excerpts),
            "notes_included": len(previous_notes)
        }),
        ip_address=ip_address
    )
    await db.commit()
    return summary_data


async def generate_referral_letter_service(
    db: AsyncSession,
    patient_id: int,
    target_specialist: str,
    referral_reason: str,
    doctor: Doctor,
    ip_address: str | None = None,
) -> dict:
    """
    Generate a formal medical referral letter to a specialist.
    """
    # 1. Verify patient ownership and get profile
    patient = await get_patient_model(db, patient_id, doctor)

    # 2. Retrieve some clinical context (e.g. latest clinical notes)
    notes_result = await db.execute(
        select(ClinicalNote.generated_note).where(
            ClinicalNote.patient_id == patient_id,
            ClinicalNote.doctor_id == doctor.id
        ).order_by(ClinicalNote.consultation_date.desc())
        .limit(3)
    )
    previous_notes = list(notes_result.scalars().all())
    clinical_context = "\n\n---\n\n".join(previous_notes) if previous_notes else "No recent clinical notes recorded."

    # 3. Invoke agent
    patient_details = {
        "name": patient.name,
        "age": patient.age,
        "gender": patient.gender,
        "blood_group": patient.blood_group,
        "allergies": patient.allergies,
        "medical_history": patient.medical_history
    }
    
    from app.ai.agents.referral_writer import generate_referral_letter
    letter_data = await generate_referral_letter(
        patient_details=patient_details,
        clinical_context=clinical_context,
        target_specialist=target_specialist,
        sender_doctor_name=doctor.name,
        referral_reason=referral_reason
    )

    if not letter_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate referral letter using AI."
        )

    # 4. Log audit
    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient_id,
        action=AuditAction.REFERRAL_LETTER_GENERATED,
        resource_type="patient",
        resource_id=patient_id,
        details=json.dumps({
            "target_specialist": target_specialist,
            "referral_reason_length": len(referral_reason)
        }),
        ip_address=ip_address
    )
    await db.commit()
    return letter_data
