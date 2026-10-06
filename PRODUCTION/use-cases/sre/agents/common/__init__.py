"""Shared runtime library for the SRE multi-agent system.

Pure LangGraph + the AgentCore wire protocols (HTTP/A2A/MCP) — no Strands dependency. Modules:
- `llm`        : Bedrock Claude via LangChain, single factory used by every agent.
- `a2a`        : minimal A2A (JSON-RPC 2.0) server adapter + client, per the AgentCore contract.
- `context`    : per-request tenant/scenario context propagated across A2A hops and tool calls.
- `contract`   : AgentCore container-contract helpers (ping, ports) shared by all runtimes.
"""
