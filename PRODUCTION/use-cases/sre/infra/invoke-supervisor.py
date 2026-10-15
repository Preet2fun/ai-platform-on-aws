"""Checkpoint 4 — invoke the deployed supervisor runtime end-to-end (SigV4).

Sends an alarm to the supervisor's AgentCore Runtime and prints the aggregated result.
This exercises the full cloud chain:
  supervisor (HTTP) -> investigator (A2A) -> telemetry/change (A2A) -> tools (SigV4) -> conclusion
Usage:
  AWS_PROFILE=agentcore AWS_REGION=us-east-1 python3 infra/invoke-supervisor.py <tenant> <scenario> "<alarm>"
"""
import json
import sys
import uuid

import boto3
from botocore.config import Config

SUPERVISOR_ARN = (
    "arn:aws:bedrock-agentcore:us-east-1:001961766007:runtime/sre_agentic_dev_supervisor-dSf6vD9ngf"
)


def main():
    tenant = sys.argv[1] if len(sys.argv) > 1 else "acme-retail"
    scenario = sys.argv[2] if len(sys.argv) > 2 else "rds-connection-exhaustion"
    alarm = sys.argv[3] if len(sys.argv) > 3 else "RDS connection pool exhausted on checkout-service; 5xx spiking"

    payload = json.dumps({
        "tenant_id": tenant,
        "scenario_id": scenario,
        "alarm": alarm,
        "session_id": str(uuid.uuid4()),
        "stream": False,
    }).encode("utf-8")

    # The full nested chain can run for minutes; the platform allows up to 15 min synchronous.
    client = boto3.client(
        "bedrock-agentcore",
        config=Config(read_timeout=840, connect_timeout=10, retries={"max_attempts": 0}),
    )
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=SUPERVISOR_ARN,
        qualifier="DEFAULT",
        runtimeSessionId=f"ckpt4-{uuid.uuid4().hex}{uuid.uuid4().hex}",
        payload=payload,
    )

    ct = resp.get("contentType", "") or ""
    body = resp.get("response")
    if "text/event-stream" in ct:
        parts = []
        for line in body.iter_lines(chunk_size=10):
            if line:
                line = line.decode("utf-8") if isinstance(line, bytes) else line
                if line.startswith("data: "):
                    parts.append(line[6:])
        raw = "".join(parts)
    else:
        chunks = []
        for chunk in body:
            chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        raw = "".join(chunks)

    try:
        data = json.loads(raw)
    except Exception:
        print("RAW RESPONSE:", raw[:2000])
        return

    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
