# Synthetic incident scenario — schema

Each scenario is a self-contained, tenant-scoped incident "story" with a **ground-truth root
cause** (which doubles as the offline eval label). The synthetic backends read these fixtures and
serve them tenant- and time-scoped to the MCP tools; the agent never sees `manifest.yaml` (that is
eval-only ground truth).

```
synthetic-data/tenants/<tenant_id>/scenarios/<scenario_id>/
├── manifest.yaml     # alarm + ground-truth root cause + expected hypotheses (EVAL-ONLY, hidden from agent)
├── metrics.json      # time-series per service/metric (served by metrics-api)
├── logs.json         # log lines per service (served by logs-api)
├── traces.json       # spans/trace summaries (served by traces-api)
├── changes.json      # deploys / config changes / infra events (served by changes-api)
└── events.json       # k8s / platform events (served by k8s-events-api)
```

## `manifest.yaml` fields
| Field | Meaning |
|---|---|
| `scenario_id`, `tenant_id`, `title` | identity |
| `alarm` | the triggering alarm the agent receives (name, service, metric, threshold, fired_at) |
| `symptom_window` | `{start, end}` ISO-8601 — the time range the symptoms live in |
| `ground_truth.root_cause` | the single correct root cause (eval label) |
| `ground_truth.causal_chain` | ordered events from trigger → symptom |
| `ground_truth.remediation` | the correct fix (what the HITL step should propose) |
| `ground_truth.evidence_keys` | which fixtures/signals contain the smoking gun |
| `expected_hypotheses[]` | each `{id, statement, verdict: confirm|reject, reject_reason?}` — the agent should land on the `confirm` one and reject the rest for the stated reasons (hypothesis-rejection-quality eval) |
| `difficulty` | easy | medium | hard |
| `tags` | freeform (e.g. database, deploy, network) |

## Fixture conventions
- All timestamps ISO-8601 UTC; keep each scenario inside a ~60-min window.
- `metrics.json`: `{ service, metric, unit, points: [{ts, value}] }` — include a clear anomaly in
  the true-cause signal and plausible-but-not-causal wiggles elsewhere (so rejection is non-trivial).
- `logs.json`: `{ service, level, ts, message }` — the smoking-gun lines live in the true-cause
  service; include red-herring warnings elsewhere.
- `traces.json`: `{ trace_id, root_service, duration_ms, spans: [{service, op, duration_ms, error?}] }`.
- `changes.json`: `{ ts, type: deploy|config|scaling|infra, service, summary, actor, ref }`.
- `events.json`: `{ ts, source: k8s|platform, service, reason, message }`.
- Tenant/time scoping is enforced by the backend, not the fixture.
