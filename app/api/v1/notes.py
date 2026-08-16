"""
Sushruta — Clinical Note API Routes
=====================================

Exposes endpoints for generating SOAP note drafts via AI, creating notes
manually, listing patient notes, retrieving, updating, and deleting notes.
"""

from typing import List
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.database import get_db
from app.db.models import Doctor
from app.schemas.note import (
    NoteCreate,
    NoteUpdate,
    NoteResponse,
    NoteGenerationRequest,
)
from app.services.note_service import (
    generate_note_draft_service,
    create_clinical_note_service,
    get_clinical_note_service,
    list_clinical_notes_by_patient_service,
    update_clinical_note_service,
    delete_clinical_note_service,
)

router = APIRouter(prefix="/notes", tags=["Clinical Notes"])

@router.post(
    "/generate",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate SOAP note draft via AI",
    description="Processes raw consultation dialogue via the AI scribe, saves it as a draft clinical note.",
)
async def generate_note_draft(
    request: Request,
    payload: NoteGenerationRequest,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    ip_address = request.client.host if request.client else None
    return await generate_note_draft_service(
        db=db,
        patient_id=payload.patient_id,
        raw_input=payload.raw_input,
        consultation_date=payload.consultation_date,
        doctor=doctor,
        ip_address=ip_address,
    )

@router.post(
    "",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a clinical note",
    description="Manually record a clinical note (either draft or finalized).",
)
async def create_note(
    request: Request,
    payload: NoteCreate,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    ip_address = request.client.host if request.client else None
    return await create_clinical_note_service(
        db=db,
        patient_id=payload.patient_id,
        note_data=payload,
        doctor=doctor,
        ip_address=ip_address,
    )

@router.get(
    "/patient/{patient_id}",
    response_model=List[NoteResponse],
    summary="List patient notes",
    description="Retrieve all clinical notes recorded for a specific patient.",
)
async def list_notes(
    patient_id: int,
    limit: int = 20,
    offset: int = 0,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    return await list_clinical_notes_by_patient_service(
        db=db,
        patient_id=patient_id,
        doctor=doctor,
        limit=limit,
        offset=offset,
    )

@router.get(
    "/{id}",
    response_model=NoteResponse,
    summary="Get clinical note",
    description="Retrieve clinical note details by ID.",
)
async def get_note(
    request: Request,
    id: int,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    ip_address = request.client.host if request.client else None
    return await get_clinical_note_service(
        db=db,
        note_id=id,
        doctor=doctor,
        ip_address=ip_address,
    )

@router.patch(
    "/{id}",
    response_model=NoteResponse,
    summary="Update clinical note",
    description="Update note details, such as editing the content or finalizing a draft.",
)
async def update_note(
    request: Request,
    id: int,
    payload: NoteUpdate,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    ip_address = request.client.host if request.client else None
    return await update_clinical_note_service(
        db=db,
        note_id=id,
        note_update=payload,
        doctor=doctor,
        ip_address=ip_address,
    )

@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Delete clinical note",
    description="Deletes a clinical note record.",
)
async def delete_note(
    request: Request,
    id: int,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    ip_address = request.client.host if request.client else None
    await delete_clinical_note_service(
        db=db,
        note_id=id,
        doctor=doctor,
        ip_address=ip_address,
    )
    return {"message": "Note deleted successfully"}
