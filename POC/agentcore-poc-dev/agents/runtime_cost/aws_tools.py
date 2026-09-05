"""Cost agent tools — Cost Explorer analysis + shared AWS API caller."""
import os
from langchain_core.tools import tool
import boto3, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from call_aws_tool import make_call_aws_tool

# Cost Explorer is a global AWS service — only accessible via us-east-1
_CE_REGION = "us-east-1"
AWS_REGION = os.environ["AWS_REGION"]


def _default_session(region: str):
    return boto3.Session(region_name=region)


@tool
def get_cost_analysis(days: int = 30, group_by: str = "SERVICE") -> str:
    """Get AWS cost breakdown. group_by can be SERVICE, REGION, or USAGE_TYPE."""
    try:
        ce = boto3.client("ce", region_name=_CE_REGION)
        end = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        resp = ce.get_cost_and_usage(TimePeriod={"Start": start, "End": end}, Granularity="MONTHLY", Metrics=["BlendedCost"], GroupBy=[{"Type": "DIMENSION", "Key": group_by}])
        lines = []
        for period in resp.get("ResultsByTime", []):
            for group in period.get("Groups", []):
                cost = float(group["Metrics"]["BlendedCost"]["Amount"])
                if cost > 0.001:
                    lines.append(f"${cost:.2f} — {group['Keys'][0]}")
        return "\n".join(sorted(lines, reverse=True)) if lines else "No costs recorded in this period."
    except Exception as e:
        return f"Cost Explorer error: {e}"


# Cost Explorer is a global service accessed via us-east-1
call_aws = make_call_aws_tool(_default_session, default_region=_CE_REGION)


def get_tools():
    return [get_cost_analysis, call_aws]
