# Phase 1 · Stage C — Live Online Testing & Online Eval

> **Online eval** = quality measured on **real production traffic**, after release, **without
> ground truth** — the opposite of Stage B's golden-set gate. It answers *"is the shipped
> system still good on real, changing questions?"* using LLM-judge proxies (faithfulness,
> relevancy) plus behavioural proxies (deflection, guardrail-block, citation coverage, latency).
> Design: `../../evals/ONLINE-EVAL-PLAN.md`. Config label: `phase1-final-online`.

## C.0 — Prerequisite: production Q&A capture (Step 1 of the plan)
Online eval has no data to score unless live Q&A is captured. Before this stage, the query
Lambda only logged errors. We added a structured capture line (`_log_qa()` in
`query-service/app.py`) that emits **one JSON line per request** to CloudWatch Logs:

```
CSHUB_QA {"request_id","ts","question","answer","citations":[doc_ids],
          "retrieved","latency_ms","blocked","is_idk","model_id","flags"}
```

It is a plain `print(json.dumps(...))` on stdout — asynchronous to the user, **zero added query
latency**, decoupled from the request path. This is the hard prerequisite for everything below.

## C.1 — Test method
A real user drives the deployed UI (`https://d1s8aphl5ns4nb.cloudfront.net`) and asks the
**10 frozen questions** in `evals/online/ONLINE-QUESTION-SET.md` — the **same list used for both
Phase-1 and Phase-2** so the online comparison is a fair A/B. The set mixes in-corpus questions
(original + new PDFs, incl. the FI-5 IAM case) with **out-of-corpus** questions (Azure, GCP) that
should trigger an honest refusal. Each produces a `CSHUB_QA` log line and an FI-6 trace span.

The run is scored directly from the trace spans (real retrieved context), no manual export:

```
AWS_PAGER="" AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
python3 evals/online/score_online.py --from-traces --minutes <N> \
    --config phase1-final-online \
    --out evals/results/phase1-final-online.json --emit-cloudwatch
```

**Why a separate scorer from `offline/score.py`:** offline scores against golden ground-truth
context. Online has none. The online scorer judges only the two metrics that don't need labels
(faithfulness, answer_relevancy) and computes behavioural proxies directly from the log fields.
`context_precision`/`context_recall` are offline-only by design (they require labelled context).

## C.1.1 — How the eval was measured, end to end

This is the exact chain from *you logging in and asking a question* to *a number in
CloudWatch*. Nothing here runs on the user's request path — scoring happens **after the fact**
from the logs.

```
[1] You log in to the UI (Cognito)         ── real user session, SRP auth
        │  type a question, hit send
        ▼
[2] Query Lambda answers it                 ── retrieve (dense top-6) → Claude → guardrails
        │  and, as a side-effect, prints:
        ▼
[3] CSHUB_QA {json} line → CloudWatch Logs  ── one line per question (the raw record)
        │  (async, adds no latency to your answer)
        ▼
[4] We collect the lines (Logs Insights)    ── filter /CSHUB_QA/, export the 7 to a JSON array
        │
        ▼
[5] score_online.py reads that array        ── per question:
        │      • 2 quality metrics  → ask Claude (LLM-as-judge) for a 0–1 score
        │      • behavioural proxies → computed with plain arithmetic from the log fields
        ▼
[6] Aggregate + emit                          ── mean the per-question scores, count the proxies,
                                                 write results JSON + put metrics to CloudWatch
```

**Step 2 — what each captured field means.** Every `CSHUB_QA` line already carries the raw
signals we score, so no extra instrumentation was needed:
- `question`, `answer` — the text pair the judge reads.
- `citations` — the doc_ids the answer was grounded on (→ citation coverage).
- `retrieved` — how many chunks retrieval returned (→ full-retrieval rate).
- `is_idk` — did the system say "I don't have enough information" (→ deflection).
- `blocked` — did an input/output guardrail trip (→ guardrail-block rate).
- `latency_ms` — server-side answer time (→ latency proxies).

