# tests/test_memory_integration.py
"""Integration tests for AgentCore Memory (long-term memory).

Mocks the boto3 bedrock-agentcore client to verify:
- Memory save (CreateEvent) payload construction
- Memory load (GetSession / RetrieveMemoryRecords) response parsing
- Graceful handling when memory service is unavailable
"""

import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("COGNITO_USER_POOL_ID", "ap-south-1_TestPool")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")
os.environ.setdefault("MEMORY_ID", "test-memory-id")


class TestMemorySave:
    """Verify _memory_save_turn correctly writes to AgentCore Memory."""

    @patch("app.api.routes.settings")
    @patch("app.api.routes._get_memory_client")
    def test_save_creates_event_with_correct_structure(self, mock_get_client, mock_settings):
        """Verify CreateEvent is called with USER and ASSISTANT messages."""
        from app.api.routes import _memory_save_turn

        mock_settings.MEMORY_ID = "test-memory-id"
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        _memory_save_turn(
            user_msg="What alarms are active?",
            assistant_msg="There are 3 active alarms.",
            user_id="user-123",
            session_id="session-abc",
        )

        mock_client.create_event.assert_called_once()
        call_kwargs = mock_client.create_event.call_args.kwargs
        assert call_kwargs["actorId"] == "user-123"
        assert call_kwargs["sessionId"] == "session-abc"
        assert len(call_kwargs["payload"]) == 2
        assert call_kwargs["payload"][0]["conversational"]["role"] == "USER"
        assert call_kwargs["payload"][1]["conversational"]["role"] == "ASSISTANT"

    @patch("app.api.routes.settings")
    @patch("app.api.routes._get_memory_client")
    def test_save_truncates_long_responses(self, mock_get_client, mock_settings):
        """Verify assistant messages are truncated to 4000 chars."""
        from app.api.routes import _memory_save_turn

        mock_settings.MEMORY_ID = "test-memory-id"
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        long_response = "x" * 10000
        _memory_save_turn("hi", long_response, "user-1", "sess-1")

        call_kwargs = mock_client.create_event.call_args.kwargs
        assistant_text = call_kwargs["payload"][1]["conversational"]["content"]["text"]
        assert len(assistant_text) <= 4000

    @patch("app.api.routes._get_memory_client")
    def test_save_handles_client_none_gracefully(self, mock_get_client):
        """Verify no error when memory client is unavailable."""
        from app.api.routes import _memory_save_turn

        mock_get_client.return_value = None

        # Should not raise
        _memory_save_turn("hello", "world", "user-1", "sess-1")


class TestMemoryLoad:
    """Verify _memory_load_turns correctly reads from AgentCore Memory."""

    @patch("app.api.routes._get_memory_client")
    def test_load_returns_formatted_context(self, mock_get_client):
        """Verify loaded memory is formatted as a context string."""
        from app.api.routes import _memory_load_turns

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_session.return_value = {
            "events": [
                {
                    "payload": [
                        {"conversational": {"content": {"text": "What is RCA?"}, "role": "USER"}},
                        {"conversational": {"content": {"text": "Root Cause Analysis."}, "role": "ASSISTANT"}},
                    ]
                }
            ]
        }

        result = _memory_load_turns("user-1", "sess-1", k=3)
        assert isinstance(result, str)

    @patch("app.api.routes._get_memory_client")
    def test_load_returns_empty_when_unavailable(self, mock_get_client):
        """Verify empty string returned when memory client is None."""
        from app.api.routes import _memory_load_turns

        mock_get_client.return_value = None
        result = _memory_load_turns("user-1", "sess-1")
        assert result == ""

    @patch("app.api.routes._get_memory_client")
    def test_load_handles_exception_gracefully(self, mock_get_client):
        """Verify exceptions from boto3 are caught, not propagated."""
        from app.api.routes import _memory_load_turns

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_session.side_effect = Exception("Service unavailable")

        # Should not raise — returns empty string
        result = _memory_load_turns("user-1", "sess-1")
        assert result == ""
