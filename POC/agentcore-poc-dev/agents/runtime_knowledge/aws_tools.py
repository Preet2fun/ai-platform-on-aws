"""Knowledge agent tools — AWS documentation search + shared AWS API caller."""
from langchain_core.tools import tool
import boto3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from call_aws_tool import make_call_aws_tool


def _default_session(region: str):
    return boto3.Session(region_name=region)


@tool
def search_aws_docs(query: str) -> str:
    """Search AWS documentation."""
    return f"For AWS documentation on '{query}', visit: https://docs.aws.amazon.com/search?query={query.replace(' ', '+')}"


call_aws = make_call_aws_tool(_default_session)


def get_tools():
    return [search_aws_docs, call_aws]
