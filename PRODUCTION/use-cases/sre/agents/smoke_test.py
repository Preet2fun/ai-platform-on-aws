"""P1 end-to-end smoke test: supervisor -> investigator -> (telemetry+change) -> remediation.

Runs in-process (local fallback, no A2A URLs) against the synthetic backend on :8080, exercising
the full hypothesis loop with real Bedrock Claude. Prints the hypothesis lanes + conclusion so we
can eyeball that the agent reached (or approached) the scenario's ground-truth root cause.

Usage:
  SRE_TOOLS_BASE_URL=http://localhost:8080 AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
    python3 agents/smoke_test.py acme-retail rds-connection-exhaustion \
    "checkout-api 5xx spike (checkout-api-5xx-high)"
"""
from __future__ import annotations

import json
import sys

from agents.common.context import RequestContext
from agents.supervisor.graph import run_supervisor


def main():
    tenant = sys.argv[1] if len(sys.argv) > 1 else "acme-retail"
    scenario = sys.argv[2] if len(sys.argv) > 2 else "rds-connection-exhaustion"
    alarm = sys.argv[3] if len(sys.argv) > 3 else "checkout-api 5xx spike (alarm: checkout-api-5xx-high)"

    ctx = RequestContext(tenant_id=tenant, scenario_id=scenario, session_id="smoke-" + "x" * 30)
    print(f"\n=== Investigating [{tenant}/{scenario}] alarm: {alarm} ===\n")
    result = run_supervisor(alarm, ctx)

    print("--- THOUGHT STREAM ---")
    for step in result.get("thought_stream", []):
        print("  •", step)

    print("\n--- HYPOTHESES ---")
    for h in result.get("hypotheses", []):
        print(f"  [{h.get('id')}] {h.get('status','?').upper():12} {h.get('statement','')}")
        if h.get("reason"):
            print(f"        reason: {h['reason']}")

    print("\n--- CONCLUSION ---")
    print(json.dumps(result.get("conclusion", {}), indent=2))

    print("\n--- REMEDIATION (HITL proposal) ---")
    print(json.dumps(result.get("remediation", {}), indent=2)[:1500])


if __name__ == "__main__":
    main()
