# tests/conftest.py
"""Shared test fixtures for the MSP Assistant backend."""

import os
import pytest
from unittest.mock import patch

# Set test environment variables before importing app
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("COGNITO_USER_POOL_ID", "ap-south-1_TestPool")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")
os.environ.setdefault("ENVIRONMENT", "test")


@pytest.fixture
def test_user():
    """Mock authenticated user payload."""
    return {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "username": "testuser",
        "token_use": "id",
        "auth_time": 1700000000,
        "exp": 9999999999,
    }
