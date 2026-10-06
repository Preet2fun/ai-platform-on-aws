# Synthetic Observability Backends (Option A)

Six tenant-scoped read APIs that serve the synthetic incident fixtures to the agents' MCP tools.
One shared FastAPI app (`common/app.py`) exposes all six routers; each maps 1:1 to an MCP tool in
P4 (OpenAPI → MCP via the AgentCore Gateway), so the OpenAPI schema here **is** the tool contract.

| Router | Path | Serves |
|---|---|---|
| metrics-api | `GET /metrics` | metric time-series |
| logs-api | `GET /logs` | log lines |
| traces-api | `GET /traces` | trace/span summaries |
| changes-api | `GET /changes` | deploys / config / scaling / infra changes |
| k8s-events-api | `GET /events` | k8s / platform events |
| runbooks-api | `GET /runbooks` | tenant operational runbooks (keyword/service search) |

**Every data call requires `tenant_id`** (tenant isolation) and `scenario_id` (which incident to
serve); `runbooks` is tenant-level (no scenario). Optional filters: `service`, time `start`/`end`,
and per-router extras (`metric`, `level`, `contains`, `errors_only`, `change_type`, `source`).

## Run locally
```bash
cd PRODUCTION/use-cases/sre
python3 -m venv .venv && source .venv/bin/activate
pip install -r tools/requirements.txt
uvicorn tools.common.app:app --reload --port 8080
# OpenAPI docs: http://localhost:8080/docs
# example:
curl "http://localhost:8080/metrics?tenant_id=acme-retail&scenario_id=rds-connection-exhaustion&service=product-db&metric=active_connections"
curl "http://localhost:8080/changes?tenant_id=globex-fintech&scenario_id=pod-crashloop-bad-config"
```

## Notes
- Fixtures live in `../synthetic-data/tenants/<tenant_id>/scenarios/<scenario_id>/`.
- `manifest.yaml` is **eval-only ground truth** and is NOT exposed by any route.
- Data root override: `SRE_SYNTH_DATA_ROOT` env var (defaults to the repo path).
- P9: a `cloudwatch_tools` backend implements the same routes against real CloudWatch — agents
  swap data source by config, not code.
