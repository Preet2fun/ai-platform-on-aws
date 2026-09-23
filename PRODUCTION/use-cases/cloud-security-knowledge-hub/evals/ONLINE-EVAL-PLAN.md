# Online Evaluation — Design & Implementation Plan

> **Status:** design only — **not built yet.**
> **What this is:** continuous quality evaluation of the RAG system on **real production
> traffic** after release, as opposed to the offline eval (golden set, pre-release gate) that
> already exists in `evals/offline/`.
>
> **Why separate from offline:** offline eval answers *"is this version good enough to ship?"*
> against curated ground truth. Online eval answers *"is the shipped system still good on
> real, changing questions?"* — usually **without** ground truth, using proxies.

---

## 1. The gap today

| Signal | Exists? | Notes |
|---|---|---|
| Operational metrics (latency, errors, invocations) | ✅ | CloudWatch + X-Ray + alarms — **observability, not quality** |
| Golden-set accuracy (offline) | ✅ | `evals/offline/` — pre-release only |
| **Live Q&A captured anywhere** | ❌ | `query-service/app.py` logs only errors — **there is no record of production questions/answers to evaluate** |
| **Online quality metrics** | ❌ | no LLM-judge on live answers, no user feedback, no deflection/guardrail-rate tracking, no drift alarm |

**Hard prerequisite:** online eval needs a **data source of production Q&A**. That does not
exist yet. Step 1 below creates it. Everything else depends on it.

---

## 2. Target architecture

```
User question ──▶ Query Lambda (run_pipeline)
                     │  emits one structured JSON log line per request:
                     │  {request_id, ts, question, answer, citations[], retrieved,
                     │   latency_ms, blocked, is_idk, model_id, flags}
                     ▼
              CloudWatch Logs  ── (async, decoupled from the user request) ──▶
                     │
        ┌────────────┴─────────────┐
        ▼                          ▼
  Scheduled sampler          User feedback API
  (EventBridge → Lambda)     POST /feedback {request_id, rating}
        │  sample N/day             │  → DynamoDB feedback table
        ▼                           ▼
  LLM-as-judge (Bedrock)      aggregate thumbs up/down
  faithfulness + relevancy         │
  on live answers (no GT)          │
        └────────────┬─────────────┘
                     ▼
        CloudWatch namespace  CSHub/OnlineEval
        (quality proxies + rates)  ──▶ dashboard widgets + drift alarms
```

Key principle: **online eval is asynchronous and off the request path.** The user never waits
for scoring; a sampler reads logs after the fact. This keeps query latency unaffected.

---

## 3. What to implement (phased)

### Step 1 — Capture production Q&A (the prerequisite)
- In `query-service/app.py`, emit **one structured JSON log line per request** (question,
  answer, citation doc_ids, retrieved count, latency, `blocked`, `is_idk`, model id, flags,
  `request_id`). Use `print(json.dumps(...))` — CloudWatch captures stdout.
- **Privacy:** questions may contain sensitive text. Decide retention (e.g. 30–90 days) and
  whether to hash/redact. Output-guardrail already blocks secret PII in answers.
- *(Optional)* also persist to the DynamoDB request table for easier querying than Logs Insights.
- **No new infra required** beyond the log line — CloudWatch Logs already exists.

