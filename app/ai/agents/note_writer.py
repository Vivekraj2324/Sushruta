"""
Sushruta — Clinical Note Writer Agent
======================================

Generates structured SOAP (Subjective, Objective, Assessment, Plan) notes
from raw doctor-patient dialogue or consultation transcripts.
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

class SOAPNoteSchema(BaseModel):
    """Structured SOAP note JSON output schema."""
    subjective: str = Field(description="Patient's reports, symptoms, history, and chief complaints.")
    objective: str = Field(description="Physical exam findings, vitals, lab results, and observations.")
    assessment: str = Field(description="Diagnosis, differential diagnoses, and clinical reasoning.")
    plan: str = Field(description="Treatment, medications, follow-up, and next steps.")
    clinical_summary: str = Field(description="A brief 1-2 sentence high-level summary of the encounter.")

def format_soap_note_markdown(soap: SOAPNoteSchema) -> str:
    """Format the structured SOAP note into a clean Markdown string."""
    return f"""# Clinical Note (SOAP format)

## Subjective
{soap.subjective}

## Objective
{soap.objective}

## Assessment
{soap.assessment}

## Plan
{soap.plan}

---
**Clinical Summary:** {soap.clinical_summary}"""

async def generate_clinical_note(raw_input: str) -> Optional[dict]:
    """
    Generate a SOAP clinical note from raw dialogue or dictation.

    Parameters
    ----------
    raw_input : str
        The raw dialogue transcript or doctor dictation.

    Returns
    -------
    dict | None
        Dict containing SOAP note parts and formatted markdown string, or None if failed.
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured — skipping clinical note generation")
        return None

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
                contents=f"Generate a SOAP note for the following raw encounter:\n\n{raw_input}",
                config=types.GenerateContentConfig(
                    system_instruction=get_prompt("note_writer", "v1"),
                    temperature=settings.LLM_TEMPERATURE,
                    response_mime_type="application/json",
                    response_schema=SOAPNoteSchema,
                ),
            )

        response = _call_gemini_api()

        # Parse JSON response
        import json
        data = json.loads(response.text)
        soap_obj = SOAPNoteSchema(**data)
        
        return {
            "subjective": soap_obj.subjective,
            "objective": soap_obj.objective,
            "assessment": soap_obj.assessment,
            "plan": soap_obj.plan,
            "clinical_summary": soap_obj.clinical_summary,
            "formatted_note": format_soap_note_markdown(soap_obj),
        }

    except Exception as e:
        logger.error(f"Clinical note generation failed: {e}")
        return None
