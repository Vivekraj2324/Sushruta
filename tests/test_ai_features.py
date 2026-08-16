"""
Sushruta — AI Features API Tests
===================================

Integration tests for patient summary and referral letter generation endpoints.
"""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient

class TestAIFeatures:
    """Tests for AI-powered patient summary and referral letter endpoints."""

    @pytest.mark.asyncio
    @patch("app.ai.agents.summariser.generate_patient_summary")
    async def test_get_patient_summary_success(
        self, mock_summary, client: AsyncClient, auth_headers: dict
    ):
        """Generate clinical patient summary mock test."""
        # Create patient
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={
                "name": "Summary Patient",
                "age": 65,
                "gender": "male",
                "allergies": "Sulfa drugs",
                "medical_history": "Type 2 Diabetes, Hypertension",
            },
        )
        patient_id = patient_resp.json()["id"]

        # Mock summariser agent response
        mock_summary.return_value = {
            "active_problems": [
                {"condition": "Type 2 Diabetes", "status": "active", "notes": "Managed with Metformin"},
                {"condition": "Hypertension", "status": "active", "notes": "Stable on Lisinopril"},
            ],
            "allergies": ["Sulfa drugs"],
            "current_medications": ["Metformin 500mg BID", "Lisinopril 10mg QD"],
            "recent_developments": "Routine checkup, vitals normal.",
            "clinical_recommendations": "Continue current therapy, check HbA1c in 3 months.",
            "brief_narrative": "65-year-old male with stable Type 2 Diabetes and controlled Hypertension.",
        }

        # Call endpoint
        response = await client.get(
            f"/api/v1/patients/{patient_id}/summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["brief_narrative"] == "65-year-old male with stable Type 2 Diabetes and controlled Hypertension."
        assert len(data["active_problems"]) == 2
        assert "Sulfa drugs" in data["allergies"]

    @pytest.mark.asyncio
    @patch("app.ai.agents.referral_writer.generate_referral_letter")
    async def test_generate_referral_letter_success(
        self, mock_referral, client: AsyncClient, auth_headers: dict
    ):
        """Generate clinical referral letter mock test."""
        # Create patient
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Referral Patient", "age": 55, "gender": "female"},
        )
        patient_id = patient_resp.json()["id"]

        # Mock referral letter agent response
        mock_referral.return_value = {
            "recipient_specialist": "Dr. Smith (Cardiology)",
            "sender_doctor": "Dr. Test Doctor",
            "patient_name": "Referral Patient",
            "subject": "Referral: Referral Patient, Age 55, Female",
            "body": "Dear Dr. Smith, I am writing to refer...",
            "formatted_letter": "# Medical Referral Letter\n\nDear Dr. Smith...",
        }

        # Call endpoint
        response = await client.post(
            f"/api/v1/patients/{patient_id}/referral",
            headers=auth_headers,
            json={
                "target_specialist": "Dr. Smith (Cardiology)",
                "referral_reason": "Evaluate chest tightness on exertion.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["recipient_specialist"] == "Dr. Smith (Cardiology)"
        assert "Medical Referral Letter" in data["formatted_letter"]
