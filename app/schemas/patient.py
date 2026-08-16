"""
Sushruta — Patient Schemas
============================

Pydantic v2 models for patient CRUD operations.

Design:
- PatientCreate: All required fields for new patient + optional medical metadata.
- PatientUpdate: All fields optional (PATCH semantics — update only what's sent).
- PatientResponse: Full patient view (from_attributes=True for ORM conversion).
- PatientListResponse: Paginated list with total count for frontend pagination.

Validation:
- age: 0–150 (clinical reality check).
- gender: Validated string (flexible for international standards).
- blood_group: Optional, validated against known types.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class GenderEnum(str, Enum):
    """Accepted gender values for patient records."""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class PatientCreate(BaseModel):
    """
    New patient creation request.

    Required: name, age, gender.
    Optional: blood_group, allergies, medical_history.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Patient's full name",
        examples=["Rajesh Kumar"],
    )
    age: int = Field(
        ...,
        ge=0,
        le=150,
        description="Patient age in years",
        examples=[45],
    )
    gender: GenderEnum = Field(
        ...,
        description="Patient gender",
        examples=["male"],
    )
    blood_group: str | None = Field(
        default=None,
        max_length=10,
        description="Blood group (e.g., A+, B-, O+, AB+)",
        examples=["B+"],
    )
    allergies: str | None = Field(
        default=None,
        description="Known allergies (comma-separated or free text)",
        examples=["Penicillin, Sulfa drugs"],
    )
    medical_history: str | None = Field(
        default=None,
        description="Relevant medical history summary",
        examples=["Type 2 Diabetes since 2015, Hypertension"],
    )

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Patient name cannot be blank")
        return v.strip()

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid_groups = {
            "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-",
        }
        v_upper = v.strip().upper()
        if v_upper not in valid_groups:
            raise ValueError(
                f"Invalid blood group '{v}'. Must be one of: {', '.join(sorted(valid_groups))}"
            )
        return v_upper


class PatientUpdate(BaseModel):
    """
    Partial patient update (PATCH semantics).

    All fields are optional. Only provided fields are updated.
    This enables atomic field-level updates without overwriting
    untouched fields.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    age: int | None = Field(default=None, ge=0, le=150)
    gender: GenderEnum | None = None
    blood_group: str | None = None
    allergies: str | None = None
    medical_history: str | None = None

    @field_validator("blood_group")
    @classmethod
    def validate_blood_group(cls, v: str | None) -> str | None:
        if v is None:
            return v
        valid_groups = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        v_upper = v.strip().upper()
        if v_upper not in valid_groups:
            raise ValueError(
                f"Invalid blood group '{v}'. Must be one of: {', '.join(sorted(valid_groups))}"
            )
        return v_upper


class PatientResponse(BaseModel):
    """
    Patient profile response.

    Includes all fields except is_active (filtered by queries).
    from_attributes=True enables direct ORM-to-schema conversion.
    """

    id: int
    doctor_id: int
    name: str
    age: int
    gender: str
    blood_group: str | None = None
    allergies: str | None = None
    medical_history: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientListResponse(BaseModel):
    """
    Paginated list of patients.

    Provides total count for frontend pagination controls.
    """

    patients: list[PatientResponse]
    total: int
    page: int
    limit: int


class ReferralRequest(BaseModel):
    """Request schema for referral letter generation."""
    target_specialist: str = Field(..., min_length=2, description="Target specialty or doctor name.")
    referral_reason: str = Field(..., min_length=10, description="Why the patient is being referred.")

