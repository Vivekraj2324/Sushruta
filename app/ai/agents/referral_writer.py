"""
Sushruta — Referral Letter Writer Agent
========================================

Generates formal clinical referral letters from referring doctors to specialists
based on patient details, clinical findings, and referral reasons.
"""

import logging
from typing import Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.ai.prompts import get_prompt

logger = logging.getLogger(__name__)
settings = get_settings()

class ReferralLetterResponse(BaseModel):
    """Structured response for referral letters."""
    recipient_specialist: str = Field(description="Target specialty or doctor name.")
    sender_doctor: str = Field(description="Referring doctor's name.")
    patient_name: str = Field(description="Patient's name.")
    subject: str = Field(description="Subject line of the referral letter.")
    body: str = Field(description="The formal clinical body of the letter, structured with medical history, findings, and request.")
    formatted_letter: str = Field(description="The complete, ready-to-print formatted letter in Markdown.")

async def generate_referral_letter(
    patient_details: dict,
    clinical_context: str,
    target_specialist: str,
    sender_doctor_name: str,
    referral_reason: str,
) -> Optional[dict]:
    """
    Generate a formal referral letter.

    Parameters
    ----------
    patient_details : dict
        Patient attributes (name, age, gender, blood_group, allergies, medical_history).
    clinical_context : str
        Clinical findings, notes or document summaries.
    target_specialist : str
        Target specialty or doctor name.
    sender_doctor_name : str
        Referring doctor's name.
    referral_reason : str
        Why the patient is being referred.

    Returns
    -------
    dict | None
        Dict matching ReferralLetterResponse schema, or None if failed.
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured — skipping referral letter generation")
        return None

    # Construct input prompt
    prompt = f"""Generate a referral letter with the following information:

REFERRING DOCTOR: {sender_doctor_name}
TARGET RECIPIENT: {target_specialist}
REFERRAL REASON: {referral_reason}

PATIENT DETAILS:
- Name: {patient_details.get('name')}
- Age: {patient_details.get('age')}
- Gender: {patient_details.get('gender')}
- Blood Group: {patient_details.get('blood_group', 'Not documented')}
- Allergies: {patient_details.get('allergies', 'None documented')}
- Medical History: {patient_details.get('medical_history', 'None documented')}

CLINICAL CONTEXT:
{clinical_context}
"""

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Resilient API wrapper
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
                    system_instruction=get_prompt("referral_writer", "v1"),
                    temperature=settings.LLM_TEMPERATURE,
                    response_mime_type="application/json",
                    response_schema=ReferralLetterResponse,
                ),
            )

        response = _call_gemini_api()

        # Parse JSON response
        import json
        data = json.loads(response.text)
        return data

    except Exception as e:
        logger.error(f"Referral letter generation failed: {e}")
        return None
