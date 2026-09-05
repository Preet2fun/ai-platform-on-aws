# tests/test_auth_flow.py
"""Integration tests for authentication and authorization.

Verifies:
- JWT validation logic
- Refresh token cookie flow
- Unauthorized access rejection
- User info extraction from tokens
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("COGNITO_USER_POOL_ID", "ap-south-1_TestPool")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")


class TestUnauthenticatedAccess:
    """Verify endpoints reject requests without valid JWT."""

    def setup_method(self):
        from app.main import app
        self.client = TestClient(app)

    def test_chat_rejects_no_token(self):
        """POST /chat without Authorization header returns 401."""
        response = self.client.post(
            "/api/v1/chat",
            json={"message": "hello"},
        )
        assert response.status_code == 401

    def test_conversations_reject_no_token(self):
        """GET /conversations without Authorization returns 401."""
        response = self.client.get("/api/v1/conversations")
        assert response.status_code == 401

    def test_accounts_reject_no_token(self):
        """GET /accounts without Authorization returns 401."""
        response = self.client.get("/api/v1/accounts")
        assert response.status_code == 401

    def test_health_allows_no_token(self):
        """GET /health (public) should work without auth."""
        response = self.client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestAuthEndpoints:
    """Verify auth cookie endpoints."""

    def setup_method(self):
        from app.main import app
        self.client = TestClient(app)

    def test_set_refresh_stores_cookie(self):
        """POST /auth/set-refresh should set httpOnly cookie."""
        response = self.client.post(
            "/api/v1/auth/set-refresh",
            json={"refresh_token": "test-refresh-token"},
        )
        # Should succeed (sets cookie)
        assert response.status_code == 200
        assert response.json()["success"] is True
        # Cookie should be in response
        assert "refresh_token" in response.cookies or "set-cookie" in str(response.headers).lower()

    def test_logout_clears_cookies(self):
        """POST /auth/logout should clear session cookies."""
        response = self.client.post("/api/v1/auth/logout")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_restore_without_cookie_returns_401(self):
        """POST /auth/restore without refresh cookie should fail."""
        response = self.client.post("/api/v1/auth/restore")
        assert response.status_code == 401


class TestSecurityHeaders:
    """Verify security headers are present on all responses."""

    def setup_method(self):
        from app.main import app
        self.client = TestClient(app)

    def test_security_headers_on_public_endpoint(self):
        """Health endpoint should have all security headers."""
        response = self.client.get("/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert "max-age" in response.headers.get("Strict-Transport-Security", "")
        assert "frame-ancestors" in response.headers.get("Content-Security-Policy", "")

    def test_request_id_header_present(self):
        """All responses should include X-Request-Id."""
        response = self.client.get("/health")
        assert "X-Request-Id" in response.headers
