# app/api/routes.py
"""
API routes for MSP Assistant.

Handles chat, workflow, and user endpoints with an async fire-and-poll pattern
for long-running operations:
  1. POST /chat  — enqueues work in a background asyncio Task, returns request_id.
  2. GET  /chat/{id}     — client polls DynamoDB for the finished result.
  3. GET  /chat/{id}/stream — SSE stream that forwards progress events from DynamoDB
                              as the background Task writes them (see chat_state.py).

Workflow endpoints (/workflows/*) follow the same async pattern:
  step approval → background Task → DynamoDB → poll or SSE.

Auth endpoints (/auth/*) store Cognito refresh tokens in httpOnly cookies so
the frontend never has to touch localStorage for long-lived credentials.

Architecture note:
  All agent work runs in AgentCore Runtime (serverless).  This file is the
  HTTP surface only — no agent logic lives here.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Dict, Optional
from pydantic import BaseModel, Field, validator
from app.core.auth import get_current_user
from app.services.account_service import get_account_service
from app.core.secrets_credential_manager import get_current_msp_principal_arn, get_current_msp_account_id
from app.services.health_service import get_health_service
from app.services.workflow_service import get_workflow_service
from app.core.config import settings
from app.core.task_registry import track_task
import asyncio
import threading
import uuid
import re
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)

router = APIRouter()


def _safe_error_message(exc: Exception) -> str:
    """Return a generic error message safe to surface to users.
    Full exception details are already logged at the call site before fail_request.
    """
    from botocore.exceptions import ClientError
    if isinstance(exc, ClientError):
        return f"AWS service error ({exc.response['Error']['Code']}). Check server logs for details."
    return "An unexpected error occurred. Please try again."

# AgentCore Memory client — shared across requests, lazy-initialized
_memory_client = None
_memory_client_lock = threading.Lock()

def _user_session_id(user_id: str) -> str:
    """Daily-rotating AgentCore Memory session ID — STM resets each day, LTM provides cross-day recall."""
    from datetime import date
    return f"msp-{user_id}-{date.today().isoformat()}"


def _get_memory_client() -> object:
    """Lazy-init boto3 bedrock-agentcore client for memory operations."""
    global _memory_client
    if _memory_client is not None:
        return _memory_client
    memory_id = settings.MEMORY_ID
    if not memory_id:
        return None
    with _memory_client_lock:
        if _memory_client is not None:
            return _memory_client
        try:
            import boto3 as _b3
            _memory_client = _b3.client("bedrock-agentcore", region_name=settings.AWS_REGION)
            logger.info("AgentCore Memory boto3 client initialized")
        except Exception as e:
            logger.warning(f"AgentCore Memory client init failed: {e}")
    return _memory_client


def _memory_save_turn(user_msg: str, assistant_msg: str, user_id: str, session_id: str) -> None:
    """Save a conversation turn to AgentCore Memory."""
    from datetime import datetime, timezone
    mem = _get_memory_client()
    if not mem or not settings.MEMORY_ID:
        return
    try:
        mem.create_event(
            memoryId=settings.MEMORY_ID,
            actorId=user_id,
            sessionId=session_id,
            eventTimestamp=datetime.now(timezone.utc),
            payload=[
                {"conversational": {"content": {"text": user_msg}, "role": "USER"}},
                {"conversational": {"content": {"text": assistant_msg[:4000]}, "role": "ASSISTANT"}},
            ]
        )
    except Exception as e:
        logger.warning(f"Memory save failed: {e}")


def _memory_load_turns(user_id: str, session_id: str, k: int = 3) -> str:
    """Load last k conversation events from AgentCore Memory. Returns formatted context string."""
    mem = _get_memory_client()
    if not mem or not settings.MEMORY_ID:
        return ""
    try:
        resp = mem.list_events(
            memoryId=settings.MEMORY_ID,
            actorId=user_id,
            sessionId=session_id,
            includePayloads=True,
        )
        events = resp.get("events", [])[-k:]
        if not events:
            return ""
        lines = []
        for ev in events:
            for msg in ev.get("payload", []):
                conv = msg.get("conversational", {})
                role = conv.get("role", "")
                text = conv.get("content", {}).get("text", "")
                if text:
                    lines.append(f"{role}: {text[:500]}")
        return "Previous conversation:\n" + "\n".join(lines) + "\n\n" if lines else ""
    except Exception as e:
        logger.warning(f"Memory load failed: {e}")
        return ""



# Shared regex for sanitizing account names — single source of truth for validator and helper
_ACCOUNT_NAME_UNSAFE_CHARS = r'[^a-z0-9_]'

# UUID format: 8-4-4-4-12 hex digits
_CONVERSATION_ID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


# Request/Response Models
class ChatRequest(BaseModel):
    message: str = Field(..., max_length=10000)
    account_name: Optional[str] = "default"
    workflow_enabled: bool = False
    full_automation: bool = False
    conversation_id: Optional[str] = None

    @validator('account_name')
    @classmethod
    def sanitize_account_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Strip chars that could break the metadata JSON prefix injected into A2A prompts
        sanitized = re.sub(_ACCOUNT_NAME_UNSAFE_CHARS, '', v)
        if sanitized != v:
            logger.warning(f"account_name sanitized: {v!r} -> {sanitized!r}")
        return sanitized

    @validator('conversation_id')
    @classmethod
    def validate_conversation_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if not _CONVERSATION_ID_PATTERN.match(v):
            raise ValueError("conversation_id must be a valid UUID")
        return v


def _sanitize_account_name(name: str) -> str:
    """Sanitize path-param account names (same rule as ChatRequest validator)."""
    return re.sub(_ACCOUNT_NAME_UNSAFE_CHARS, '', name)


class AccountCreateRequest(BaseModel):
    account_name: str
    account_id: str
    description: Optional[str] = None


class AccountResponse(BaseModel):
    id: str
    name: str
    account_id: str
    status: str
    role_name: str
    external_id: str
    created_at: Optional[str]
    needs_refresh: bool


# Helper Functions
# Keyword sets per domain — single source of truth for both routing functions
_AGENT_KEYWORDS = {
    'rca':        ['root cause', 'rca', 'investigate', 'anomaly', 'incident', 'telemetry', 'breach', 'spike'],
    'cost':       ['cost', 'spend', 'bill', 'budget', 'pricing', 'expense', 'saving'],
    'cloudwatch': ['alarm', 'cloudwatch', 'metric', 'log', 'monitor', 'cw', 'performance', 'cpu', 'memory', 'utilization'],
    'security':   ['security', 'finding', 'compliance', 'vulnerability', 'securityhub', 'risk'],
    'advisor':    ['advisor', 'best practice', 'recommendation', 'trusted', 'optimize', 'optimization', 'health check', 'health'],
    'jira':       ['jira', 'ticket', 'issue', 'incident'],
    'knowledge':  ['knowledge', 'troubleshoot', 'how to', 'guide', 'kb', 'fix', 'resolve'],
}
_COMPREHENSIVE_KEYWORDS = ['health check', 'complete', 'full', 'overview', 'summary', 'all', 'everything', 'environment', 'status']


def _detect_agent_stage(message: str) -> str:
    """Return the single best-match agent domain, or 'supervisor' for ambiguous queries."""
    return _detect_multi_agents(message)[0]


def _detect_multi_agents(message: str) -> list:
    """Return ordered list of agent domains needed to answer this query."""
    msg = message.lower()
    matches = {agent: any(w in msg for w in words) for agent, words in _AGENT_KEYWORDS.items()}
    is_comprehensive = any(w in msg for w in _COMPREHENSIVE_KEYWORDS)

    agents = []
    if is_comprehensive:
        if matches['cost'] or 'spending' in msg:
            agents.append('cost')
        agents.extend(['cloudwatch', 'security', 'advisor'])
    else:
        for agent in _AGENT_KEYWORDS:
            if matches[agent]:
                agents.append(agent)

    # Deduplicate while preserving order
    seen: set = set()
    unique = []
    for a in agents:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    return unique if unique else ['supervisor']


def _detect_alarm_in_response(response_text: str) -> bool:
    """
    Regex-based heuristic that decides whether an agent response contains active alarms.

    First checks an explicit no-alarm phrase list to avoid false positives (e.g. a
    response that says "found 0 active alarms" would otherwise match the count regex).
    Then tries count-based patterns ("3 active alarms"), and finally scans for alarm
    state indicators such as emoji markers or status strings.

    Args:
        response_text: Raw text returned by a CloudWatch or other agent.

    Returns:
        True if the response appears to describe at least one active alarm.
    """
    text = response_text.lower()
    no_alarm_phrases = [
        "no active alarms", "0 active alarms", "no alarms",
        "found 0 active alarms", "not see any", "don't see any",
        "active alarms: 0", "zero alarms", "no active alarm"
    ]
    if any(phrase in text for phrase in no_alarm_phrases):
        return False
    # Regex patterns that extract the count of alarms from common agent phrasing.
    # If every matched count is 0 we return False; any count > 0 returns True.
    count_patterns = [
        r'(\d+)\s+active\s+alarms?',
        r'found\s+(\d+)\s+alarms?',
        r'(\d+)\s+alarms?\s+detected',
        r'(\d+)\s+alarms?\s+found',
    ]
    for pattern in count_patterns:
        count_matches = re.findall(pattern, text)
        if count_matches:
            for count in count_matches:
                if int(count) > 0:
                    return True
            return False
    alarm_indicators = [
        "alarm state", "status: alarm", "state: alarm",
        "🚨", "⚠️", "in alarm state",
        "currently have 1", "currently have 2",
        "[critical]", "active alarm", "critical alarm",
    ]
    return any(indicator in text for indicator in alarm_indicators)


async def _detect_remediation_intent_llm(response_text: str) -> bool:
    """
    Use Supervisor Runtime to classify whether a response contains
    actionable issues requiring remediation (alarms, security findings, cost anomalies).

    Falls back to regex on any failure.
    """
    try:
        SUPERVISOR_RUNTIME_ARN = settings.SUPERVISOR_RUNTIME_ARN
        AWS_REGION = settings.AWS_REGION
        if not SUPERVISOR_RUNTIME_ARN:
            return _detect_alarm_in_response(response_text)

        from app.core.langgraph_client import get_langgraph_client as get_agentcore_client
        agentcore = get_agentcore_client(region=AWS_REGION)

        classification_prompt = f"""Classify this AWS agent response. Does it contain an actionable issue that needs remediation?

