"""
Sushruta — Document Schemas
==============================

Pydantic v2 models for document upload and retrieval.

Design:
- Documents are uploaded as multipart/form-data (no Pydantic input schema).
- DocumentResponse: Shows document metadata without the raw extracted text
  (which can be very large).
- DocumentDetailResponse: Includes extracted_text for detailed views.
- DocumentListResponse: List wrapper for consistency.

The processing_status field tracks the document pipeline:
  uploaded → processing → ready → failed
"""

from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """
    Document metadata response (list view).

    Excludes extracted_text to keep list responses lightweight.
    """

    id: int
    patient_id: int
    doctor_id: int
    original_filename: str
    file_type: str
    file_size_bytes: int
    processing_status: str
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailResponse(BaseModel):
    """
    Full document response including extracted text.

    Used for single-document detail views where the doctor
    needs to see the extracted content.
    """

    id: int
    patient_id: int
    doctor_id: int
    original_filename: str
    stored_filename: str
    file_type: str
    file_size_bytes: int
    extracted_text: str | None = None
    processing_status: str
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """List of documents for a patient."""

    documents: list[DocumentResponse]
    total: int
