"""
Sushruta — Authentication Schemas
===================================

Pydantic v2 models for request validation and response serialisation
in the auth module.

Schema design:
- Input schemas (Create/Login) validate what enters the API.
- Output schemas (Response) control what leaves the API.
- TokenResponse wraps the JWT + doctor profile.
- hashed_password is NEVER included in any response schema.

Validation rules:
- Email: Pydantic's EmailStr-like validation via regex.
- Password: Minimum 8 characters (medical system baseline).
- License number: Non-empty string (format varies by country).
- Name: 1–255 characters.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class DoctorCreate(BaseModel):
    """
    Registration request schema.

    All fields required except specialisation.
    Password must be ≥8 characters.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Doctor's full name",
        examples=["Dr. Priya Sharma"],
    )
    email: EmailStr = Field(
        ...,
        description="Unique email address for login",
        examples=["priya.sharma@hospital.in"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 characters)",
        examples=["securepassword123"],
    )
    license_number: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Medical license/registration number",
        examples=["MCI-12345-2020"],
    )
    specialisation: str | None = Field(
        default=None,
        max_length=255,
        description="Medical specialisation",
        examples=["Cardiology"],
    )

    @field_validator("license_number")
    @classmethod
    def license_number_not_blank(cls, v: str) -> str:
        """Ensure license number is not just whitespace."""
        if not v.strip():
            raise ValueError("License number cannot be blank")
        return v.strip()

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip()


class DoctorLogin(BaseModel):
    """
    Login request schema.

    Uses email + password (not username) because email is
    the unique identifier for doctors.
    """

    email: EmailStr = Field(
        ...,
        description="Registered email address",
        examples=["priya.sharma@hospital.in"],
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Account password",
        examples=["securepassword123"],
    )


class DoctorResponse(BaseModel):
    """
    Doctor profile response schema.

    Security: hashed_password is excluded — this schema defines
    exactly what information leaves the API boundary.
    """

    id: int
    name: str
    email: str
    license_number: str
    specialisation: str | None = None
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """
    Login response with JWT token and doctor profile.

    token_type is always "bearer" — standard OAuth2 convention.
    The doctor object is included so the client has profile data
    immediately without a separate /me request.
    """

    access_token: str
    token_type: str = "bearer"
    doctor: DoctorResponse