Response text (first 1500 chars):
{response_text[:1500]}

Actionable issues include:
- CloudWatch alarms in ALARM state
- Security Hub findings with CRITICAL or HIGH severity
- Cost anomalies or budget threshold breaches
- Trusted Advisor warnings requiring action

Reply with ONLY one word: YES or NO"""

        result = await agentcore.invoke_runtime(
            runtime_arn=SUPERVISOR_RUNTIME_ARN,
            payload={
                "prompt": classification_prompt,
                "session_id": f"intent-classify-{uuid.uuid4().hex[:8]}"
            }
        )
        answer = result.get("response", "").strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        logger.warning(f"LLM intent classification failed, falling back to regex: {e}")
        return _detect_alarm_in_response(response_text)


async def _should_trigger_remediation(response_text: str) -> bool:
    """
    Router: checks REMEDIATION_DETECTION_MODE config and delegates
    to LLM or regex detection accordingly.
    """
    if settings.REMEDIATION_DETECTION_MODE == "llm":
        return await _detect_remediation_intent_llm(response_text)
    return _detect_alarm_in_response(response_text)


def _build_routing_reason(message: str, agent_hint: str) -> str:
    """Build a human-readable explanation of why this agent was chosen."""
    msg = message.lower()
    keyword_map = {
        'cost':       ['cost', 'spend', 'bill', 'budget', 'pricing', 'expense', 'saving'],
        'cloudwatch': ['alarm', 'cloudwatch', 'metric', 'log', 'monitor', 'performance', 'cpu', 'memory'],
        'security':   ['security', 'finding', 'compliance', 'vulnerability', 'securityhub'],
        'advisor':    ['advisor', 'best practice', 'recommendation', 'trusted', 'optimize'],
        'jira':       ['jira', 'ticket', 'issue', 'incident'],
        'knowledge':  ['troubleshoot', 'how to', 'guide', 'kb', 'fix', 'resolve'],
    }
    if agent_hint in keyword_map:
        matched = [k for k in keyword_map[agent_hint] if k in msg]
        if matched:
            return f"Keywords detected: {', '.join(matched[:4])}"
    return f"{agent_hint} domain query"


async def _process_chat_async(request_id: str, request: ChatRequest, current_user: Dict) -> None:
    """
    Background Task that drives a single chat request end-to-end.

    This function is always invoked via asyncio.create_task() so POST /chat can
    return immediately.  All progress is written to DynamoDB via chat_state helpers
    and forwarded to connected SSE clients by get_progress_stream().

    High-level flow:
      1. Staggered asyncio Tasks emit routing/agent_switch/tool_call SSE events to
         DynamoDB so the frontend ThinkingDropdown has live progress before the
         AgentCore response arrives.
      2. Try direct routing: if the query maps to a single specialist domain, invoke
         that specialist's Runtime ARN directly (saves 45-90 s vs Supervisor roundtrip).
      3. Fallback to Supervisor Runtime streaming.  SSE events from the stream are
         forwarded atomically to DynamoDB (append_streaming_event + set_streaming_content).
      4. After the response arrives, check whether it describes active alarms/issues
         (via _should_trigger_remediation) and optionally start a workflow.
      5. Call complete_request() or fail_request() to unblock polling clients.

    Args:
        request_id: UUID that identifies this request in DynamoDB.
        request: Validated ChatRequest body.
        current_user: Decoded JWT claims dict from get_current_user().
    """
    from app.core.langgraph_client import get_langgraph_client as get_agentcore_client
    from app.core.workspace_context import get_workspace_context
    from app.services.chat_state import (
        update_progress, complete_request, fail_request,
        append_streaming_event, set_streaming_content
    )

    agent_hint = _detect_agent_stage(request.message)
    agent_messages = {

        'cost':        'Querying Cost Explorer agent',
        'cloudwatch':  'Querying CloudWatch monitoring agent',
        'security':    'Scanning with Security Hub agent',
        'jira':        'Managing tickets with Jira agent',
        'advisor':     'Checking Trusted Advisor recommendations',
        'knowledge':   'Searching knowledge base',
        'rca':         'Initiating Root Cause Analysis investigation',
        'supervisor':  'Processing with Supervisor agent',
    }
    tool_name_map = {
        'cost': 'analyze_costs', 'cloudwatch': 'check_cloudwatch',
        'security': 'check_security', 'advisor': 'check_advisor',
        'jira': 'manage_jira', 'knowledge': 'search_knowledge',
        'supervisor': 'supervisor',
    }

    try:
        SUPERVISOR_RUNTIME_ARN = settings.SUPERVISOR_RUNTIME_ARN
        AWS_REGION = settings.AWS_REGION

        if not SUPERVISOR_RUNTIME_ARN:
            raise Exception("SUPERVISOR_RUNTIME_ARN not configured")

        user_id = current_user.get("user_id", current_user.get("sub"))
        # Per-conversation session ID ties STM (short-term memory) to this browser tab's
        # conversation.  If the frontend sends a conversation_id the session is stable;
        # without it we fall back to a daily-rotating session so at least same-day
        # turns are grouped.  LTM always persists via actor_id regardless.
        if not request.conversation_id:
            logger.warning(f"No conversation_id in chat request from user {user_id} — falling back to daily session")
        session_id = f"msp-{user_id}-{request.conversation_id}" if request.conversation_id else _user_session_id(user_id)

        workspace = get_workspace_context()
        if request.account_name and request.account_name != "default":
            success = workspace.set_current_account(request.account_name)
            # Auto-refresh credentials if expired
            if not success:
                logger.info(f"Auto-refreshing expired credentials for {request.account_name}")
                try:
                    account_service = get_account_service()
                    await account_service.refresh_account(request.account_name)
                    workspace.set_current_account(request.account_name)
                except Exception as refresh_err:
                    logger.warning(f"Auto-refresh failed for {request.account_name}: {refresh_err}")
        else:
            workspace.clear_context()

        account_name = request.account_name or "default"

        # Build rich routing reasoning for ThinkingDropdown
        query_snippet = request.message[:80] + ('...' if len(request.message) > 80 else '')
        routing_reason = _build_routing_reason(request.message, agent_hint)
        expected_agents = _detect_multi_agents(request.message)
        specialist_tool = tool_name_map.get(agent_hint, agent_hint)

        # Steps 1-4 below fire staggered SSE progress events to DynamoDB so that the
        # frontend ThinkingDropdown shows live activity instead of a blank spinner
        # while the AgentCore Runtime call is in flight.  The tasks are cancelled
        # immediately if a response arrives before the timer fires (avoids duplicate
        # events on fast responses).
        # NOTE: RCA path emits its own 8-step progress events, so skip generic ones.

        _progress_tasks = []
        if agent_hint != 'rca':
            # Emit step 1: Supervisor analyzing (immediate)
            append_streaming_event(request_id, {
                "event": "progress",
                "data": {"stage": "routing", "message": f"Supervisor analyzing: \"{query_snippet}\""}
            })

            # Emit step 2: Routing decision with reason (after 1s)
            async def _emit_routing() -> None:
                await asyncio.sleep(1)
                update_progress(request_id, "routing", "Routing to specialist agent")
                append_streaming_event(request_id, {
                    "event": "agent_switch",
                    "data": {
                        "from_agent": "supervisor",
                        "to_agent": agent_hint,
                        "message": f"Routing to {agent_hint} specialist",
                        "routing_reason": routing_reason,
                        "agent_index": 1,
                        "agent_count": len(expected_agents) if len(expected_agents) > 1 else 1,
                    }
                })
                append_streaming_event(request_id, {
                    "event": "tool_call",
                    "data": {
                        "tool_name": specialist_tool,
                        "agent": agent_hint,
                        "routing_reason": query_snippet,
                    }
                })

            # Emit step 3: Execution progress (after 3s)
            async def _emit_delegating() -> None:
                await asyncio.sleep(3)
                exec_msg = agent_messages.get(agent_hint, f"{agent_hint} agent processing")
                update_progress(request_id, "delegating", exec_msg)
                append_streaming_event(request_id, {
                    "event": "progress",
                    "data": {"stage": "delegating", "message": exec_msg}
                })

            # Emit step 4: Waiting (after 15s)
            async def _emit_waiting() -> None:
                await asyncio.sleep(15)
                update_progress(request_id, "waiting", "Agent is analyzing data and generating response")
                append_streaming_event(request_id, {
                    "event": "progress",
                    "data": {"stage": "waiting", "message": "Agent is analyzing data and generating response"}
                })

            _progress_tasks = [
                asyncio.create_task(_emit_routing()),
                asyncio.create_task(_emit_delegating()),
                asyncio.create_task(_emit_waiting()),
            ]

        # For multi-domain queries, emit a separate agent_switch event per specialist
        # so the ThinkingDropdown shows each agent being invoked in sequence.
        # Delays are staggered (5 s, 17 s, 29 s, …) to roughly match real agent latency.
        if agent_hint != 'rca' and len(expected_agents) > 1:
            for idx, agent_key in enumerate(expected_agents):
                delay = 5 + idx * 12
                agent_msg = agent_messages.get(agent_key, f"Querying {agent_key} agent")
                labeled_msg = agent_msg.replace("...", f"... ({idx + 1}/{len(expected_agents)})")

                async def _fire_multi_agent(msg=labeled_msg, d=delay, ak=agent_key, i=idx) -> None:
                    await asyncio.sleep(d)
                    update_progress(request_id, "delegating", msg)
                    if i > 0:
                        prev_agent = expected_agents[i - 1]
                        append_streaming_event(request_id, {
                            "event": "agent_switch",
                            "data": {
                                "from_agent": prev_agent,
                                "to_agent": ak,
                                "message": f"Querying {ak} specialist ({i + 1}/{len(expected_agents)})",
                                "routing_reason": f"Multi-domain query requires {ak} data",
                                "agent_index": i + 1,
                                "agent_count": len(expected_agents),
                            }
                        })

                _progress_tasks.append(asyncio.create_task(_fire_multi_agent()))

        async def _complete_with_workflow(resp: str, atype: str) -> None:
            """Shared finalization for both direct-routing and Supervisor paths."""
            wf_triggered = False
            wf_id = None
            alarm_detected = await _should_trigger_remediation(resp)
            logger.info(f"Workflow check [{request_id}]: enabled={request.workflow_enabled}, agent={atype!r}, alarm_detected={alarm_detected}")
            # In LLM mode, allow security/cost/advisor responses to trigger workflow too
            agent_qualifies = (
                "cloudwatch" in atype.lower()
                or (settings.REMEDIATION_DETECTION_MODE == "llm" and atype.lower() in ("security", "cost", "advisor", "supervisor"))
            )
            if request.workflow_enabled and agent_qualifies and alarm_detected:
                try:
                    workflow_service = get_workflow_service()
                    wr = await workflow_service.start_workflow(
                        request.message,
                        request.account_name,
                        full_automation=request.full_automation,
                        has_alarm=True,
                        cloudwatch_response=resp,
                        user_id=user_id,
                        session_id=session_id
                    )
                    logger.info(f"Workflow start result [{request_id}]: {wr}")
                    if wr.get("success") and wr.get("requires_approval"):
                        wf_id = wr["workflow_id"]
                        wf_triggered = True
                        if request.full_automation:
                            resp += "\n\n---\n\n**Full Automation Mode Active**\n\nRemediation steps will be executed automatically."
                except Exception as e:
                    logger.warning(f"Workflow start failed [{request_id}]: {e}")
            complete_request(request_id, {
                "success": True,
                "content": resp,
                "agent_type": atype,
                "workflow_triggered": wf_triggered,
                "workflow_id": wf_id,
            })

        # --- Load conversation history from AgentCore Memory (direct routing path) ---
        memory_context_prefix = _memory_load_turns(user_id, session_id, k=3)


        # --- LTM (Long-Term Memory) semantic retrieval via retrieve_memory_records ---
        ltm_context = ""
        _LTM_STRATEGY_ID = "SemanticFacts-NkLbAg2CKs"
        if settings.MEMORY_ID:
            try:
                mem = _get_memory_client()
                if mem:
                    namespace = f"/strategy/{_LTM_STRATEGY_ID}/actor/{user_id}/"
                    records_resp = mem.retrieve_memory_records(
                        memoryId=settings.MEMORY_ID,
                        namespace=namespace,
                        searchCriteria={"searchQuery": request.message, "memoryStrategyId": _LTM_STRATEGY_ID, "topK": 5}
                    )
                    summaries = records_resp.get("memoryRecordSummaries", [])
                    if summaries:
                        facts = [s.get("content", {}).get("text", "") for s in summaries]
                        facts = [f for f in facts if f]
                        if facts:
                            ltm_context = "Relevant context from previous conversations:\n" + "\n".join(f"- {f}" for f in facts[:5]) + "\n\n"
                            logger.info(f"LTM retrieval: {len(facts)} facts for {request_id}")
            except Exception as ltm_err:
                logger.warning(f"LTM retrieval failed (non-fatal): {ltm_err}")

        # Cancel staggered SSE progress tasks — the Supervisor streaming path emits its
        # own agent_switch/tool_call events, so the pre-emptive timers would duplicate them.
        for t in _progress_tasks:
            t.cancel()

        # --- Direct investigator call for RCA queries (bypasses supervisor timeout issues) ---
        if agent_hint == 'rca' or 'investigate' in request.message.lower() or 'root cause' in request.message.lower() or 'rca' in request.message.lower():
            try:
                import json as _json
                update_progress(request_id, "delegating", "RCA Investigator analyzing telemetry data...")
                append_streaming_event(request_id, {"event": "tool_call", "data": {"tool_name": "investigate_scenario", "agent": "investigator", "status": "running"}})

                from botocore.config import Config as _BotoConfig
                _inv_client = boto3.client("bedrock-agentcore", region_name=AWS_REGION,
                    config=_BotoConfig(read_timeout=300, connect_timeout=30, retries={'max_attempts': 0}))
                _inv_resp = _inv_client.invoke_agent_runtime(
                    agentRuntimeArn=settings.INVESTIGATOR_A2A_ARN,
                    runtimeSessionId=f"rca-{uuid.uuid4().hex}",
                    payload=_json.dumps({"prompt": request.message, "account_name": account_name}).encode()
                )
                _inv_result = _json.loads(_inv_resp["response"].read())
                response = _inv_result.get("result", str(_inv_result))
                agent_type = "investigator"

                if response:
                    _memory_save_turn(request.message, response, user_id, session_id)
                await _complete_with_workflow(response, agent_type)
                return
            except Exception as inv_err:
                logger.warning(f"Direct investigator call failed: {inv_err}, falling back to supervisor")

        # Invoke Supervisor via streaming; fall back to non-streaming on error
        update_progress(request_id, "delegating", agent_messages.get(agent_hint, "Processing with Supervisor agent"))
        agentcore = get_agentcore_client(region=AWS_REGION)

        payload = {
            "prompt": request.message,
            "account_name": account_name,
            "workflow_enabled": request.workflow_enabled,
            "full_automation": request.full_automation,
            "session_id": session_id,
            "user_context": {
                "user_id": user_id,
                "email": current_user.get("email"),
                "account_name": account_name
            },
        }

        response = ""
        agent_type = "supervisor"
        streaming_succeeded = False
        content_chunk_count = 0

        try:
            # Stream SSE events from the Supervisor Runtime and forward each one to
            # DynamoDB so the polling SSE endpoint (get_progress_stream) can relay
            # them to the browser in near real-time.
            async for evt in agentcore.invoke_runtime_stream(
                runtime_arn=SUPERVISOR_RUNTIME_ARN,
                payload=payload,
                session_id=session_id,
            ):
                event_name = evt.get("event", "")
                event_data = evt.get("data", {})

                if event_name == "error":
                    logger.warning(f"Streaming error for {request_id}: {event_data.get('message')}")
                    break

                if event_name in ("agent_switch", "tool_call", "progress"):
                    append_streaming_event(request_id, evt)
                    if event_name == "agent_switch":
                        to_agent = event_data.get("to_agent", "")
                        if to_agent:
                            agent_type = to_agent
                            update_progress(request_id, "delegating",
                                            agent_messages.get(to_agent, f"{to_agent} agent processing"))
                elif event_name == "content":
                    chunk = event_data.get("text", "")
                    if chunk:
                        response += chunk
                        content_chunk_count += 1
                        set_streaming_content(request_id, response)
                        if event_data.get("agent_type"):
                            agent_type = event_data["agent_type"]
                        # Persist reasoning flag so SSE poller can forward it
                        if event_data.get("is_reasoning"):
                            append_streaming_event(request_id, {
                                "event": "content_meta",
                                "data": {"is_reasoning": True, "agent_type": event_data.get("agent_type", "")}
                            })
                elif event_name == "complete":
                    complete_response = event_data.get("response", response)
                    complete_agent = event_data.get("agent_type", agent_type)
                    if complete_response:
                        response = complete_response
                    if complete_agent:
                        agent_type = complete_agent
                    streaming_succeeded = True
                    break

            if response:
                set_streaming_content(request_id, response)

        except Exception as stream_err:
            logger.warning(f"Streaming invoke failed for {request_id}: {stream_err}")

        # Streaming failed (connection error, cold-start timeout, etc.) — retry with a
        # single blocking invoke_runtime() call so the request still completes.
        if not streaming_succeeded:
            logger.info(f"Falling back to non-streaming invoke for {request_id}")
            result = await agentcore.invoke_runtime(
                runtime_arn=SUPERVISOR_RUNTIME_ARN,
                payload=payload,
                session_id=session_id,
            )
            response = result.get("response", "")
            agent_type = result.get("agent_type", "supervisor")

        # Save turn to memory (all paths)
        if response:
            _memory_save_turn(request.message, response, user_id, session_id)
            # Save conversation metadata (for sidebar listing)
            if request.conversation_id:
                try:
                    table = _get_conversations_table()
                    from datetime import datetime, timezone
                    table.put_item(Item={
                        "user_id": user_id,
                        "conversation_id": request.conversation_id,
                        "title": request.message[:80],
                        "first_message": request.message[:200],
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    pass  # Non-critical — don't fail the chat

        await _complete_with_workflow(response, agent_type)
        
    except Exception as e:
        logger.error(f"Error processing chat {request_id}: {e}", exc_info=True)
        fail_request(request_id, _safe_error_message(e))


async def _process_workflow_automation_async(request_id: str, workflow_id: str, current_user: Dict) -> None:
    """Background processor for full workflow automation."""
    from app.services.chat_state import update_progress, complete_request, fail_request
    from app.services.workflow_service import get_workflow_service
    
    try:
        update_progress(request_id, "routing", "Starting full automation workflow")
        await asyncio.sleep(2)
        update_progress(request_id, "delegating", "Step 1/4: Creating Jira ticket")
        await asyncio.sleep(1)
        workflow_service = get_workflow_service()
        result = await workflow_service.execute_full_automation(workflow_id, use_dynamic=True)
        complete_request(request_id, {
            "success": result.get("success", False),
            "content": result.get("message", "Automation completed"),
            "agent_type": "workflow_automation",
            "workflow_complete": True,
            "step_results": result.get("result", {}).get("steps", [])
        })
    except Exception as e:
        logger.error(f"Error in workflow automation {request_id}: {e}", exc_info=True)
        fail_request(request_id, _safe_error_message(e))


async def _process_workflow_step_async(request_id: str, workflow_id: str, step_type: str, current_user: Dict) -> None:
    """Background processor for individual workflow step approvals."""
    from app.services.chat_state import update_progress, complete_request, fail_request, append_streaming_event
    from app.services.workflow_service import get_workflow_service

    step_messages = {
        "jira": "Creating Jira ticket",
        "kb_search": "Searching knowledge base",
        "remediation": "Executing remediation",
        "closure": "Closing Jira ticket",
        "full_auto": "Running full automation",
    }

    try:
        update_progress(request_id, "executing", step_messages.get(step_type, "Processing workflow step..."))
        workflow_service = get_workflow_service()

        if step_type == "full_auto":
            # Track per-step status to detect mutations
            # (workflow_graph mutates existing dicts from "executing" -> "completed")
            step_statuses = {}  # {step_num: last_seen_status}

            def on_step_progress(results: dict) -> None:
                steps = results.get("steps", [])
                for i, step in enumerate(steps):
                    step_num = step.get("step_num", i + 1)
                    current_status = step.get("status", "")
                    prev_status = step_statuses.get(step_num)

                    # Emit if new step (prev_status is None) or status changed
                    if current_status != prev_status:
                        step_statuses[step_num] = current_status
                        append_streaming_event(request_id, {
                            "event": "progress",
                            "data": {
                                "type": "workflow_step",
                                "step_num": step_num,
                                "step_name": step.get("step") or step.get("message", ""),
                                "status": current_status,
                                "result": (step.get("result", "") or "")[:2000] if current_status == "completed" else "",
                                "message": step.get("message", ""),
                            }
                        })

            result = await workflow_service.approve_step(workflow_id, step_type, progress_callback=on_step_progress)
        else:
            result = await workflow_service.approve_step(workflow_id, step_type)

        complete_request(request_id, result)
    except Exception as e:
        logger.error(f"Error in workflow step {step_type} for {request_id}: {e}", exc_info=True)
        fail_request(request_id, _safe_error_message(e))


@router.get("/chat/history")
async def get_chat_history(
    k: int = 10,
    conversation_id: Optional[str] = None,
    current_user: Dict = Depends(get_current_user),
) -> dict:
    """Return the last k conversation turns from AgentCore Memory for the current user."""
    k = min(k, 50)  # Cap to prevent unbounded memory fetches

    # Validate conversation_id format (same rule as ChatRequest validator)
    if conversation_id is not None:
        conversation_id = conversation_id.strip().lower()
        if not _CONVERSATION_ID_PATTERN.match(conversation_id):
            raise HTTPException(status_code=400, detail="conversation_id must be a valid UUID")

    memory_id = settings.MEMORY_ID
    if not memory_id:
        return {"success": True, "messages": []}

    user_id = current_user.get("user_id", current_user.get("sub"))
    session_id = f"msp-{user_id}-{conversation_id}" if conversation_id else _user_session_id(user_id)

    try:
        mem_client = _get_memory_client()
        if not mem_client:
            return {"success": True, "messages": []}

        resp = mem_client.list_events(
            memoryId=memory_id, actorId=user_id, sessionId=session_id, includePayloads=True
        )
        events = resp.get("events", [])[-k:]
        if not events:
            return {"success": True, "messages": []}

        messages = []
        for ev in events:
            for msg in ev.get("payload", []):
                conv = msg.get("conversational", {})
                role = conv.get("role", "")
                content = conv.get("content", {}).get("text", "")
                if not content:
                    continue
                sender = "user" if role.upper() == "USER" else "agent"
                messages.append({
                    "id": str(uuid.uuid4()),
                    "sender": sender,
                    "content": content,
                    "agentType": None,
                    "timestamp": ev.get("eventTimestamp", ""),
                })
        return {"success": True, "messages": messages}
    except Exception as e:
        logger.warning(f"Failed to load chat history: {e}")
        return {"success": True, "messages": []}


@router.post("/chat")
@limiter.limit("10/minute")
async def send_chat_message(request: Request, body: ChatRequest, current_user: Dict = Depends(get_current_user)) -> dict:
    """
    POST /chat — submit a chat message for async processing.

    Auth: Bearer JWT (Cognito).
    Request body: ChatRequest {message, account_name, workflow_enabled, full_automation, conversation_id}
    Response: {request_id, status: "processing"}

    Immediately returns a request_id and spawns _process_chat_async as a background Task.
    Clients poll GET /chat/{request_id} or stream GET /chat/{request_id}/stream.
    """
    from app.services.chat_state import create_request
    request_id = str(uuid.uuid4())
    user_id = current_user.get("user_id", current_user.get("sub"))
    agent_hint = _detect_agent_stage(body.message)
    create_request(request_id, user_id, agent_hint)
    track_task(asyncio.create_task(_process_chat_async(request_id, body, current_user)))
    return {"request_id": request_id, "status": "processing"}


@router.get("/chat/{request_id}")
async def get_chat_result(request_id: str, event_index: int = 0, current_user: Dict = Depends(get_current_user)) -> dict:
    """
    GET /chat/{request_id} — poll once for a chat request's current state.

    Auth: Bearer JWT (Cognito).
    Query params: event_index (int, default 0) — only return streaming_events after this index
    Response: {request_id, status, progress, result, streaming_events, event_count}
    Status values: "processing" | "complete" | "error"
    Returns 404 if the request_id is not found or belongs to a different user.
    """
    from app.services.chat_state import get_request
    user_id = current_user.get("user_id", current_user.get("sub"))
    entry = get_request(request_id, user_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found or access denied")
    all_events = entry.get("streaming_events", [])
    return {
        "request_id": request_id,
        "status": entry["status"],
        "progress": entry["progress"],
        "result": entry.get("result"),
        "streaming_events": all_events[event_index:],
        "event_count": len(all_events),
    }


@router.get("/chat/{request_id}/stream")
async def stream_chat_result(request_id: str, current_user: Dict = Depends(get_current_user)) -> StreamingResponse:
    """
    GET /chat/{request_id}/stream — Server-Sent Events stream for a chat request.

    Auth: Bearer JWT (Cognito).
    Media type: text/event-stream

    Delegates to chat_state.get_progress_stream() which polls DynamoDB at 300 ms
    intervals and yields SSE-formatted strings.  Event types forwarded:
      progress, agent_switch, tool_call, content, complete, error.

    X-Accel-Buffering: no disables nginx proxy buffering so chunks reach the browser
    immediately.  API Gateway has a 29 s idle timeout; a heartbeat comment is emitted
    every 20 s to prevent the connection from being closed prematurely.
    """
    from app.services.chat_state import get_progress_stream
    user_id = current_user.get("user_id", current_user.get("sub"))
    return StreamingResponse(
        get_progress_stream(request_id, user_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )





# --- Auth Cookie Config ---
_REFRESH_COOKIE = "msp_refresh_token"
_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days

class SetRefreshRequest(BaseModel):
    refresh_token: str
    id_token: Optional[str] = None

class AccountCreateRequest(BaseModel):
    account_name: str
    account_id: str
    description: Optional[str] = None


# --- Auth Endpoints ---

@router.post("/auth/set-refresh")
async def auth_set_refresh(body: SetRefreshRequest, response: Response) -> dict:
    """Store Cognito refresh token (and optionally id_token) in httpOnly cookies."""
    response.set_cookie(
        key=_REFRESH_COOKIE, value=body.refresh_token,
        httponly=True, secure=True, samesite="none", max_age=_COOKIE_MAX_AGE, path="/",
    )
    if body.id_token:
        response.set_cookie(
            key="session_token", value=body.id_token,
            httponly=True, secure=True, samesite="none", max_age=3600, path="/",
        )
    return {"success": True}


@router.post("/auth/restore")
@limiter.limit("5/minute")
async def auth_restore(request: Request) -> dict:
    """Restore session from httpOnly refresh cookie. Returns new tokens."""
    import base64 as _b64
    import json as _json
    refresh_token = request.cookies.get(_REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token cookie")
    try:
        import boto3 as _boto3
        cognito = _boto3.client("cognito-idp", region_name=settings.AWS_REGION)
        result = cognito.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": refresh_token},
            ClientId=settings.COGNITO_CLIENT_ID,
        )
        auth_result = result["AuthenticationResult"]
        id_token = auth_result["IdToken"]
        access_token = auth_result["AccessToken"]
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = _json.loads(_b64.b64decode(payload_b64))
        response = JSONResponse({
            "success": True, "idToken": id_token, "accessToken": access_token,
            "user": {"userId": payload.get("sub"), "email": payload.get("email") or payload.get("cognito:username"), "username": payload.get("cognito:username") or payload.get("email")},
        })
        new_refresh = auth_result.get("RefreshToken")
        if new_refresh:
            response.set_cookie(key=_REFRESH_COOKIE, value=new_refresh, httponly=True, secure=True, samesite="none", max_age=_COOKIE_MAX_AGE, path="/")
        return response
    except Exception as e:
        err_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
        logger.warning(f"Session restore failed: {e}")
        http_status = status.HTTP_401_UNAUTHORIZED if err_code in ("NotAuthorizedException", "InvalidParameterException") else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(status_code=http_status, detail="Session restore failed")


@router.post("/auth/logout")
async def auth_logout(response: Response) -> dict:
    """Clear httpOnly cookies."""
    response.delete_cookie(key=_REFRESH_COOKIE, path="/", httponly=True, secure=True, samesite="none")
    response.delete_cookie(key="session_token", path="/", httponly=True, secure=True, samesite="none")
    return {"success": True}


# --- User Info Endpoints ---

@router.get("/me")
async def get_user_info(current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /me — return the authenticated user's JWT claims."""
    return {"user": current_user, "authenticated": True, "message": "Token is valid"}


