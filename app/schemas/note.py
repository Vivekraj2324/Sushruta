"""
Sushruta — Clinical Note Schemas
==================================

Pydantic schemas for validation and serialization of clinical notes.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class NoteBase(BaseModel):
    """Base note attributes."""
    patient_id: int = Field(..., description="ID of the patient.")
    raw_input: str = Field(..., min_length=10, description="Raw input transcript or doctor dictation.")
    consultation_date: datetime = Field(..., description="Date/time of the consultation.")
    is_draft: bool = Field(True, description="Whether the note is a draft.")

class NoteCreate(NoteBase):
    """Note creation input validation schema."""
    generated_note: Optional[str] = Field(None, description="Pre-generated clinical note text (optional).")

class NoteUpdate(BaseModel):
    """Note partial update schema."""
    generated_note: Optional[str] = Field(None, description="Updated clinical note text.")
    is_draft: Optional[bool] = Field(None, description="Update draft status (e.g. set to false to finalize).")

class NoteResponse(NoteBase):
    """Note database output serialization schema."""
    id: int
    doctor_id: int
    generated_note: str
    note_type: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

class NoteGenerationRequest(BaseModel):
    """Note generation input schema."""
    patient_id: int = Field(..., description="ID of the patient.")
    raw_input: str = Field(..., min_length=10, description="Raw dialogue transcript or doctor dictation.")
    consultation_date: datetime = Field(default_factory=datetime.now, description="Consultation date.")

class NoteGenerationResponse(BaseModel):
    """Note generation response schema containing individual SOAP parts and formatted note."""
    patient_id: int
    note_type: str = "SOAP"
    subjective: str
    objective: str
    assessment: str
    plan: str
    clinical_summary: str
    formatted_note: str