**Step 5a — the two quality metrics (LLM-as-judge).** For each question the scorer sends the
question + answer to Claude on Bedrock (temperature 0, "reply with ONLY a number 0.0–1.0") and
reads back a single score. There is **no ground truth** on live traffic, so the two label-free
metrics are:

| Metric | What the judge is asked | Why it's honest without ground truth |
|---|---|---|
| **faithfulness** | "Does the answer make only claims consistent with established AWS security facts and its own citations, with no fabricated APIs/parameters? An answer that correctly says it lacks information invents nothing → score 1.0." | It penalises hallucination and rewards honest refusals — it does not need a golden answer to do that. |
| **answer_relevancy** | "How directly does the answer address the question? A truthful 'I don't have enough information' to an out-of-scope question is on-point." | Relevance is judged against the *question*, which we always have. |

> This is why an out-of-corpus question (e.g. the Azure/GCP ones in the frozen set) scores
> **faithfulness 1.00** when it refuses — it invents nothing, which is exactly what the
> faithfulness prompt rewards.
>
> Faithfulness is judged against the **real retrieved passage text** carried on the FI-6 trace
> span (joined by `request_id`), not the answer's self-consistency — see §C.6. This closed the
> online half of **FI-4**.

**Step 5b — the behavioural proxies (no LLM, just counting).** These come straight from the log
fields with simple formulas over the N = 10 questions:

