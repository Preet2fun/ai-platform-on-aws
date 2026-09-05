# tests/test_allowed_operations.py
"""Tests for the AWS API operation allowlist."""

import sys
from pathlib import Path

# Add agents/shared to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agents" / "shared"))

from allowed_operations import is_operation_allowed, ALLOWED_OPERATIONS


class TestAllowlist:
    """Verify the allowlist blocks destructive operations and permits reads."""

    def test_allowed_read_operations(self):
        """Read operations should be permitted."""
        assert is_operation_allowed("cloudwatch", "describe_alarms") is True
        assert is_operation_allowed("ec2", "describe_instances") is True
        assert is_operation_allowed("s3", "list_buckets") is True
        assert is_operation_allowed("securityhub", "get_findings") is True
        assert is_operation_allowed("ce", "get_cost_and_usage") is True

    def test_blocked_write_operations(self):
        """Write/delete/modify operations should be blocked."""
        assert is_operation_allowed("ec2", "terminate_instances") is False
        assert is_operation_allowed("s3", "delete_bucket") is False
        assert is_operation_allowed("s3", "delete_object") is False
        assert is_operation_allowed("iam", "create_role") is False
        assert is_operation_allowed("iam", "delete_role") is False
        assert is_operation_allowed("iam", "put_role_policy") is False
        assert is_operation_allowed("ec2", "run_instances") is False
        assert is_operation_allowed("lambda", "delete_function") is False

    def test_unknown_service_blocked(self):
        """Operations on unknown services should be blocked."""
        assert is_operation_allowed("unknown_service", "do_something") is False
        assert is_operation_allowed("", "describe_alarms") is False

    def test_empty_operation_blocked(self):
        """Empty operation string should be blocked."""
        assert is_operation_allowed("cloudwatch", "") is False

    def test_all_services_have_entries(self):
        """Verify key services are covered in the allowlist."""
        expected_services = [
            "cloudwatch", "ec2", "s3", "iam", "securityhub",
            "ce", "ecs", "rds", "lambda", "dynamodb",
        ]
        for svc in expected_services:
            assert svc in ALLOWED_OPERATIONS, f"Service '{svc}' missing from allowlist"
            assert len(ALLOWED_OPERATIONS[svc]) > 0, f"Service '{svc}' has empty allowlist"

    def test_dangerous_patterns_not_in_allowlist(self):
        """No delete/terminate/put/create operations should be in any allowlist."""
        dangerous_prefixes = ["delete_", "terminate_", "put_", "create_", "remove_", "update_"]
        for service, ops in ALLOWED_OPERATIONS.items():
            for op in ops:
                for prefix in dangerous_prefixes:
                    assert not op.startswith(prefix), \
                        f"Dangerous operation '{op}' found in {service} allowlist"
