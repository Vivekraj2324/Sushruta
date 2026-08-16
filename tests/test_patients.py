"""
Sushruta — Patient Tests
==========================

Tests for patient CRUD operations.

Coverage:
- Create patient (success + validation).
- List patients (pagination, search, only own patients).
- Get patient (success + not found).
- Update patient (partial update, validation).
- Soft delete (deactivation, not hard delete).
- Data isolation (doctor A cannot see doctor B's patients).
"""

import pytest
from httpx import AsyncClient


class TestCreatePatient:
    """Test POST /api/v1/patients."""

    @pytest.mark.asyncio
    async def test_create_patient_success(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Create a patient with all fields returns 201."""
        response = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={
                "name": "Rajesh Kumar",
                "age": 45,
                "gender": "male",
                "blood_group": "B+",
                "allergies": "Penicillin",
                "medical_history": "Type 2 Diabetes since 2015",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Rajesh Kumar"
        assert data["age"] == 45
        assert data["gender"] == "male"
        assert data["blood_group"] == "B+"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_patient_minimal(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Create a patient with only required fields returns 201."""
        response = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={
                "name": "Anita Desai",
                "age": 30,
                "gender": "female",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["blood_group"] is None
        assert data["allergies"] is None

    @pytest.mark.asyncio
    async def test_create_patient_invalid_age(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Age outside 0-150 returns 422."""
        response = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Invalid", "age": 200, "gender": "male"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_patient_invalid_blood_group(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Invalid blood group returns 422."""
        response = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Invalid", "age": 30, "gender": "male", "blood_group": "X+"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_patient_unauthenticated(self, client: AsyncClient):
        """Creating patient without auth returns 401."""
        response = await client.post(
            "/api/v1/patients",
            json={"name": "No Auth", "age": 30, "gender": "male"},
        )
        assert response.status_code == 401


class TestListPatients:
    """Test GET /api/v1/patients."""

    @pytest.mark.asyncio
    async def test_list_patients_empty(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Empty patient list returns valid structure with total=0."""
        response = await client.get("/api/v1/patients", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["patients"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_patients_with_data(
        self, client: AsyncClient, auth_headers: dict
    ):
        """List returns created patients."""
        # Create two patients
        await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Patient One", "age": 30, "gender": "male"},
        )
        await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Patient Two", "age": 40, "gender": "female"},
        )

        response = await client.get("/api/v1/patients", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["patients"]) == 2

    @pytest.mark.asyncio
    async def test_list_patients_search(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Search filter returns matching patients only."""
        await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Rajesh Kumar", "age": 45, "gender": "male"},
        )
        await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Anita Desai", "age": 30, "gender": "female"},
        )

        response = await client.get(
            "/api/v1/patients?search=Rajesh", headers=auth_headers
        )
        data = response.json()
        assert data["total"] == 1
        assert data["patients"][0]["name"] == "Rajesh Kumar"

    @pytest.mark.asyncio
    async def test_list_patients_only_own(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_doctor_headers: dict,
    ):
        """Doctor A cannot see Doctor B's patients."""
        # Doctor A creates a patient
        await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Doctor A Patient", "age": 30, "gender": "male"},
        )

        # Doctor B sees no patients
        response = await client.get(
            "/api/v1/patients", headers=second_doctor_headers
        )
        data = response.json()
        assert data["total"] == 0
        assert data["patients"] == []

    @pytest.mark.asyncio
    async def test_list_patients_pagination(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Pagination limits results correctly."""
        # Create 3 patients
        for i in range(3):
            await client.post(
                "/api/v1/patients",
                headers=auth_headers,
                json={"name": f"Patient {i}", "age": 30 + i, "gender": "male"},
            )

        # Page 1, limit 2
        response = await client.get(
            "/api/v1/patients?page=1&limit=2", headers=auth_headers
        )
        data = response.json()
        assert len(data["patients"]) == 2
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["limit"] == 2


class TestGetPatient:
    """Test GET /api/v1/patients/{patient_id}."""

    @pytest.mark.asyncio
    async def test_get_patient_success(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Get an existing patient returns 200 with full data."""
        create_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Get Test", "age": 50, "gender": "female"},
        )
        patient_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/patients/{patient_id}", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Get Test"

    @pytest.mark.asyncio
    async def test_get_patient_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Non-existent patient ID returns 404."""
        response = await client.get(
            "/api/v1/patients/99999", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_patient_ownership(
        self,
        client: AsyncClient,
        auth_headers: dict,
        second_doctor_headers: dict,
    ):
        """Doctor cannot access another doctor's patient."""
        # Doctor A creates a patient
        create_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Owned Patient", "age": 30, "gender": "male"},
        )
        patient_id = create_resp.json()["id"]

        # Doctor B tries to access it
        response = await client.get(
            f"/api/v1/patients/{patient_id}", headers=second_doctor_headers
        )
        assert response.status_code == 404


class TestUpdatePatient:
    """Test PATCH /api/v1/patients/{patient_id}."""

    @pytest.mark.asyncio
    async def test_update_patient_partial(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Partial update changes only sent fields."""
        create_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={
                "name": "Before Update",
                "age": 30,
                "gender": "male",
                "blood_group": "A+",
            },
        )
        patient_id = create_resp.json()["id"]

        # Update only the name
        response = await client.patch(
            f"/api/v1/patients/{patient_id}",
            headers=auth_headers,
            json={"name": "After Update"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "After Update"
        assert data["age"] == 30  # Unchanged
        assert data["blood_group"] == "A+"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_patient_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Update non-existent patient returns 404."""
        response = await client.patch(
            "/api/v1/patients/99999",
            headers=auth_headers,
            json={"name": "Ghost"},
        )
        assert response.status_code == 404


class TestDeletePatient:
    """Test DELETE /api/v1/patients/{patient_id}."""

    @pytest.mark.asyncio
    async def test_soft_delete_patient(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Soft delete deactivates patient — no longer appears in list."""
        create_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "To Delete", "age": 30, "gender": "male"},
        )
        patient_id = create_resp.json()["id"]

        # Delete
        delete_resp = await client.delete(
            f"/api/v1/patients/{patient_id}", headers=auth_headers
        )
        assert delete_resp.status_code == 200
        assert "deactivated" in delete_resp.json()["message"].lower()

        # Should not appear in list
        list_resp = await client.get("/api/v1/patients", headers=auth_headers)
        assert list_resp.json()["total"] == 0

        # Should not be accessible by ID
        get_resp = await client.get(
            f"/api/v1/patients/{patient_id}", headers=auth_headers
        )
        assert get_resp.status_code == 404
