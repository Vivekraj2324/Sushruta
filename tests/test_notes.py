"""
Sushruta — Clinical Note API Tests
====================================

Integration tests for the clinical notes API endpoints.
"""

from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClinicalNote

class TestClinicalNotes:
    """Tests for notes API endpoints."""

    @pytest.mark.asyncio
    @patch("app.services.note_service.generate_clinical_note")
    async def test_generate_note_draft_success(
        self, mock_generate, client: AsyncClient, auth_headers: dict
    ):
        """AI note generation mock test."""
        # Create patient
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Note Patient", "age": 50, "gender": "female"},
        )
        patient_id = patient_resp.json()["id"]

        # Mock the note writer agent response
        mock_generate.return_value = {
            "subjective": "Chief complaint of chest pain.",
            "objective": "Vitals stable, normal ECG.",
            "assessment": "Angina pectoris.",
            "plan": "Schedule coronary angiogram.",
            "clinical_summary": "Stable patient presenting with chest pain.",
            "formatted_note": "# SOAP Note\n\n## Subjective\nChief complaint...",
        }

        # Call generate endpoint
        response = await client.post(
            "/api/v1/notes/generate",
            headers=auth_headers,
            json={
                "patient_id": patient_id,
                "raw_input": "Patient reports chest pain for 3 days. ECG is normal.",
                "consultation_date": "2026-06-12T12:00:00Z",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["patient_id"] == patient_id
        assert data["is_draft"] is True
        assert "SOAP Note" in data["generated_note"]
        assert data["note_type"] == "SOAP"

    @pytest.mark.asyncio
    async def test_create_note_manual(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Create a clinical note manually."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Manual Note Patient", "age": 28, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        response = await client.post(
            "/api/v1/notes",
            headers=auth_headers,
            json={
                "patient_id": patient_id,
                "raw_input": "Direct patient encounter dictation.",
                "generated_note": "# Manual SOAP Note\n\nContent...",
                "consultation_date": "2026-06-12T14:00:00Z",
                "is_draft": False,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["patient_id"] == patient_id
        assert data["is_draft"] is False
        assert data["generated_note"] == "# Manual SOAP Note\n\nContent..."

    @pytest.mark.asyncio
    async def test_note_ownership_isolation(
        self, client: AsyncClient, auth_headers: dict, second_doctor_headers: dict
    ):
        """Verify Doctor A cannot access Doctor B's patient notes."""
        # Doctor A creates patient
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Patient A", "age": 40, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        # Doctor B tries to create note for Doctor A's patient
        response = await client.post(
            "/api/v1/notes",
            headers=second_doctor_headers,
            json={
                "patient_id": patient_id,
                "raw_input": "Intrusion attempt raw input.",
                "generated_note": "Intrusion details.",
                "consultation_date": "2026-06-12T15:00:00Z",
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_and_update_note(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Get note detail and partially update it."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Edit Patient", "age": 35, "gender": "female"},
        )
        patient_id = patient_resp.json()["id"]

        # Create note draft
        note_resp = await client.post(
            "/api/v1/notes",
            headers=auth_headers,
            json={
                "patient_id": patient_id,
                "raw_input": "Encounter text.",
                "generated_note": "Draft SOAP content.",
                "consultation_date": "2026-06-12T10:00:00Z",
                "is_draft": True,
            },
        )
        note_id = note_resp.json()["id"]

        # Get note
        get_resp = await client.get(
            f"/api/v1/notes/{note_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["raw_input"] == "Encounter text."

        # Update note
        update_resp = await client.patch(
            f"/api/v1/notes/{note_id}",
            headers=auth_headers,
            json={
                "generated_note": "Finalized SOAP note content.",
                "is_draft": False,
            },
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["generated_note"] == "Finalized SOAP note content."
        assert data["is_draft"] is False

    @pytest.mark.asyncio
    async def test_delete_note(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        """Delete clinical note and check it is deleted from DB."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Delete Patient", "age": 60, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        note_resp = await client.post(
            "/api/v1/notes",
            headers=auth_headers,
            json={
                "patient_id": patient_id,
                "raw_input": "Trash note.",
                "consultation_date": "2026-06-12T09:00:00Z",
            },
        )
        note_id = note_resp.json()["id"]

        # Delete note
        del_resp = await client.delete(
            f"/api/v1/notes/{note_id}",
            headers=auth_headers,
        )
        assert del_resp.status_code == 200

        # Try to retrieve note
        get_resp = await client.get(
            f"/api/v1/notes/{note_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 404
