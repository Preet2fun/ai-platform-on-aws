# tests/test_chat_routing.py
"""Integration tests for chat message routing logic.

Tests that messages are correctly classified and routed to the
appropriate specialist agent based on intent detection.
"""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("COGNITO_USER_POOL_ID", "ap-south-1_TestPool")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")


class TestAgentDetection:
    """Verify _detect_agent_stage correctly classifies user messages."""

    def setup_method(self):
        from app.api.routes import _detect_agent_stage
        self.detect = _detect_agent_stage

    def test_cloudwatch_alarm_query(self):
        result = self.detect("show me active CloudWatch alarms")
        assert result == "cloudwatch"

    def test_security_findings_query(self):
        result = self.detect("list critical security findings")
        assert result == "security"

    def test_cost_query(self):
        result = self.detect("what's my AWS spend this month?")
        assert result == "cost"

    def test_rca_query(self):
        result = self.detect("perform root cause analysis on the outage")
        assert result == "rca"

    def test_general_query_defaults(self):
        result = self.detect("hello how are you")
        # Should not match any specialist
        assert result in ("general", "supervisor", "")


class TestMultiAgentDetection:
    """Verify _detect_multi_agents identifies multi-domain queries."""

    def setup_method(self):
        from app.api.routes import _detect_multi_agents
        self.detect = _detect_multi_agents

    def test_single_domain(self):
        result = self.detect("show CloudWatch alarms")
        assert len(result) <= 1

    def test_multi_domain(self):
        result = self.detect("check alarms and security findings and cost")
        assert len(result) >= 2


class TestAlarmDetection:
    """Verify _detect_alarm_in_response identifies alarm mentions."""

    def setup_method(self):
        from app.api.routes import _detect_alarm_in_response
        self.detect = _detect_alarm_in_response

    def test_alarm_present(self):
        response = "The CloudWatch alarm 'HighCPU' is in ALARM state since 2 hours ago."
        assert self.detect(response) is True

    def test_no_alarm(self):
        response = "All systems are operating normally. No issues detected."
        assert self.detect(response) is False