### Step 2 — Automated quality proxies (LLM-as-judge on live answers)
- **EventBridge scheduled rule** (e.g. hourly/daily) → **sampler Lambda**.
- Sampler queries CloudWatch **Logs Insights** for a random sample of the last window's Q&A.
- For each sampled answer, reconstruct context (from cited doc_ids, like `offline/score.py`),
  run the **Bedrock LLM-judge** for **faithfulness** and **answer_relevancy** (no ground truth
  needed — these two don't require it; context_precision/recall need labels so are offline-only).
- Emit aggregates to CloudWatch **`CSHub/OnlineEval`** (avg faithfulness, avg relevancy, sample size).
- Reuse `evals/lib/` + the judge prompts from `offline/score.py` — factor the judge into
  `evals/lib/judge.py` so offline and online share it.

### Step 3 — Behavioural / product proxies (no LLM needed)
Computed directly from the Step-1 logs by the same sampler:
- **Deflection rate** — % of answers that are "I don't have enough information" (`is_idk`).
  Rising deflection = corpus gaps or retrieval regression.
- **Guardrail-block rate** — % `blocked` on input/output. Spikes = attack traffic or a
  guardrail misconfig (recall the MISCONDUCT false-positive we fixed).
- **Citation rate / retrieved count** — answers with 0 citations = ungrounded responses.
- **Latency & error rate** — already in CloudWatch; surface alongside quality on one dashboard.

### Step 4 — User feedback loop (ground-truth-free signal)
- Add a **thumbs up/down** control in the SPA next to each answer.
- New **`POST /feedback`** route (API Gateway → small Lambda) writing
  `{request_id, rating, ts}` to a **DynamoDB feedback table**.
- Emit **helpfulness rate** to `CSHub/OnlineEval`. This is the most direct real-world quality
  signal; correlate it with the LLM-judge proxies to validate that the judge tracks reality.

### Step 5 — Drift detection & alarms
- CloudWatch **alarms** on `CSHub/OnlineEval`: alert if faithfulness proxy drops below a floor
  or falls week-over-week (anomaly detection), deflection rate spikes, or helpfulness drops.
- Add an **Online quality** row to the `cshub-dev-hub` dashboard beside the operational widgets.
- Route alarms to the existing SNS topic (`cshub-dev-alerts`).

### Step 6 — Close the loop back to offline
- **Mine hard/low-rated live questions** (thumbs-down, low judge score, high deflection) into
  golden-set candidates → human-review → append to `golden/golden.jsonl`.
- This grows the offline golden set from real usage (the standard flywheel), so the pre-release
  gate keeps getting more representative over time.

---

## 4. AWS services (all reuse existing patterns)

| Purpose | Service | New? |
|---|---|---|
| Capture Q&A | CloudWatch Logs (structured line) | ✅ log line in app.py |
| Sampler schedule | EventBridge scheduled rule | ✅ small |
| Sampler + judge | Lambda (in VPC) + Bedrock InvokeModel | ✅ new Lambda |
| Query live Q&A | CloudWatch Logs Insights | reuse |
| Feedback store | DynamoDB table + `POST /feedback` Lambda | ✅ new |
| Metrics | CloudWatch `CSHub/OnlineEval` namespace | ✅ |
| Dashboard + alarms | CloudWatch (extend `05-observability.yaml`) | extend |
| Alerts | SNS `cshub-dev-alerts` | reuse |

Estimated footprint: 1 scheduled sampler Lambda + 1 feedback Lambda + 1 DynamoDB table +
dashboard/alarm additions. Bedrock judge cost scales with sample size (sample, don't score 100%).

---

## 5. Metric summary — offline vs online

| Metric | Offline (golden set) | Online (live traffic) |
|---|---|---|
| faithfulness | ✅ (vs ground truth context) | ✅ (LLM-judge, no GT) |
| answer_relevancy | ✅ | ✅ (LLM-judge, no GT) |
| context_precision / recall | ✅ (needs labels) | ❌ (no labels live) |
| deflection rate (`is_idk`) | — | ✅ |
| guardrail-block rate | — | ✅ |
| helpfulness (user 👍/👎) | — | ✅ |
| latency / errors | measured on golden run | ✅ live (already in CloudWatch) |

---

## 6. Recommended order

1. **Step 1 (capture Q&A)** — do this first; nothing else works without it. Small, low-risk.
2. **Step 3 (behavioural proxies)** — free once logs exist; immediate signal (deflection, blocks).
3. **Step 2 (LLM-judge sampler)** — the core online quality metric.
4. **Step 5 (alarms/dashboard)** — make it continuous + alertable.
5. **Step 4 (user feedback)** — needs a UI change; highest-value real signal.
6. **Step 6 (mine into golden set)** — ongoing flywheel.

> **Sequencing note:** this is independent of Phase-3 (advanced RAG). It is most valuable
> **after** the system takes real traffic. For a not-yet-launched ~20-user tool, Steps 1 + 3
> are a sensible minimum to ship at launch; Steps 2/4/5 follow once there's traffic to sample.
