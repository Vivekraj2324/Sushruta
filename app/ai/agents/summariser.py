"""
Sushruta — Patient Summariser Agent
====================================

Synthesizes a comprehensive clinical patient summary from patient records,
medical history, allergies, document chunks (RAG), and previous clinical notes.
"""

import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.ai.prompts import get_prompt

logger = logging.getLogger(__name__)
settings = get_settings()

class ChronicCondition(BaseModel):
    """Represents a medical problem or chronic condition."""
    condition: str = Field(description="Name of the condition (e.g., Hypertension).")
    status: str = Field(description="Status of the condition (e.g., active, stable, controlled, resolved).")
    notes: str = Field(description="Brief clinical details, treatment, or notes.")

class PatientSummaryResponse(BaseModel):
    """Structured clinical patient summary response."""
    active_problems: List[ChronicCondition] = Field(description="List of active chronic or acute medical conditions.")
    allergies: List[str] = Field(description="List of patient allergies.")
    current_medications: List[str] = Field(description="List of current medications patient is taking.")
    recent_developments: str = Field(description="Summary of recent consultations, diagnostic findings, or hospitalizations.")
    clinical_recommendations: str = Field(description="Recommendations or guidance for future follow-up care.")
    brief_narrative: str = Field(description="A concise clinical narrative overview of the patient's state.")

async def generate_patient_summary(
    patient_details: dict,
    document_excerpts: List[str],
    previous_notes: List[str],
) -> Optional[dict]:
    """
    Generate a patient summary by synthesizing demographic info and clinical records.

    Parameters
    ----------
    patient_details : dict
        Patient details (name, age, gender, allergies, medical_history).
    document_excerpts : List[str]
        Text segments retrieved from patient documents.
    previous_notes : List[str]
        Previous clinical notes text.

    Returns
    -------
    dict | None
        Dict matching PatientSummaryResponse schema, or None if failed.
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured — skipping patient summary generation")
        return None

    excerpts_text = "\n\n---\n\n".join(document_excerpts) if document_excerpts else "No medical documents uploaded or processed."
    notes_text = "\n\n---\n\n".join(previous_notes) if previous_notes else "No previous clinical notes documented."

    prompt = f"""Generate a patient summary based on the following patient records:

PATIENT DEMOGRAPHICS & BASIC PROFILE:
- Name: {patient_details.get('name')}
- Age: {patient_details.get('age')}
- Gender: {patient_details.get('gender')}
- Documented Allergies: {patient_details.get('allergies', 'None documented')}
- Medical History: {patient_details.get('medical_history', 'None documented')}

PREVIOUS CLINICAL NOTES:
{notes_text}

EXTRACTED MEDICAL RECORD EXCERPTS (RAG CONTEXT):
{excerpts_text}
"""

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Resilient API invocation wrapper
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True
        )
        def _call_gemini_api():
            return client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=get_prompt("summariser", "v1"),
                    temperature=settings.LLM_TEMPERATURE,
                    response_mime_type="application/json",
                    response_schema=PatientSummaryResponse,
                ),
            )

        response = _call_gemini_api()

        # Parse JSON response
        import json
        data = json.loads(response.text)
        return data

    except Exception as e:
        logger.error(f"Patient summary generation failed: {e}")
        return None
