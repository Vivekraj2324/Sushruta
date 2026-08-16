"""
Sushruta — Document API Routes
================================

HTTP endpoints for medical document upload and management.

Documents are nested under patients:
  /api/v1/patients/{patient_id}/documents

File upload uses FastAPI's UploadFile with multipart/form-data.
All routes are protected and verify patient ownership.
"""

from fastapi import APIRouter, Depends, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.database import get_db
from app.db.models import Doctor
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
)
from app.services import document_service

router = APIRouter(prefix="/patients/{patient_id}/documents", tags=["Documents"])


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description="Upload a medical document (PDF, PNG, JPG, DOCX) for a patient.",
)
async def upload_document(
    patient_id: int,
    file: UploadFile,
    request: Request,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """
    Upload a medical document.

    - Validates file type and size.
    - Extracts text from PDF/DOCX.
    - Saves file to disk with UUID filename.
    """
    return await document_service.upload_document(
        db=db,
        patient_id=patient_id,
        file=file,
        doctor=doctor,
        ip_address=request.client.host if request.client else None,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="List all active documents for a patient.",
)
async def list_documents(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """List all documents for a patient. Only the owning doctor can access these."""
    return await document_service.list_documents(
        db=db,
        patient_id=patient_id,
        doctor=doctor,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document details",
    description="Get full document details including extracted text.",
)
async def get_document(
    patient_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """Get a single document with all details including extracted text."""
    return await document_service.get_document(
        db=db,
        patient_id=patient_id,
        document_id=document_id,
        doctor=doctor,
    )


@router.delete(
    "/{document_id}",
    summary="Delete document (soft)",
    description="Deactivate a document. File and data are retained for compliance.",
)
async def delete_document(
    patient_id: int,
    document_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """Soft-delete a document. File remains on disk. Record stays in DB."""
    return await document_service.delete_document(
        db=db,
        patient_id=patient_id,
        document_id=document_id,
        doctor=doctor,
        ip_address=request.client.host if request.client else None,
    )
