"""
Sushruta — Document Tests
===========================

Tests for document upload, listing, retrieval, and deletion.

Coverage:
- Upload valid PDF (mocked — uses in-memory file).
- Upload file too large (413).
- Upload unsupported file type (415).
- List documents per patient.
- Get document detail.
- Soft delete document.
- Audit log creation on patient create (cross-cutting verification).

Note: Since we use in-memory SQLite for tests, actual PDF text
extraction is tested via a small helper. The upload tests focus
on the API contract, not file I/O.
"""

import io
import os

import pytest
from httpx import AsyncClient

from app.db.models import AuditLog


class TestUploadDocument:
    """Test POST /api/v1/patients/{patient_id}/documents."""

    @pytest.mark.asyncio
    async def test_upload_document_valid_pdf(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Upload a valid PDF file returns 201."""
        # Create a patient first
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Doc Patient", "age": 30, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        # Create a minimal PDF-like file (won't extract text, but passes type check)
        pdf_content = b"%PDF-1.4 fake pdf content for testing"
        files = {"file": ("test_report.pdf", io.BytesIO(pdf_content), "application/pdf")}

        response = await client.post(
            f"/api/v1/patients/{patient_id}/documents",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "test_report.pdf"
        assert data["file_type"] == ".pdf"
        assert data["processing_status"] in ("uploaded", "ready", "failed")
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_upload_document_too_large(
        self, client: AsyncClient, auth_headers: dict
    ):
        """File exceeding MAX_FILE_SIZE_MB returns 413."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Big File Patient", "age": 30, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        # Create a file larger than 10MB
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        files = {"file": ("large.pdf", io.BytesIO(large_content), "application/pdf")}

        response = await client.post(
            f"/api/v1/patients/{patient_id}/documents",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_upload_document_invalid_type(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Unsupported file type returns 415."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Bad Type Patient", "age": 30, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        files = {"file": ("malware.exe", io.BytesIO(b"bad"), "application/octet-stream")}

        response = await client.post(
            f"/api/v1/patients/{patient_id}/documents",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 415

    @pytest.mark.asyncio
    async def test_upload_document_nonexistent_patient(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Upload to non-existent patient returns 404."""
        files = {"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
        response = await client.post(
            "/api/v1/patients/99999/documents",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 404


class TestListDocuments:
    """Test GET /api/v1/patients/{patient_id}/documents."""

    @pytest.mark.asyncio
    async def test_list_documents_empty(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Empty document list returns valid structure."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "No Docs", "age": 30, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        response = await client.get(
            f"/api/v1/patients/{patient_id}/documents",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["documents"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_documents_with_uploads(
        self, client: AsyncClient, auth_headers: dict
    ):
        """List returns uploaded documents."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Has Docs", "age": 30, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        # Upload two documents
        for name in ["report1.pdf", "report2.pdf"]:
            files = {"file": (name, io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
            await client.post(
                f"/api/v1/patients/{patient_id}/documents",
                headers=auth_headers,
                files=files,
            )

        response = await client.get(
            f"/api/v1/patients/{patient_id}/documents",
            headers=auth_headers,
        )
        data = response.json()
        assert data["total"] == 2
        assert len(data["documents"]) == 2


class TestGetDocument:
    """Test GET /api/v1/patients/{patient_id}/documents/{document_id}."""

    @pytest.mark.asyncio
    async def test_get_document_detail(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Get document returns full details including extracted_text field."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Detail Patient", "age": 30, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        files = {"file": ("detail.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
        upload_resp = await client.post(
            f"/api/v1/patients/{patient_id}/documents",
            headers=auth_headers,
            files=files,
        )
        doc_id = upload_resp.json()["id"]

        response = await client.get(
            f"/api/v1/patients/{patient_id}/documents/{doc_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["original_filename"] == "detail.pdf"
        assert "extracted_text" in data  # Detail response includes this field
        assert "stored_filename" in data

    @pytest.mark.asyncio
    async def test_get_document_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Non-existent document returns 404."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "No Doc", "age": 30, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        response = await client.get(
            f"/api/v1/patients/{patient_id}/documents/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestDeleteDocument:
    """Test DELETE /api/v1/patients/{patient_id}/documents/{document_id}."""

    @pytest.mark.asyncio
    async def test_soft_delete_document(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Soft delete removes document from list but doesn't hard-delete."""
        patient_resp = await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Delete Doc Patient", "age": 30, "gender": "male"},
        )
        patient_id = patient_resp.json()["id"]

        # Upload
        files = {"file": ("to_delete.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
        upload_resp = await client.post(
            f"/api/v1/patients/{patient_id}/documents",
            headers=auth_headers,
            files=files,
        )
        doc_id = upload_resp.json()["id"]

        # Delete
        delete_resp = await client.delete(
            f"/api/v1/patients/{patient_id}/documents/{doc_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200
        assert "removed" in delete_resp.json()["message"].lower()

        # Should not appear in list
        list_resp = await client.get(
            f"/api/v1/patients/{patient_id}/documents",
            headers=auth_headers,
        )
        assert list_resp.json()["total"] == 0


class TestAuditLog:
    """Cross-cutting test: verify audit logs are created."""

    @pytest.mark.asyncio
    async def test_audit_log_created_on_patient_create(
        self, client: AsyncClient, auth_headers: dict, db_session
    ):
        """Creating a patient generates an audit log entry."""
        from sqlalchemy import select

        await client.post(
            "/api/v1/patients",
            headers=auth_headers,
            json={"name": "Audit Test", "age": 30, "gender": "male"},
        )

        # Check audit_logs table directly
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "PATIENT_CREATED")
        )
        logs = result.scalars().all()
        assert len(logs) >= 1
        assert logs[0].resource_type == "patient"


class TestHealthCheck:
    """Test GET /health."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health check returns 200 with status info."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "app" in data
        assert "version" in data
