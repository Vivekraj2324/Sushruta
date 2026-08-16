"""
Sushruta — Clinical Note Service
=================================

Handles database operations, authorization checks, and audit logging
for clinical notes. Interfaces with Note Writer agent to generate notes.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.note_writer import generate_clinical_note
from app.core.audit import AuditAction, create_audit_log
from app.db.models import Doctor, ClinicalNote
from app.schemas.note import NoteCreate, NoteUpdate
from app.services.patient_service import get_patient_model

logger = logging.getLogger(__name__)

async def get_note_model(
    db: AsyncSession,
    note_id: int,
    doctor: Doctor,
) -> ClinicalNote:
    """
    Retrieve a clinical note by ID and verify doctor ownership.
    """
    result = await db.execute(
        select(ClinicalNote).where(
            ClinicalNote.id == note_id,
            ClinicalNote.doctor_id == doctor.id,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical note not found or access denied.",
        )
    return note

async def generate_note_draft_service(
    db: AsyncSession,
    patient_id: int,
    raw_input: str,
    consultation_date: datetime,
    doctor: Doctor,
    ip_address: Optional[str] = None,
) -> ClinicalNote:
    """
    Call the Clinical Note Writer agent to generate a draft SOAP note
    and save it in the database.
    """
    # Verify patient ownership
    await get_patient_model(db, patient_id, doctor)

    # Call AI agent
    generated_data = await generate_clinical_note(raw_input)
    if not generated_data:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate clinical note using AI.",
        )

    # Save to database
    db_note = ClinicalNote(
        patient_id=patient_id,
        doctor_id=doctor.id,
        raw_input=raw_input,
        generated_note=generated_data["formatted_note"],
        consultation_date=consultation_date,
        is_draft=True,
        note_type="SOAP",
    )
    db.add(db_note)
    await db.flush()

    # Log audit
    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient_id,
        action=AuditAction.CLINICAL_NOTE_GENERATED,
        resource_type="clinical_note",
        resource_id=db_note.id,
        details=json.dumps({
            "note_type": "SOAP",
            "consultation_date": consultation_date.isoformat(),
            "raw_length": len(raw_input),
        }),
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(db_note)
    return db_note

async def create_clinical_note_service(
    db: AsyncSession,
    patient_id: int,
    note_data: NoteCreate,
    doctor: Doctor,
    ip_address: Optional[str] = None,
) -> ClinicalNote:
    """
    Manually save a clinical note in the database.
    """
    await get_patient_model(db, patient_id, doctor)

    db_note = ClinicalNote(
        patient_id=patient_id,
        doctor_id=doctor.id,
        raw_input=note_data.raw_input,
        generated_note=note_data.generated_note or "",
        consultation_date=note_data.consultation_date,
        is_draft=note_data.is_draft,
        note_type="SOAP",
    )
    db.add(db_note)
    await db.flush()

    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient_id,
        action=AuditAction.CLINICAL_NOTE_CREATED,
        resource_type="clinical_note",
        resource_id=db_note.id,
        details=json.dumps({
            "is_draft": note_data.is_draft,
            "consultation_date": note_data.consultation_date.isoformat(),
        }),
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(db_note)
    return db_note

async def get_clinical_note_service(
    db: AsyncSession,
    note_id: int,
    doctor: Doctor,
    ip_address: Optional[str] = None,
) -> ClinicalNote:
    """
    Retrieve clinical note detail.
    """
    note = await get_note_model(db, note_id, doctor)

    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=note.patient_id,
        action=AuditAction.CLINICAL_NOTE_VIEWED,
        resource_type="clinical_note",
        resource_id=note.id,
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(note)
    return note

async def list_clinical_notes_by_patient_service(
    db: AsyncSession,
    patient_id: int,
    doctor: Doctor,
    limit: int = 20,
    offset: int = 0,
) -> List[ClinicalNote]:
    """
    List all clinical notes for a patient.
    """
    await get_patient_model(db, patient_id, doctor)

    result = await db.execute(
        select(ClinicalNote).where(
            ClinicalNote.patient_id == patient_id,
            ClinicalNote.doctor_id == doctor.id,
        ).order_by(ClinicalNote.consultation_date.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())

async def update_clinical_note_service(
    db: AsyncSession,
    note_id: int,
    note_update: NoteUpdate,
    doctor: Doctor,
    ip_address: Optional[str] = None,
) -> ClinicalNote:
    """
    Update details of a clinical note (e.g. editing generated_note or finalizing draft).
    """
    note = await get_note_model(db, note_id, doctor)

    update_details = {}
    if note_update.generated_note is not None:
        note.generated_note = note_update.generated_note
        update_details["generated_note_edited"] = True
    if note_update.is_draft is not None:
        note.is_draft = note_update.is_draft
        update_details["is_draft"] = note_update.is_draft

    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=note.patient_id,
        action=AuditAction.CLINICAL_NOTE_UPDATED,
        resource_type="clinical_note",
        resource_id=note.id,
        details=json.dumps(update_details),
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(note)
    return note

async def delete_clinical_note_service(
    db: AsyncSession,
    note_id: int,
    doctor: Doctor,
    ip_address: Optional[str] = None,
) -> None:
    """
    Delete a clinical note.
    """
    note = await get_note_model(db, note_id, doctor)
    patient_id = note.patient_id

    await db.delete(note)

    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient_id,
        action=AuditAction.CLINICAL_NOTE_DELETED,
        resource_type="clinical_note",
        resource_id=note_id,
        ip_address=ip_address,
    )
    await db.commit()
