"""
Sushruta — Authentication Tests
=================================

Tests for doctor registration, login, and profile access.

Coverage:
- Password hashing and verification (unit tests).
- JWT creation and validation (unit tests).
- Registration success and duplicate rejection (integration tests).
- Login success and failure (integration tests).
- Profile access with and without authentication (integration tests).
"""

import pytest
from httpx import AsyncClient

from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


# ══════════════════════════════════════════════════════════════════
# UNIT TESTS — Security Utilities
# ══════════════════════════════════════════════════════════════════


class TestPasswordHashing:
    """Test bcrypt password hashing and verification."""

    def test_hash_password_returns_hash(self):
        """Hashing produces a bcrypt hash string, not the original password."""
        password = "securepassword123"
        hashed = hash_password(password)
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt identifier

    def test_verify_correct_password(self):
        """Correct password verifies against its hash."""
        password = "securepassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        """Wrong password fails verification."""
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt uses random salt — same password produces different hashes."""
        password = "securepassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # Different salts
        # But both verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWT:
    """Test JWT token creation and verification."""

    def test_create_token_returns_string(self):
        """Token creation returns a non-empty string."""
        token = create_access_token(data={"sub": "1", "email": "test@test.com"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        """Valid token decodes to the original claims."""
        data = {"sub": "42", "email": "doctor@hospital.in"}
        token = create_access_token(data=data)
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["email"] == "doctor@hospital.in"
        assert "exp" in payload
        assert "iat" in payload

    def test_decode_invalid_token(self):
        """Tampered/invalid token returns None."""
        payload = decode_token("this.is.not.a.valid.jwt")
        assert payload is None

    def test_decode_expired_token(self):
        """Expired token returns None."""
        from datetime import timedelta

        token = create_access_token(
            data={"sub": "1", "email": "test@test.com"},
            expires_delta=timedelta(seconds=-1),  # Already expired
        )
        payload = decode_token(token)
        assert payload is None


# ══════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — Auth Endpoints
# ══════════════════════════════════════════════════════════════════


class TestRegistration:
    """Test POST /api/v1/auth/register."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Successful registration returns 201 with doctor profile (no password)."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Dr. Priya Sharma",
                "email": "priya@hospital.in",
                "password": "securepassword123",
                "license_number": "MCI-12345",
                "specialisation": "Cardiology",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Dr. Priya Sharma"
        assert data["email"] == "priya@hospital.in"
        assert data["license_number"] == "MCI-12345"
        assert data["specialisation"] == "Cardiology"
        assert "password" not in data
        assert "hashed_password" not in data
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient):
        """Duplicate email returns 400."""
        doctor_data = {
            "name": "Dr. First",
            "email": "duplicate@hospital.in",
            "password": "securepassword123",
            "license_number": "MCI-DUP-001",
        }
        # First registration
        response1 = await client.post("/api/v1/auth/register", json=doctor_data)
        assert response1.status_code == 201

        # Duplicate email
        doctor_data["license_number"] = "MCI-DUP-002"  # Different license
        response2 = await client.post("/api/v1/auth/register", json=doctor_data)
        assert response2.status_code == 400
        assert "email" in response2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_duplicate_license(self, client: AsyncClient):
        """Duplicate license number returns 400."""
        # First registration
        await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Dr. First",
                "email": "first@hospital.in",
                "password": "securepassword123",
                "license_number": "MCI-SAME-001",
            },
        )
        # Same license, different email
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Dr. Second",
                "email": "second_lic@hospital.in",
                "password": "securepassword123",
                "license_number": "MCI-SAME-001",
            },
        )
        assert response.status_code == 400
        assert "license" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_short_password(self, client: AsyncClient):
        """Password shorter than 8 characters returns 422."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": "Dr. Short",
                "email": "short@hospital.in",
                "password": "short",
                "license_number": "MCI-SHORT-001",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, client: AsyncClient):
        """Missing required fields returns 422."""
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "Dr. Incomplete"},
        )
        assert response.status_code == 422


class TestLogin:
    """Test POST /api/v1/auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(
        self, client: AsyncClient, registered_doctor: dict
    ):
        """Successful login returns 200 with token and doctor profile."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@hospital.in",
                "password": "securepassword123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["doctor"]["email"] == "test@hospital.in"
        assert "password" not in data["doctor"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self, client: AsyncClient, registered_doctor: dict
    ):
        """Wrong password returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@hospital.in",
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, client: AsyncClient):
        """Non-existent email returns 401 (not 404 — no information leakage)."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@hospital.in",
                "password": "somepassword123",
            },
        )
        assert response.status_code == 401


class TestProfile:
    """Test GET /api/v1/auth/me."""

    @pytest.mark.asyncio
    async def test_get_profile_authenticated(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Authenticated request returns doctor profile."""
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@hospital.in"
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_get_profile_unauthenticated(self, client: AsyncClient):
        """Request without token returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_profile_invalid_token(self, client: AsyncClient):
        """Request with invalid token returns 401."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401
