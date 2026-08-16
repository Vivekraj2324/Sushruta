"""
Sushruta — Clinical Interaction Service
=========================================

Handles database CRUD for patient encounters/interactions and performs
drug-drug interaction analysis via the Drug Checker agent.
"""

import json
import logging
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.drug_checker import check_drug_interactions
from app.core.audit import AuditAction, create_audit_log
from app.db.models import Doctor, ClinicalInteraction
from app.schemas.interaction import InteractionCreate
from app.services.patient_service import get_patient_model

logger = logging.getLogger(__name__)

async def create_clinical_interaction_service(
    db: AsyncSession,
    patient_id: int,
    interaction_data: InteractionCreate,
    doctor: Doctor,
    ip_address: Optional[str] = None,
) -> ClinicalInteraction:
    """
    Record a new patient encounter / clinical interaction.
    """
    # Verify patient ownership
    await get_patient_model(db, patient_id, doctor)

    db_interaction = ClinicalInteraction(
        patient_id=patient_id,
        doctor_id=doctor.id,
        interaction_date=interaction_data.interaction_date,
        type=interaction_data.type,
        notes=interaction_data.notes,
    )
    db.add(db_interaction)
    await db.flush()

    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient_id,
        action=AuditAction.CLINICAL_INTERACTION_RECORDED,
        resource_type="clinical_interaction",
        resource_id=db_interaction.id,
        details=json.dumps({
            "type": interaction_data.type,
            "interaction_date": interaction_data.interaction_date.isoformat(),
        }),
        ip_address=ip_address,
    )
    await db.commit()
    await db.refresh(db_interaction)
    return db_interaction

async def list_clinical_interactions_by_patient_service(
    db: AsyncSession,
    patient_id: int,
    doctor: Doctor,
    limit: int = 20,
    offset: int = 0,
) -> List[ClinicalInteraction]:
    """
    List clinical interactions for a patient.
    """
    # Verify patient ownership
    await get_patient_model(db, patient_id, doctor)

    result = await db.execute(
        select(ClinicalInteraction).where(
            ClinicalInteraction.patient_id == patient_id,
            ClinicalInteraction.doctor_id == doctor.id,
        ).order_by(ClinicalInteraction.interaction_date.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())

async def check_drug_interactions_service(
    db: AsyncSession,
    medications: List[str],
    doctor: Doctor,
    patient_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> dict:
    """
    Perform drug interaction checking using the Drug Checker agent.
    """
    # Perform patient validation if ID is provided
    if patient_id is not None:
        await get_patient_model(db, patient_id, doctor)

    # Call AI agent
    results = await check_drug_interactions(medications)
    if results is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to run drug interaction check using AI.",
        )

    # Log audit
    await create_audit_log(
        db,
        doctor_id=doctor.id,
        patient_id=patient_id,
        action=AuditAction.DRUG_INTERACTION_CHECKED,
        resource_type="patient" if patient_id else None,
        resource_id=patient_id,
        details=json.dumps({
            "medications": medications,
            "has_interactions": results.get("has_interactions", False),
            "interaction_count": len(results.get("interactions", [])),
        }),
        ip_address=ip_address,
    )
    await db.commit()
    return results