| Proxy | Formula |
|---|---|
| deflection_rate | (# with `is_idk = true`) / N |
| guardrail_block_rate | (# with `blocked` set) / N |
| citation_coverage | (# with ≥ 1 citation) / N |
| full_retrieval_rate | (# with `retrieved ≥ 6`) / N |
| avg_latency_ms | mean(`latency_ms`) |
| p95_latency_ms | 95th-percentile(`latency_ms`) |

For this fixed 10-question set, `deflection_rate` should be ≈ 0.2 (the two out-of-corpus
questions), and every in-corpus answer should carry ≥ 1 citation.

**Step 6 — aggregate + publish.** The per-question faithfulness/relevancy scores are **averaged**
across the 10 questions, the proxies are the counts above, and everything is written to
`evals/results/phase1-final-online.json` and pushed to CloudWatch namespace `CSHub/OnlineEval`
(dimension `Config=phase1-final-online`) so it can be graphed and alarmed alongside the
operational metrics.

> **Why sequential, not parallel:** the judge makes 2 Bedrock calls per question (20 for the 10-Q set); the
> scorer runs them one at a time with exponential backoff because parallel judge calls throttle
> and the local Python path is single-threaded here. Small sample, so this is fast enough.

## C.1.2 — Do we use trace data? And how the FI-4 fix makes it accurate *and* automated

Two questions worth answering plainly, because they shape Phase 2.

### Why the score comes from logs, not X-Ray traces
X-Ray **is** enabled on the query Lambda (`TracingConfig = Active`), so we do have traces — but
this is **plain X-Ray auto-tracing** (no OTel/ADOT layer attached), which records **timing and
call structure** (how long retrieve → Bedrock → guardrails took), **not the content**. The
question text, the answer, and the retrieved passages are **not** in the trace. So:

| Source | Holds | Used for |
|---|---|---|
| **X-Ray traces** | per-stage latency, error segments | latency root-cause (why a query was slow) — *operational* |
| **`CSHUB_QA` logs** | question, answer, citations, is_idk, blocked, latency | the online **quality** eval above |

That split is deliberate for the *plain* X-Ray we have today: traces answer *"is it
fast/healthy?"*, the Q&A log answers *"is it good?"*.

> **Content-carrying traces (FI-6) — now DONE.** The query Lambda is instrumented with
> **OpenTelemetry GenAI tracing** (ADOT layer + GenAI spans). Each `rag.query` span carries the
> user query, the retrieved chunks (id/doc_id/score/text), and the answer — one trace = one full
> conversation turn — exported to CloudWatch Transaction Search (`aws/spans`). Eval is now driven
> **from the spans**, scored against the **real retrieved context** — both offline
> (`score.py`, 61/61 this run) and online (`score_online.py --from-traces`). This closed **FI-4**.

### How the real retrieved text is captured (FI-4 fix, now live)
Retrieval (`query-service/common/retrieval.py`) returns `Hit` objects that carry the full chunk
`text`, and the FI-6 tracing wraps each turn so that text is emitted on the `rag.query` span
(`cshub.retrieved_context` + per-chunk `cshub.chunk.N.*`), keyed by `request_id`. The scorer
joins each record's `request_id` to its span and judges faithfulness against **what retrieval
actually returned** — the same rigour offline and online. This is what closed FI-4 (no more
false 0.00 on PDF-sourced answers).

> **Still pending — automation.** Scoring is proven and trace-grounded, but the run is still
> triggered by hand. The continuous path (EventBridge schedule → sampler Lambda → `CSHub/OnlineEval`
> → drift alarms) is Steps 2/5 of `../../evals/ONLINE-EVAL-PLAN.md`, deferred. See §C.5.

## C.2 — The frozen questions & results (config `phase1-final-online`)

A real operator drove the deployed UI (signed in via Cognito) and asked **13 questions** — 10
in-corpus AWS-security questions (WAF, GuardDuty, Shield+WAF, IAM least-privilege, S3 exposure,
stolen-access-key detection, Security Hub, Inspector, EC2-compromise IR) + 3 out-of-corpus
(Azure WAF, GCP encryption, and a nonsense "distance between Texas and NYC"). The exact set is
frozen in `../../evals/online/ONLINE-QUESTION-SET.md` and is reused verbatim for Phase-2.

Scored from the FI-6 trace spans (`--from-traces`), **13/13 on real retrieved context**:

### Quality (Bedrock LLM-as-judge, no ground truth)
| Metric | Value |
|---|---|
| Faithfulness | **0.955** |
| Answer relevancy | **0.873** |

### Behavioural proxies
| Proxy | Value | Reading |
|---|---|---|
| Deflection rate (`is_idk`) | **23.1%** (3/13) | the 3 out-of-corpus questions — all correct honest refusals |
| Guardrail-block rate | **0.0%** | no guardrail trips on benign security-education traffic |
| Full-retrieval rate | **100%** | retrieval consistently returned the top-6 |
| Grounded on real context | **13/13** | every record scored against actual retrieved passages |
| Citation coverage | 100%* | *from the `CSHUB_QA` log (every in-corpus answer carried 6 citations); reads 0 on the `--from-traces` path, which only sees span content — see §C.6 note |

### Notable behaviour
- **All 10 in-corpus questions answered, cited, none deflected** — including broad multi-service
  questions (Security Hub aggregation, EC2-compromise incident response) that span several docs.
- **All 3 out-of-corpus questions correctly refused** (faithfulness 1.00 each — they invent
  nothing). The two cloud-provider refusals (Azure WAF, GCP encryption) also scored relevancy
  0.90; the nonsense geography question scored relevancy 0.00 (the judge marks a refusal to a
  question with no legitimate in-scope intent as "not addressing it") — this single 0.00 is what
  pulls the relevancy mean to 0.873. It is correct behaviour, scored conservatively.
- Lowest in-corpus faithfulness was the stolen-access-key detection question (0.75) — a broad
  "which services" question where the answer reached slightly beyond the retrieved passages.

Results file: `../../evals/results/phase1-final-online.json`. Metrics → CloudWatch
`CSHub/OnlineEval` (dimension `Config=phase1-final-online`), 8 metrics.

## C.3 — Online vs offline (same corpus, different lens)
| Metric | Offline (`phase1-final`, in-corpus 58) | Online (`phase1-final-online`, 13 live) |
|---|---|---|
| Faithfulness | 0.969 | 0.955 |
| Answer relevancy | 0.930 | 0.873 |
| Deflection | 5 IDK / 61 (incl. 3 OOC) | 23.1% (3/13, all OOC) |
| Guardrail-block | — | 0.0% |

Online faithfulness (0.955) tracks the offline in-corpus headline (0.969) closely — the live
answers are as grounded as the golden run. Relevancy is a bit lower (0.873 vs 0.930), almost
entirely from the single nonsense out-of-scope question scoring 0.00; excluding it, online
relevancy is ~0.95. Both stay well above the gate floors (faith 0.80 / rel 0.75). The system
behaves correctly on real, messy traffic — grounded on in-corpus questions, honestly refusing
out-of-scope ones.

## C.5 — What this stage proves (and its limits)
**Proves (once the run is in):**
- The capture + trace path works end-to-end — real production Q&A is observable and scorable
  against **real retrieved context** (FI-6).
- The system is **honest under uncertainty** (the out-of-corpus questions deflect) and grounded
  on in-corpus answers.
- Online eval is runnable today with the existing pieces (trace spans + Bedrock judge), no new
  infra required for the scoring itself.

**Limits (carried to Phase 2 / FUTURE-IMPROVEMENTS):**
- This is a **fixed 10-question run**, not the automated **EventBridge → sampler Lambda** from
  the plan (Step 2 infra). Continuous online eval still needs that scheduled sampler.
- No **user-feedback loop** yet (thumbs 👍/👎 → `POST /feedback` → DynamoDB) — Step 4 of the plan.
- No **drift alarms** on `CSHub/OnlineEval` yet — Step 5 of the plan.

## C.6 — Trace-grounded online eval (FI-6) — the mechanism

Online faithfulness is judged against the **real retrieved context**, not the answer's
self-consistency, because the query Lambda is instrumented with **OpenTelemetry GenAI tracing**
(**FI-6**): each query emits a content-carrying `rag.query` span to **CloudWatch Transaction
Search** (the `aws/spans` log group) with the **real retrieved chunks**
(`cshub.chunk.N.{id,doc_id,score,text}` + a joined `cshub.retrieved_context`), the question, and
the answer — keyed by `cshub.request_id`. `score_online.py --from-traces` reads that span and
judges against **what retrieval actually returned** — the same rigour as the offline gate, on
live traffic. This closed the online half of **FI-4**.

> Two proxy fields read 0 on the pure `--from-traces` path (`citation_coverage`,
> `avg_latency_ms`): those come from the `CSHUB_QA` **log** (doc_ids, server latency), not the
> span (which carries content). The `--qa <file>` path joins both sources by `request_id` and
> reports them; `--from-traces` is the content-only shortcut.

### How the trace path works (end to end)
```
query -> Lambda run_pipeline
           ├─ CSHUB_QA log line     (behavioural proxies: is_idk, blocked, citations, latency)
           └─ rag.query OTel span   (content: question + retrieved chunk TEXT + answer)
                    │  ADOT layer -> awsxray exporter -> CloudWatch Transaction Search
                    ▼
              aws/spans log group
                    │  score_online.py --from-traces  (or --qa + join by request_id)
                    ▼
        Bedrock LLM-judge faithfulness vs REAL retrieved context -> CSHub/OnlineEval
```

### Reproduce (trace-grounded)
```
# score straight from the trace spans (window covering the run):
AWS_PAGER="" AWS_PROFILE=agentcore AWS_REGION=us-east-1 \
python3 evals/online/score_online.py --from-traces --minutes <N> \
    --config phase1-final-online \
    --out evals/results/phase1-final-online.json --emit-cloudwatch
```

### One-time prerequisite (account level)
Content spans export to **CloudWatch Transaction Search**, which must be enabled once:
```
aws xray update-trace-segment-destination --destination CloudWatchLogs
aws logs put-resource-policy --policy-name CshubTransactionSearchXRay \
  --policy-document '{... allow xray.amazonaws.com logs:PutLogEvents on aws/spans:* ...}'
```
See `FUTURE-IMPROVEMENTS.md` → FI-6 for the full policy and the ADOT layer/collector/sampler
configuration. This is the trace-eval foundation Phase 2 builds on (measuring each advanced-RAG
stage against real retrieved context, per conversation).
