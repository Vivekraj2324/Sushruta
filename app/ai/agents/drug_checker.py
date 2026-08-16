"""
Sushruta — Drug Interaction Checker Agent
===========================================

Analyzes a list of patient medications to identify potential drug-drug interactions
and returns severity levels, mechanisms, and clinical advice.
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

class DrugInteractionDetail(BaseModel):
    """Detailed information for a single drug-drug interaction."""
    drugs: List[str] = Field(description="The list of 2 or more drugs that interact.")
    severity: str = Field(description="Severity level: HIGH, MODERATE, or MINOR.")
    description: str = Field(description="Explanation of why these drugs interact and the physiological mechanism.")
    clinical_advice: str = Field(description="Clinical advice for the doctor on how to manage this interaction.")

class DrugInteractionResponse(BaseModel):
    """Structured response for drug interaction checks."""
    has_interactions: bool = Field(description="Whether any interactions were found among the medications.")
    interactions: List[DrugInteractionDetail] = Field(default=[], description="List of detected drug-drug interactions.")

async def check_drug_interactions(medications: List[str]) -> Optional[dict]:
    """
    Check a list of medications for potential drug-drug interactions.

    Parameters
    ----------
    medications : List[str]
        List of medication names (e.g. ['Aspirin', 'Warfarin']).

    Returns
    -------
    dict | None
        Dict containing interaction details matching DrugInteractionResponse schema, or None if failed.
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured — skipping drug interaction check")
        return None

    if len(medications) < 2:
        return {
            "has_interactions": False,
            "interactions": []
        }

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Resilient wrapper for network/rate-limit hiccups
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True
        )
        def _call_gemini_api():
            return client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=f"Analyze the following list of medications for drug-drug interactions:\n\n{', '.join(medications)}",
                config=types.GenerateContentConfig(
                    system_instruction=get_prompt("drug_checker", "v1"),
                    temperature=settings.LLM_TEMPERATURE,
                    response_mime_type="application/json",
                    response_schema=DrugInteractionResponse,
                ),
            )

        response = _call_gemini_api()

        # Parse JSON response
        import json
        data = json.loads(response.text)
        return data

    except Exception as e:
        logger.error(f"Drug interaction check failed: {e}")
        return None
