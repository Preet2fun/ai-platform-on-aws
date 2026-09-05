"""Cost A2A Runtime — Cost optimization specialist using shared base class."""
import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

from base_runtime import BaseSpecialistRuntime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an MSP Cost Optimization specialist analyzing spending for budget management.

When providing information:
1. Always include dollar amounts and percentage of total
2. Sort by cost (highest first)
3. Identify anomalies: sudden spikes vs gradual growth
4. Flag budget threshold breaches
5. Recommend savings: Reserved Instances, right-sizing, unused resources

CONCISENESS RULES:
- Top 10 services by cost
- Include period (e.g., "June 2026" or "Last 30 days")
- Keep under 500 words
- Never dump raw JSON"""


def _get_tools():
    """Return local boto3 cost tools (get_cost_analysis + call_aws).

    Uses the local Cost Explorer tool rather than the MCP Gateway path, which
    does not reliably support Cost Explorer queries.
    """
    from aws_tools import get_tools
    logger.info("Using local boto3 tools (Cost Explorer via get_cost_analysis)")
    return get_tools()


runtime = BaseSpecialistRuntime(
    agent_name="cost",
    system_prompt=SYSTEM_PROMPT,
    get_tools_fn=_get_tools,
)
app = runtime.app

if __name__ == "__main__":
    runtime.run()
