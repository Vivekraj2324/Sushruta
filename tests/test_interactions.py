"""
Sushruta — Clinical Interaction API Tests
=============================================

Integration tests for the clinical interactions and drug checking API endpoints.
"""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient

class TestClinicalInteractions:
    """Tests for interactions API endpoints."""

    @pytest.mark.asyncio
    async def test_record_interaction_success(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Record patient encounter successfully."""
        # Create patient
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Encounter Patient", "age": 32, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        # Record encounter
        response = await client.post(
            "/api/v1/interactions",
            headers=auth_headers,
            json={
                "patient_id": patient_id,
                "interaction_date": "2026-06-12T10:00:00Z",
                "type": "Routine Follow-up",
                "notes": "Patient reports compliance with medication, BP is 120/80.",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["patient_id"] == patient_id
        assert data["type"] == "Routine Follow-up"
        assert data["notes"] == "Patient reports compliance with medication, BP is 120/80."

    @pytest.mark.asyncio
    async def test_list_interactions_success(
        self, client: AsyncClient, auth_headers: dict
    ):
        """List encounters recorded for a patient."""
        # Create patient
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "List Enc Patient", "age": 44, "gender": "female"},
        )
        patient_id = patient_resp.json()["id"]

        # Record two encounters
        await client.post(
            "/api/v1/interactions",
            headers=auth_headers,
            json={
                "patient_id": patient_id,
                "interaction_date": "2026-06-12T09:00:00Z",
                "type": "Initial Consultation",
                "notes": "First checkup.",
            },
        )
        await client.post(
            "/api/v1/interactions",
            headers=auth_headers,
            json={
                "patient_id": patient_id,
                "interaction_date": "2026-06-12T15:00:00Z",
                "type": "Follow-up Call",
                "notes": "Telephone follow-up.",
            },
        )

        # List
        response = await client.get(
            f"/api/v1/interactions/patient/{patient_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # Ordered by date descending
        assert data[0]["type"] == "Follow-up Call"
        assert data[1]["type"] == "Initial Consultation"

    @pytest.mark.asyncio
    @patch("app.services.interaction_service.check_drug_interactions")
    async def test_drug_interaction_check(
        self, mock_check, client: AsyncClient, auth_headers: dict
    ):
        """Stateless drug interaction check mock test."""
        # Mock pharmacologist agent response
        mock_check.return_value = {
            "has_interactions": True,
            "interactions": [
                {
                    "drugs": ["Aspirin", "Warfarin"],
                    "severity": "HIGH",
                    "description": "Increased risk of severe bleeding due to additive pharmacodynamic effects.",
                    "clinical_advice": "Avoid concurrent use or monitor INR daily.",
                }
            ],
        }

        # Call check endpoint
        response = await client.post(
            "/api/v1/interactions/check",
            headers=auth_headers,
            json={"medications": ["Aspirin", "Warfarin"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_interactions"] is True
        assert len(data["interactions"]) == 1
        assert data["interactions"][0]["severity"] == "HIGH"
        assert "Aspirin" in data["interactions"][0]["drugs"]
