"""CloudWatch agent tools — alarm/metric queries with tenant credential isolation."""
import os
from langchain_core.tools import tool
import boto3, json, logging, sys, contextvars
from pathlib import Path

AWS_REGION = os.environ["AWS_REGION"]  # Always set by AgentCore runtime

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from call_aws_tool import make_call_aws_tool

logger = logging.getLogger(__name__)

# Per-request account context (set by the runtime on each invocation)
_current_account_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("current_account", default="default")


def _get_tenant_session(region: str = AWS_REGION):
    """Get boto3 session for the current tenant. Uses STS credentials from Secrets Manager."""
    if _current_account_ctx.get() in ("default", "", None):
        return boto3.Session(region_name=region)

    try:
        sm = boto3.client("secretsmanager", region_name=region)
        secret = json.loads(sm.get_secret_value(SecretId=f"msp-credentials/{_current_account_ctx.get()}")["SecretString"])

        if secret.get("aws_access_key_id") and secret.get("expires_at"):
            from datetime import datetime, timezone
            expires_str = secret["expires_at"].replace("Z", "+00:00")
            expires = datetime.fromisoformat(expires_str)
            if expires > datetime.now(timezone.utc):
                logger.info(f"Using tenant credentials for {_current_account_ctx.get()}")
                return boto3.Session(
                    aws_access_key_id=secret["aws_access_key_id"],
                    aws_secret_access_key=secret["aws_secret_access_key"],
                    aws_session_token=secret["aws_session_token"],
                    region_name=region,
                )
        logger.warning(f"Tenant credentials expired for {_current_account_ctx.get()}, using default")
    except Exception as e:
        logger.warning(f"Failed to get tenant credentials for {_current_account_ctx.get()}: {e}")

    return boto3.Session(region_name=region)


@tool
def get_cloudwatch_data(query: str = "alarms", region: str = AWS_REGION) -> str:
    """Get CloudWatch alarms, metrics, or log groups. Pass query='alarms', 'logs', or 'metrics'."""
    try:
        session = _get_tenant_session(region)
        cw = session.client("cloudwatch", region_name=region)
        if "log" in query.lower():
            logs_client = session.client("logs", region_name=region)
            resp = logs_client.describe_log_groups(limit=20)
            groups = [g["logGroupName"] for g in resp.get("logGroups", [])]
            return f"Log groups ({len(groups)}): " + ", ".join(groups[:20])
        else:
            resp = cw.describe_alarms(MaxRecords=20)
            alarms = resp.get("MetricAlarms", [])
            lines = [f"Total alarms: {len(alarms)}"]
            for a in alarms:
                lines.append(f"[{a['StateValue']}] {a['AlarmName']} — {a['MetricName']} {a['ComparisonOperator']} {a['Threshold']}")
            return "\n".join(lines)
    except Exception as e:
        return f"CloudWatch error: {e}"


# Shared call_aws with tenant-scoped session
call_aws = make_call_aws_tool(_get_tenant_session)


def get_tools():
    return [get_cloudwatch_data, call_aws]
