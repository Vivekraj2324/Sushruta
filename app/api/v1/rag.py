"""
Sushruta — RAG API Routes (Phase 2)
=====================================

Endpoints for the intelligence layer:
- Ask questions about a patient's documents (RAG)
- Process documents for RAG (chunk + embed)
- View document chunks
- Check processing status

All routes are nested under /patients/{patient_id}/rag or
/patients/{patient_id}/documents/{document_id}/process.
"""

from fastapi import APIRouter, Depends, Request, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_doctor
from app.db.database import get_db
from app.db.models import Doctor
from app.schemas.rag import (
    ChunkListResponse,
    ProcessingStatusResponse,
    RAGAnswerResponse,
    RAGQuestionRequest,
)
from app.services import rag_service

router = APIRouter(tags=["RAG Intelligence"])


# ── Question Answering ───────────────────────────────────────────


@router.post(
    "/patients/{patient_id}/ask",
    response_model=RAGAnswerResponse,
    summary="Ask a question about a patient",
    description=(
        "Uses RAG to answer a question about a patient's medical history. "
        "Retrieves relevant document chunks via semantic search and generates "
        "a grounded answer with source citations using Gemini."
    ),
)
async def ask_question(
    patient_id: int,
    body: RAGQuestionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """
    Ask a question about a patient's documents.

    The AI will search through all of the patient's uploaded and processed
    documents, find the most relevant passages, and generate an answer
    with citations to the source documents.
    """
    return await rag_service.ask_question(
        db=db,
        patient_id=patient_id,
        question=body.question,
        doctor=doctor,
        ip_address=request.client.host if request.client else None,
    )


# ── Document Processing ─────────────────────────────────────────


@router.post(
    "/patients/{patient_id}/documents/{document_id}/process",
    response_model=ProcessingStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process a document for RAG",
    description=(
        "Chunks the document text and creates vector embeddings. "
        "Must be called after upload for the document to be searchable via RAG."
    ),
)
async def process_document(
    patient_id: int,
    document_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """
    Process a document: split into chunks and create vector embeddings.

    Call this after uploading a document. The document must have
    extracted text (PDF/DOCX). Processing enables the document
    to be searched via the /ask endpoint.
    """
    status_resp = await rag_service.start_document_processing(
        db=db,
        document_id=document_id,
        doctor=doctor,
    )
    background_tasks.add_task(
        rag_service.process_document_in_background,
        document_id=document_id,
        doctor_id=doctor.id,
    )
    return status_resp


# ── Status & Inspection ─────────────────────────────────────────


@router.get(
    "/patients/{patient_id}/documents/{document_id}/status",
    response_model=ProcessingStatusResponse,
    summary="Check processing status",
    description="Check whether a document has been fully processed for RAG.",
)
async def get_status(
    patient_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """Get the current processing status of a document."""
    return await rag_service.get_processing_status(
        db=db,
        patient_id=patient_id,
        document_id=document_id,
        doctor=doctor,
    )


@router.get(
    "/patients/{patient_id}/documents/{document_id}/chunks",
    response_model=ChunkListResponse,
    summary="List document chunks",
    description=(
        "View all chunks a document was split into. "
        "Useful for debugging and transparency."
    ),
)
async def list_chunks(
    patient_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    doctor: Doctor = Depends(get_current_doctor),
):
    """List all chunks for a processed document."""
    return await rag_service.get_document_chunks(
        db=db,
        patient_id=patient_id,
        document_id=document_id,
        doctor=doctor,
    )
