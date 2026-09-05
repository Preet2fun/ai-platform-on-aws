"""Security agent tools — Security Hub findings with tenant credential isolation."""
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
def get_security_findings(severity: str = "CRITICAL", region: str = AWS_REGION) -> str:
    """Get Security Hub findings. severity can be CRITICAL, HIGH, MEDIUM, LOW."""
    try:
        session = _get_tenant_session(region)
        sh = session.client("securityhub", region_name=region)
        filters = {"SeverityLabel": [{"Value": severity, "Comparison": "EQUALS"}], "RecordState": [{"Value": "ACTIVE", "Comparison": "EQUALS"}]}
        resp = sh.get_findings(Filters=filters, MaxResults=10)
        findings = resp.get("Findings", [])
        lines = [f"Total {severity} findings: {len(findings)}"]
        for f in findings:
            lines.append(f"[{f.get('Severity',{}).get('Label','?')}] {f.get('Title','?')} | {f.get('Resources',[{}])[0].get('Id','?')[:60]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Security Hub error: {e}"


# Shared call_aws with tenant-scoped session
call_aws = make_call_aws_tool(_get_tenant_session)


def get_tools():
    return [get_security_findings, call_aws]
