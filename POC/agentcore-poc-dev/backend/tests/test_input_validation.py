# tests/test_input_validation.py
"""Tests for API input validation — ChatRequest model."""

import pytest
from pydantic import ValidationError
import sys
import os

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

# Must set env vars before importing the app modules
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("COGNITO_USER_POOL_ID", "ap-south-1_TestPool")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")

from app.api.routes import ChatRequest


class TestChatRequest:
    """Verify ChatRequest validation rules."""

    def test_valid_message(self):
        """Normal message should be accepted."""
        req = ChatRequest(message="Show me CloudWatch alarms")
        assert req.message == "Show me CloudWatch alarms"

    def test_message_max_length(self):
        """Message exceeding 10000 chars should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(message="x" * 10001)
        assert "max_length" in str(exc_info.value).lower() or "string_too_long" in str(exc_info.value).lower()

    def test_message_at_max_length(self):
        """Message exactly at 10000 chars should be accepted."""
        req = ChatRequest(message="x" * 10000)
        assert len(req.message) == 10000

    def test_account_name_sanitized(self):
        """Account name with unsafe chars should be sanitized."""
        req = ChatRequest(message="test", account_name="my-account_1")
        # Only lowercase alphanumeric and underscores survive
        assert req.account_name == "myaccount_1"

    def test_account_name_safe(self):
        """Clean account name should pass through."""
        req = ChatRequest(message="test", account_name="production")
        assert req.account_name == "production"

    def test_default_values(self):
        """Default values should be set correctly."""
        req = ChatRequest(message="hello")
        assert req.account_name == "default"
        assert req.workflow_enabled is False
        assert req.full_automation is False
        assert req.conversation_id is None
