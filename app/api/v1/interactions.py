"""
Sushruta — Clinical Interaction API Routes
=============================================

Exposes endpoints for recording and listing patient encounters, and running
state-of-the-art drug-drug interaction checks via Gemini.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.database import get_db
from app.db.models import Doctor
from app.schemas.interaction import (
    InteractionCreate,
    InteractionResponse,
    DrugCheckRequest,
    DrugCheckResponse,
)
from app.services.interaction_service import (
    create_clinical_interaction_service,
    list_clinical_interactions_by_patient_service,
    check_drug_interactions_service,
)

router = APIRouter(prefix="/interactions", tags=["Clinical Interactions"])

@router.post(
    "",
    response_model=InteractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new clinical interaction",
    description="Save a new clinical encounter/interaction (visit log) for a patient.",
)
async def record_interaction(
    request: Request,
    payload: InteractionCreate,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    ip_address = request.client.host if request.client else None
    return await create_clinical_interaction_service(
        db=db,
        patient_id=payload.patient_id,
        interaction_data=payload,
        doctor=doctor,
        ip_address=ip_address,
    )

@router.get(
    "/patient/{patient_id}",
    response_model=List[InteractionResponse],
    summary="List patient interactions",
    description="Retrieve all recorded encounters/interactions for a patient.",
)
async def list_interactions(
    patient_id: int,
    limit: int = 20,
    offset: int = 0,
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    return await list_clinical_interactions_by_patient_service(
        db=db,
        patient_id=patient_id,
        doctor=doctor,
        limit=limit,
        offset=offset,
    )

@router.post(
    "/check",
    response_model=DrugCheckResponse,
    summary="Check drug-drug interactions",
    description="Analyzes a list of medications for potential interactions using a clinical AI agent.",
)
async def check_drugs(
    request: Request,
    payload: DrugCheckRequest,
    patient_id: Optional[int] = Query(None, description="Optional ID of the patient to validate ownership and log against."),
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    ip_address = request.client.host if request.client else None
    results = await check_drug_interactions_service(
        db=db,
        medications=payload.medications,
        doctor=doctor,
        patient_id=patient_id,
        ip_address=ip_address,
    )
    return results
