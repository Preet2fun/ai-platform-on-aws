"""Advisor agent tools — Trusted Advisor recommendations + shared AWS API caller."""
import os
from langchain_core.tools import tool
import boto3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from call_aws_tool import make_call_aws_tool

# Trusted Advisor is a global AWS service — only accessible via us-east-1
_TA_REGION = "us-east-1"


def _default_session(region: str):
    return boto3.Session(region_name=region)


@tool
def get_advisor_recommendations(region: str = _TA_REGION) -> str:
    """Get Trusted Advisor recommendations."""
    try:
        ta = boto3.client("trustedadvisor", region_name=region)
        resp = ta.list_recommendations(maxResults=10)
        recs = resp.get("recommendationSummaries", [])
        lines = [f"Total recommendations: {len(recs)}"]
        for r in recs:
            lines.append(f"[{r.get('pillar','?')}] {r.get('name','?')} — {r.get('status','?')}")
        return "\n".join(lines) if recs else "No recommendations found."
    except Exception as e:
        return f"Trusted Advisor error: {e}"


call_aws = make_call_aws_tool(_default_session)


def get_tools():
    return [get_advisor_recommendations, call_aws]