@router.get("/msp-principal")
async def get_msp_principal(current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /msp-principal — return the MSP ECS task IAM principal ARN and account ID."""
    try:
        return {"success": True, "principal_arn": get_current_msp_principal_arn(), "account_id": get_current_msp_account_id()}
    except Exception as e:
        logger.warning(f"MSP principal lookup failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get MSP principal")


# --- Conversation Management ---
_conversations_table = None

def _get_conversations_table() -> object:
    global _conversations_table
    if _conversations_table is None:
        import boto3
        dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
        _conversations_table = dynamodb.Table(settings.CONVERSATIONS_TABLE)
    return _conversations_table


@router.get("/conversations")
async def list_conversations(current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /conversations — list all conversations for the current user."""
    user_id = current_user.get("user_id", current_user.get("sub"))
    try:
        table = _get_conversations_table()
        resp = table.query(KeyConditionExpression="user_id = :uid", ExpressionAttributeValues={":uid": user_id}, ScanIndexForward=False)
        return {"success": True, "conversations": resp.get("Items", [])}
    except Exception as e:
        logger.warning(f"Failed to list conversations: {e}")
        return {"success": True, "conversations": []}


@router.post("/conversations")
async def create_conversation(request: Request, current_user: Dict = Depends(get_current_user)) -> dict:
    """POST /conversations — create/update a conversation entry."""
    from datetime import datetime, timezone
    user_id = current_user.get("user_id", current_user.get("sub"))
    body = await request.json()
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")
    try:
        table = _get_conversations_table()
        table.put_item(Item={"user_id": user_id, "conversation_id": conversation_id, "title": body.get("title", "New Conversation")[:100], "first_message": body.get("first_message", "")[:200], "updated_at": datetime.now(timezone.utc).isoformat()})
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """DELETE /conversations/{id} — remove a conversation."""
    user_id = current_user.get("user_id", current_user.get("sub"))
    try:
        table = _get_conversations_table()
        table.delete_item(Key={"user_id": user_id, "conversation_id": conversation_id})
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Account Management ---

@router.get("/accounts")
async def list_accounts(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100), current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /accounts — paginated list of registered customer accounts."""
    try:
        account_service = get_account_service()
        result = await account_service.list_accounts()
        if result["success"]:
            accounts = [{"id": "default", "name": "Default (Current MSP)", "type": "msp", "status": "active"}]
            for account in result["accounts"]:
                accounts.append({"id": account["id"], "name": account["name"], "account_id": account["account_id"], "type": "customer", "status": account["status"], "role_name": account["role_name"], "external_id": account["external_id"], "created_at": account.get("created_at"), "needs_refresh": account["needs_refresh"]})
            total = len(accounts)
            start = (page - 1) * page_size
            return {"success": True, "accounts": accounts[start:start+page_size], "total": total, "page": page, "page_size": page_size}
        else:
            return {"success": True, "accounts": [{"id": "default", "name": "Default (Current MSP)", "type": "msp", "status": "active"}], "total": 1, "page": 1, "page_size": page_size}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list accounts")


@router.post("/accounts/prepare")
@router.post("/accounts/{account_name}/prepare")
async def prepare_account(request: Request, account_name: str = None, current_user: Dict = Depends(get_current_user)) -> dict:
    """POST /accounts/prepare — validate cross-account IAM access."""
    try:
        if not account_name:
            body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
            account_name = body.get("account_name", "") if isinstance(body, dict) else ""
        if not account_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="account_name is required")
        account_service = get_account_service()
        result = await account_service.prepare_account(account_name)
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Preparation failed"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account preparation failed")


@router.post("/accounts")
async def create_account(request_body: AccountCreateRequest, current_user: Dict = Depends(get_current_user)) -> dict:
    """POST /accounts — register a new customer AWS account."""
    try:
        account_service = get_account_service()
        result = await account_service.create_account(request_body.account_name, request_body.account_id, request_body.description)
        if result["success"]:
            return {"success": True, "message": result["message"], "account": result["account"]}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account creation failed")


@router.delete("/accounts/{account_name}")
async def delete_account(account_name: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """DELETE /accounts/{account_name} — remove a customer account."""
    account_name = _sanitize_account_name(account_name)
    try:
        account_service = get_account_service()
        result = await account_service.delete_account(account_name)
        if result.get("success"):
            return {"success": True, "message": result["message"]}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message", "Unknown error"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account deletion failed")


@router.put("/accounts/{account_name}/refresh")
async def refresh_account(account_name: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """PUT /accounts/{account_name}/refresh — refresh STS credentials."""
    account_name = _sanitize_account_name(account_name)
    try:
        account_service = get_account_service()
        result = await account_service.refresh_account(account_name)
        if result["success"]:
            return result
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["message"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Token refresh failed")


@router.post("/accounts/refresh-all")
async def refresh_all_accounts(current_user: Dict = Depends(get_current_user)) -> dict:
    """POST /accounts/refresh-all — re-issue STS credentials for all accounts."""
    try:
        account_service = get_account_service()
        return await account_service.refresh_all_accounts()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Refresh all failed")


@router.post("/accounts/{account_name}/switch")
async def switch_account(account_name: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """POST /accounts/{account_name}/switch — set active account context."""
    account_name = _sanitize_account_name(account_name)
    try:
        account_service = get_account_service()
        return await account_service.switch_account_context(account_name if account_name != "default" else None)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Account switch failed")


# --- Health Endpoints ---

@router.get("/health/protected")
async def protected_health_check(current_user: Dict = Depends(get_current_user)) -> dict:
    return {"status": "healthy", "authenticated": True, "user_id": current_user["user_id"], "email": current_user["email"]}


@router.get("/health/summary")
async def get_health_summary(current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /health/summary — AWS Service Health Dashboard summary."""
    try:
        health_service = get_health_service()
        return await health_service.get_health_summary()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Health summary failed")


@router.get("/health/outages")
async def get_health_outages(current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /health/outages — current AWS regional outages."""
    try:
        health_service = get_health_service()
        return await health_service.get_outages()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch outages")


@router.get("/health/scheduled")
async def get_health_scheduled(current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /health/scheduled — upcoming AWS scheduled maintenance."""
    try:
        health_service = get_health_service()
        return await health_service.get_scheduled_maintenance()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch scheduled maintenance")


@router.get("/health/notifications")
async def get_health_notifications(current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /health/notifications — recent AWS Health event notifications."""
    try:
        health_service = get_health_service()
        return await health_service.get_notifications()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch notifications")


# --- Workflow Endpoints ---

@router.get("/workflows/pending")
async def get_pending_workflows(current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /workflows/pending — list workflows waiting for human approval."""
    try:
        workflow_service = get_workflow_service()
        return await workflow_service.get_pending_approvals()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch pending workflows")


@router.post("/workflows/{workflow_id}/approve/{step_type}")
async def approve_workflow_step(workflow_id: str, step_type: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """POST /workflows/{id}/approve/{step} — approve and execute one workflow step."""
    try:
        from app.services.chat_state import create_request
        request_id = str(uuid.uuid4())
        user_id = current_user.get("user_id", current_user.get("sub"))
        create_request(request_id, user_id, f"workflow_{step_type}")
        track_task(asyncio.create_task(_process_workflow_step_async(request_id, workflow_id, step_type, current_user)))
        return {"success": True, "request_id": request_id, "status": "processing"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Step approval failed")


@router.post("/workflows/{workflow_id}/reject/{step_type}")
async def reject_workflow_step(workflow_id: str, step_type: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """POST /workflows/{id}/reject/{step} — reject a pending workflow step."""
    try:
        workflow_service = get_workflow_service()
        return await workflow_service.reject_step(workflow_id, step_type)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Step rejection failed")


@router.get("/workflows/{workflow_id}/status")
async def get_workflow_status(workflow_id: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /workflows/{id}/status — current state of a workflow."""
    try:
        workflow_service = get_workflow_service()
        result = await workflow_service.get_workflow_status(workflow_id)
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("message"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Status check failed")


@router.post("/workflows/{workflow_id}/automate")
async def execute_full_automation(workflow_id: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """POST /workflows/{id}/automate — kick off full end-to-end automation."""
    try:
        from app.services.chat_state import create_request
        request_id = str(uuid.uuid4())
        user_id = current_user.get("user_id", current_user.get("sub"))
        create_request(request_id, user_id, "workflow_automation")
        track_task(asyncio.create_task(_process_workflow_automation_async(request_id, workflow_id, current_user)))
        return {"success": True, "request_id": request_id, "status": "processing"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Automation failed")


@router.get("/workflows/{workflow_id}/progress")
async def get_automation_progress(workflow_id: str, current_user: Dict = Depends(get_current_user)) -> dict:
    """GET /workflows/{id}/progress — per-step automation progress."""
    try:
        workflow_service = get_workflow_service()
        return await workflow_service.get_automation_progress(workflow_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Progress check failed")
