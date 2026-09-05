# tests/test_config.py
"""Tests for configuration management."""

import os
import sys

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("COGNITO_USER_POOL_ID", "ap-south-1_TestPool")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")


class TestConfig:
    """Verify Settings loads correctly and sensitive fields are protected."""

    def test_settings_loads(self):
        """Settings should load without errors."""
        from app.core.config import settings
        assert settings.AWS_REGION == "ap-south-1"

    def test_sensitive_fields_hidden_in_repr(self):
        """JIRA_API_TOKEN and COGNITO_CLIENT_SECRET should not appear in repr."""
        from app.core.config import Settings
        s = Settings(
            COGNITO_USER_POOL_ID="test",
            COGNITO_CLIENT_ID="test",
            JIRA_API_TOKEN="super-secret-token",
            COGNITO_CLIENT_SECRET="another-secret",
        )
        repr_str = repr(s)
        assert "super-secret-token" not in repr_str
        assert "another-secret" not in repr_str

    def test_default_values(self):
        """Default config values should be set."""
        from app.core.config import settings
        assert settings.GUARD_MODE == "demo"
        assert settings.REMEDIATION_DETECTION_MODE == "llm"
        assert settings.VERIFICATION_MAX_RETRIES == 3
        assert settings.VERIFICATION_RETRY_DELAY_SECONDS == 30

    def test_api_version(self):
        """API version should default to v1."""
        from app.core.config import settings
        assert settings.API_VERSION == "v1"
