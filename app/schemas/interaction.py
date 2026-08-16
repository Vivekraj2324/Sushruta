"""
Sushruta — Clinical Interaction Schemas
========================================

Pydantic schemas for validation and serialization of clinical interactions
and drug interaction checks.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class InteractionBase(BaseModel):
    """Base clinical interaction attributes."""
    patient_id: int = Field(..., description="ID of the patient.")
    interaction_date: datetime = Field(..., description="Date/time of the encounter.")
    type: str = Field("Encounter", max_length=100, description="Type of encounter (e.g. Follow-up, Routine, Phone).")
    notes: Optional[str] = Field(None, description="Encounter clinical notes.")

class InteractionCreate(InteractionBase):
    """Clinical interaction creation validation schema."""
    pass

class InteractionResponse(InteractionBase):
    """Clinical interaction database output serialization schema."""
    id: int
    doctor_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

class DrugCheckRequest(BaseModel):
    """Drug interaction check input validation schema."""
    medications: List[str] = Field(..., min_length=2, description="List of medications to check for interactions.")

class DrugInteractionDetailSchema(BaseModel):
    """Schema for individual drug interaction description."""
    drugs: List[str] = Field(..., description="The medications involved in the interaction.")
    severity: str = Field(..., description="Severity level: HIGH, MODERATE, or MINOR.")
    description: str = Field(..., description="Explanation of the interaction mechanism.")
    clinical_advice: str = Field(..., description="Clinical instructions for mitigation.")

class DrugCheckResponse(BaseModel):
    """Drug interaction check output serialization schema."""
    has_interactions: bool = Field(..., description="True if any interactions are detected.")
    interactions: List[DrugInteractionDetailSchema] = Field(default=[], description="List of interaction details.")
    checked_at: datetime = Field(default_factory=datetime.now, description="When the check was completed.")
