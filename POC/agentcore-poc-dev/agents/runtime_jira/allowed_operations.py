"""AWS API operation allowlist — controls what the LLM-driven agents can execute.

Two tiers, enforced before any call reaches AWS:

1. ALLOWED_OPERATIONS — metadata/describe/list reads. Safe: they return resource
   configuration and inventory, not the data held inside those resources.
2. SENSITIVE_DATA_OPERATIONS — data-plane reads that can return object bodies, log
   contents, or IAM policy documents (i.e. can carry secrets/PII). "Read-only" is
   not "safe to expose": a prompt-injected input could use these to exfiltrate data.
   These are blocked by default and only permitted when the agent is explicitly
   opted in via the ALLOW_SENSITIVE_DATA_READS environment variable (see is_operation_allowed).

Writes/deletes are never listed, so they are always blocked.
"""

import os

# Metadata/describe/list operations per AWS service — always permitted.
# These return resource configuration and inventory, not resource contents.
ALLOWED_OPERATIONS = {
    "cloudwatch": [
        "describe_alarms", "describe_alarms_for_metric", "describe_alarm_history",
        "get_metric_data", "get_metric_statistics", "list_metrics", "list_dashboards",
        "get_dashboard", "list_tags_for_resource",
    ],
    "logs": [
        "describe_log_groups", "describe_log_streams", "describe_queries",
    ],
    "ec2": [
        "describe_instances", "describe_security_groups", "describe_vpcs",
        "describe_subnets", "describe_volumes", "describe_network_interfaces",
        "describe_route_tables", "describe_instance_status", "describe_tags",
    ],
    "ecs": [
        "describe_clusters", "describe_services", "describe_tasks",
        "describe_task_definition", "list_clusters", "list_services", "list_tasks",
    ],
    "rds": [
        "describe_db_instances", "describe_db_clusters", "describe_events",
        "list_tags_for_resource",
    ],
    "s3": [
        "list_buckets", "get_bucket_policy", "get_bucket_acl",
        "get_bucket_location", "list_objects_v2",
        "get_bucket_tagging", "get_bucket_versioning",
    ],
    "lambda": [
        "list_functions", "get_function", "get_function_configuration",
        "list_event_source_mappings",
    ],
    "iam": [
        "list_roles", "list_policies", "get_role",
        "list_attached_role_policies", "list_role_policies",
        "get_user", "list_users",
    ],
    "dynamodb": [
        "describe_table", "list_tables", "describe_continuous_backups",
    ],
    "securityhub": [
        "get_findings", "list_findings", "describe_standards",
        "get_enabled_standards", "describe_standards_controls",
        "list_enabled_products_for_import", "describe_hub",
    ],
    "guardduty": [
        "list_detectors", "get_detector", "list_findings", "get_findings",
    ],
    "ce": [
        "get_cost_and_usage", "get_cost_forecast", "get_reservation_utilization",
        "get_savings_plans_utilization", "get_rightsizing_recommendation",
        "get_anomalies", "get_cost_categories",
    ],
    "trustedadvisor": [
        "list_checks", "list_recommendations", "get_recommendation",
        "list_organization_recommendations",
    ],
    "support": [
        "describe_trusted_advisor_checks", "describe_trusted_advisor_check_result",
        "describe_trusted_advisor_check_summaries", "refresh_trusted_advisor_check",
    ],
    "cloudtrail": [
        "lookup_events", "describe_trails", "get_trail_status",
        "get_event_selectors",
    ],
    "sts": [
        "get_caller_identity",
    ],
    "bedrock-agentcore-control": [
        "list_agent_runtimes", "get_agent_runtime",
    ],
}

# Data-plane reads that can return resource CONTENTS (object bodies, log event text,
# IAM policy documents) — these can carry secrets/PII, so they are a data-exfiltration
# surface under prompt injection. Blocked unless ALLOW_SENSITIVE_DATA_READS is truthy.
SENSITIVE_DATA_OPERATIONS = {
    "s3": ["get_object"],
    "logs": ["get_log_events", "filter_log_events", "get_query_results"],
    "iam": ["get_policy", "get_role_policy"],
}

# Env flag that opts an agent into the sensitive data-plane reads above.
# Default off (least-privilege). Set per-agent via `agentcore deploy --env` only where
# reading log/object contents is genuinely required (e.g. an RCA log-analysis agent).
_ALLOW_SENSITIVE_ENV_VAR = "ALLOW_SENSITIVE_DATA_READS"


def _sensitive_reads_enabled() -> bool:
    """True when the agent is explicitly opted into data-plane reads."""
    return os.getenv(_ALLOW_SENSITIVE_ENV_VAR, "false").strip().lower() in ("1", "true", "yes")


def is_operation_allowed(service: str, operation: str) -> bool:
    """Check if a service/operation pair may be executed.

    Metadata operations are always allowed. Sensitive data-plane reads are allowed
    only when ALLOW_SENSITIVE_DATA_READS is enabled for this agent.
    """
    if operation in ALLOWED_OPERATIONS.get(service, []):
        return True
    if operation in SENSITIVE_DATA_OPERATIONS.get(service, []):
        return _sensitive_reads_enabled()
    return False
