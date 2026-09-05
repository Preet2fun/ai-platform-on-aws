"""RCA Investigator A2A Runtime — Schema-agnostic database investigation agent."""
import os
import sys
import logging
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from sanitize import sanitize_user_input
from base_runtime import _safe_error_response

from fastapi import FastAPI, Request
import uvicorn
from langchain_aws import ChatBedrockConverse
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="RCA Investigator A2A Runtime")

MODEL_ID = os.getenv("MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
AWS_REGION = os.environ["AWS_REGION"]

# Load system prompt
_PROMPT_PATH = Path(__file__).parent / "rca_investigator_prompt.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.exists() else "You are an RCA investigator."

_graph_cache = {}  # Cache per tenant: {tenant_id: graph}


def _get_db_url(tenant_id: str = "") -> str:
    """Get database URL from environment. Fails fast if not configured."""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        logger.error("DATABASE_URL environment variable not set — cannot connect to RCA database")
        return ""
    if "sslmode" not in db_url:
        db_url += "?sslmode=prefer"
    return db_url


def _build_graph(db_url: str):
    """Build agent graph for a specific database URL."""
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    from botocore.config import Config as BotoConfig

    llm = ChatBedrockConverse(
        model_id=MODEL_ID,
        region_name=AWS_REGION,
        max_tokens=4096,
        temperature=0,
        config=BotoConfig(
            retries={"max_attempts": 10, "mode": "adaptive"},
            read_timeout=120,
        ),
    )

    db = SQLDatabase.from_uri(
        db_url,
        include_tables=["otel_metrics", "otel_logs", "otel_spans"],
        sample_rows_in_table_info=2,
        engine_args={"connect_args": {"options": "-c default_transaction_read_only=on"}},
    )
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools()

    graph = create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)
    logger.info(f"RCA Investigator agent created: model={MODEL_ID}, tools={[t.name for t in tools]}")
    return graph


def _get_graph(tenant_id: str = ""):
    """Get or build graph for a tenant."""
    cache_key = tenant_id or "_default"
    if cache_key in _graph_cache:
        return _graph_cache[cache_key]

    db_url = _get_db_url(tenant_id)
    if not db_url:
        return None

    try:
        graph = _build_graph(db_url)
        _graph_cache[cache_key] = graph
        return graph
    except Exception as e:
        logger.error(f"Failed to build graph: {e}")
        return None


@app.post("/invocations")
async def invoke(request: Request):
    """Handle invocation from Supervisor."""
    payload = await request.json()
    prompt = sanitize_user_input(payload.get("prompt", payload.get("input", "")))
    tenant_id = payload.get("tenant_id", "") or payload.get("account_name", "")
    if tenant_id == "default":
        tenant_id = ""
    hint = payload.get("hint", "")

    # Sanitize tenant_id — only allow alphanumeric, hyphens, underscores (max 64 chars)
    if tenant_id:
        tenant_id = re.sub(r'[^a-z0-9_\-]', '', tenant_id.lower())[:64]

    # Extract tenant from prompt if not explicitly passed
    if not tenant_id and "tenant" in prompt.lower():
        match = re.search(r'tenant\s+(\w+)', prompt.lower())
        if match:
            tenant_id = match.group(1)[:64]

    # Build investigation message
    # KNOWN LIMITATION (tenant isolation): the tenant filter below is enforced only by
    # instructing the model — the SQL toolkit still has schema-wide read access, so a
    # non-compliant or manipulated query could read across tenants. tenant_id is
    # regex-sanitised above to prevent SQL injection, but that does not guarantee the
    # filter is applied. Proper isolation requires a DB-level control (per-tenant role
    # or PostgreSQL row-level security on the shared otel_* tables). Tracked as a
    # known limitation; see README "Security". Do NOT rely on this for hard multi-tenant
    # data separation without the DB-level guard.
    parts = ["Investigate the data in this database and produce an RCA investigation report."]
    if tenant_id:
        parts.append(f"Filter all queries by tenant_id = '{tenant_id}'.")
    if hint:
        parts.append(f"Starting context: {hint}")
    if prompt:
        parts.append(prompt)
    parts.append("Begin by listing available tables and understanding the schema.")

    full_prompt = " ".join(parts)
    logger.info(f"Investigator invoked: tenant={tenant_id}, prompt={prompt[:60]}...")

    graph = _get_graph(tenant_id)
    if graph is None:
        return {
            "result": "RCA database is not available. Ensure the DATABASE_URL environment variable is set to the telemetry Postgres connection string.",
            "agent_type": "investigator"
        }

    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=full_prompt)]},
            config={"recursion_limit": 30},
        )
        output = result["messages"][-1].content
        return {"result": output, "agent_type": "investigator"}
    except Exception as e:
        logger.error(f"Investigation error: {e}", exc_info=True)
        return {"result": f"Investigation error: {_safe_error_response(e)}", "agent_type": "investigator"}


@app.get("/ping")
def ping():
    return {"status": "healthy", "agent": "investigator", "cached_tenants": list(_graph_cache.keys())}


if __name__ == "__main__":
    logger.info("Starting RCA Investigator Runtime on port 8080...")
    uvicorn.run(app, host="0.0.0.0", port=8080)
# Adding a comment to force rebuild
