# Phase 1 · Stage C — Live Online Testing & Online Eval

> **Online eval** = quality measured on **real production traffic**, after release, **without
> ground truth** — the opposite of Stage B's golden-set gate. It answers *"is the shipped
> system still good on real, changing questions?"* using LLM-judge proxies (faithfulness,
> relevancy) plus behavioural proxies (deflection, guardrail-block, citation coverage, latency).
> Design: `../../evals/ONLINE-EVAL-PLAN.md`. Config label: `phase1-online`.

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
A real user drove the deployed UI (`https://d1s8aphl5ns4nb.cloudfront.net`) and asked **7
free-form security questions** in natural, imperfect phrasing (typos included — this is the
point of *online* testing: real traffic, not curated goldens). Each produced a `CSHUB_QA` log
line. We pulled the window from CloudWatch Logs Insights:

```
fields @timestamp, @message
| filter @message like /CSHUB_QA/
| sort @timestamp desc
```

The 7 records were exported to a JSON array and scored with a purpose-built online scorer:

```
python evals/online/score_online.py \
    --qa <live-qa.json> --config phase1-online \
    --out evals/results/phase1-online.json --emit-cloudwatch
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

> This is why Q4 (the out-of-scope SigV4 question) scored **faithfulness 1.00** — it refused
> instead of inventing, which is exactly what the faithfulness prompt rewards.
>
> **Honest limitation:** the `CSHUB_QA` line logs only the citation **doc_ids**, not the
> retrieved passage **text**, so online faithfulness is currently judged on the answer's
> self-consistency rather than against what retrieval actually returned. Note this is a
> *logging* choice, not a data-availability problem — retrieval already has the full passage
> text in memory (see §C.1.2). Same root cause as **FI-4**; the fix in §C.1.2 upgrades this to
> true retrieved-context grounding.

**Step 5b — the behavioural proxies (no LLM, just counting).** These come straight from the log
fields with simple formulas over the N = 7 questions:

| Proxy | Formula | This run |
|---|---|---|
| deflection_rate | (# with `is_idk = true`) / N | 1 / 7 = 0.143 |
| guardrail_block_rate | (# with `blocked` set) / N | 0 / 7 = 0.0 |
| citation_coverage | (# with ≥ 1 citation) / N | 7 / 7 = 1.0 |
| full_retrieval_rate | (# with `retrieved ≥ 6`) / N | 7 / 7 = 1.0 |
| avg_latency_ms | mean(`latency_ms`) | 5,291.6 |
| p95_latency_ms | 95th-percentile(`latency_ms`) | 6,846 |

**Step 6 — aggregate + publish.** The per-question faithfulness/relevancy scores are **averaged**
across the 7 questions (0.871 and 0.921), the proxies are the counts above, and everything is
written to `evals/results/phase1-online.json` and pushed to CloudWatch namespace
`CSHub/OnlineEval` (dimension `Config=phase1-online`) so it can be graphed and alarmed alongside
the operational metrics.

> **Why sequential, not parallel:** the judge makes 2 Bedrock calls per question (14 total); the
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

> **Future — content-carrying traces (FI-6).** The standard maturity step is to instrument with
> **OpenTelemetry GenAI tracing** (ADOT layer + GenAI spans). Then each trace carries the user
> query, the retrieved chunks, and the answer as span attributes — one trace = one full
> conversation turn — and eval can be driven from **both logs and traces**, scored against the
> real retrieved context. That's the trace-based route to the FI-4 fix. Tracked as **FI-6** in
> `FUTURE-IMPROVEMENTS.md`; not instrumented in Phase 1.

### The retrieved text already exists — it's just not logged yet
Here is the key point behind FI-4. Retrieval (`query-service/common/retrieval.py`,
`dense_search`) returns a `Hit` object that already contains the full chunk **text**:

```python
@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    text: str        # ← the actual retrieved passage, in memory at answer time
    score: float
    metadata: dict
```

So the real context the model saw is available **inside the request** — we simply chose to log
only the citation `doc_id`s (to keep log lines small). The offline scorer, lacking that text,
tried to reconstruct it from local sample files and scored S3-only docs a false 0.00 (FI-4).

### The fix: log the retrieved text, score against it, run it on a schedule
This is a small change that closes FI-4 **and** makes online eval automated end to end:

1. **Capture the real context (tiny code change).** Add the retrieved passage text (or a bounded
   snippet + `chunk_id`) to the `CSHUB_QA` line — or, to keep logs lean, write full Q&A + context
   to the DynamoDB request table (the plan's optional store). The text is already in `hits`, so
   this is just "include what we already have."
2. **Score against real context.** The scorer then judges faithfulness against **what retrieval
   actually returned**, not the answer's self-consistency — the same rigour as offline, on live
   traffic. No more false 0.00 on PDF-sourced answers.
3. **Automate it (no human in the loop).** This is Step 2 of `../../evals/ONLINE-EVAL-PLAN.md`:
   an **EventBridge schedule → sampler Lambda** reads a random sample of recent `CSHUB_QA`
   records, runs the Bedrock judge, and emits to `CSHub/OnlineEval` — then **drift alarms**
   (Step 5) fire if faithfulness/deflection cross a threshold. The manual run in this document
   is that same scoring logic, done by hand once to prove it; wrapping it in the scheduled
   Lambda is what makes it continuous.

> **In short:** *yes*, the fix both **solves the accuracy problem** (grounds against real
> retrieved text) and **keeps it automated** (scheduled sampler + alarms), and it's cheaper than
> it first looked because the retrieved text is already in hand — the gap was logging, not data.
> Tracked as **FI-4** plus Steps 2/5 of the online-eval plan; see §C.5.

## C.2 — The 7 live questions & answers

| # | Question (as typed) | Answer summary | IDK | Cites | Retrieved | Latency |
|---|---|---|---|---|---|---|
| 1 | How do I stop EKS pods from stealing node IAM permissions? | IRSA / Pod Identity for scoped creds; block pod IMDS (hop-limit 1 / network policy) | no | 6 | 6 | 6,123 ms |
| 2 | what is KMS service ? | AWS KMS = managed key create/manage; HSM-backed; customer/AWS-managed/AWS-owned keys | no | 6 | 6 | 5,762 ms |
| 3 | what kind of encryption does KMS support ? | Server-side + client-side (Encryption SDK); encryption & signing keys | no | 6 | 6 | 3,501 ms |
| 4 | is SignAUth 4 is part of KMS encrypton or how ? | **"I don't have enough information…"** (correct: SigV4 is request signing, not KMS encryption; not in corpus) | **yes** | 6 | 6 | 3,659 ms |
| 5 | How do I prevent SSRF against EC2 IMDS? | Require IMDSv2 (`HttpTokens=required`), hop-limit 1, egress controls | no | 6 | 6 | 5,396 ms |
| 6 | I need S3 bucket to get access from my EKS pod ..what are the aviable option nd how should i configure it ? | IRSA / Pod Identity + scoped bucket policy; step-by-step | no | 6 | 6 | 6,846 ms |
| 7 | how encryption works in S3-SSE ? | SSE-S3, SSE-KMS, SSE-C explained | no | 6 | 6 | 5,754 ms |

Notable behaviour:
- **Q4 is the standout positive.** A confused, out-of-scope question ("is SigV4 part of KMS
  encryption?") correctly returned **"I don't have enough information from the knowledge base"**
  instead of hallucinating a plausible-but-wrong answer. This is exactly the grounding
  discipline the guardrail + prompt are designed for — the system refused rather than invented.
- **Every answer carried 6 citations and retrieved the full top-6** — no ungrounded (0-citation)
  responses in the sample.
- Several answers correctly cited the newly-ingested **SRA PDF** chunks alongside the sample
  docs (Q2, Q3, Q6, Q7) — confirming Stage-A ingestion is live in retrieval.

## C.3 — Results

### Quality proxies (Bedrock LLM-as-judge, no ground truth)
| Metric | Value | Notes |
|---|---|---|
| Faithfulness | **0.871** | grounding / no-fabrication check on each live answer |
| Answer relevancy | **0.921** | how directly each answer addresses the question |

Per-question judge scores:

| # | Question | Faithfulness | Relevancy |
|---|---|---|---|
| 1 | EKS pods stealing node IAM | 0.75 | 1.00 |
| 2 | what is KMS | 0.95 | 1.00 |
| 3 | KMS encryption types | 0.85 | 0.70 |
| 4 | SigV4 part of KMS? (IDK) | **1.00** | 0.85 |
| 5 | prevent SSRF vs IMDS | 0.85 | 1.00 |
| 6 | S3 access from EKS pod | 0.85 | 0.95 |
| 7 | how S3-SSE encryption works | 0.85 | 0.95 |

The IDK answer (Q4) scored **faithfulness 1.00** — it invented nothing — validating that honest
refusals are rewarded, not penalised, by the online scorer.

### Behavioural proxies (computed from log fields, no LLM)
| Proxy | Value | Reading |
|---|---|---|
| Deflection rate (`is_idk`) | **14.3%** (1 / 7) | the single deflection was the correct out-of-scope refusal (Q4) — a healthy deflection, not a corpus gap |
| Guardrail-block rate (`blocked`) | **0.0%** | no input/output guardrail trips on this benign traffic |
| Citation coverage | **100%** | every answer was grounded with ≥1 citation |
| Full-retrieval rate (≥6 chunks) | **100%** | retrieval consistently filled the top-6 |
| Avg latency | **5,292 ms** | consistent with the offline p95; dominated by generation |
| p95 latency | **6,846 ms** | in line with Stage-B offline p95 (7,506 ms) |

Results file: `../../evals/results/phase1-online.json`. Metrics emitted to CloudWatch namespace
**`CSHub/OnlineEval`** (8 metrics, dimension `Config=phase1-online`) — verified present via
`aws cloudwatch list-metrics --namespace CSHub/OnlineEval`.

## C.4 — Online vs offline (same corpus, different lens)
| Metric | Offline (Stage B, corrected) | Online (Stage C, live) |
|---|---|---|
| Faithfulness | 0.915 | 0.871 |
| Answer relevancy | 0.959 | 0.921 |
| p95 latency | 7,506 ms | 6,846 ms |
| Deflection | — (golden set, 1 IDK) | 14.3% |
| Guardrail-block | — | 0.0% |

Online numbers are a touch lower than offline, which is expected: live questions are messier
(typos, under-specified, out-of-scope like Q4) than curated goldens, and the online faithfulness
judge is stricter (no ground-truth context to lean on). Both stay **well above the gate floors**
(faith 0.80 / rel 0.75). The system behaves correctly on real, imperfect traffic.

## C.5 — What this stage proves (and its limits)
**Proves:**
- The Step-1 capture line works end-to-end — real production Q&A is now observable and scorable.
- The system is **honest under uncertainty** (Q4 IDK) and **fully grounded** (100% citation
  coverage) on live traffic.
- Online eval is runnable today with the existing pieces (log capture + Bedrock judge + lib),
  no new infra required for the scoring itself.

**Limits (carried to Phase 2 / FUTURE-IMPROVEMENTS):**
- This was a **manual, 7-question sample**, not the automated **EventBridge → sampler Lambda**
  from the plan (Step 2 infra). Continuous online eval still needs that scheduled sampler.
- No **user-feedback loop** yet (thumbs 👍/👎 → `POST /feedback` → DynamoDB) — Step 4 of the plan.
- No **drift alarms** on `CSHub/OnlineEval` yet — Step 5 of the plan.
- ~~Online faithfulness is judged against the answer's self-consistency, not the real retrieved
  passage text~~ — **resolved in C.7 via FI-6** (content-carrying traces). The self-consistency
  numbers above (C.3) are the initial run; the trace-grounded run is C.7.

## C.6 — Reproduce (self-consistency run, C.3)
```
# 1. pull live Q&A (Logs Insights: filter @message like /CSHUB_QA/), export to JSON array
# 2. score + emit
python evals/online/score_online.py \
    --qa <live-qa.json> --config phase1-online \
    --out evals/results/phase1-online.json --emit-cloudwatch
```

## C.7 — Upgrade: trace-grounded online eval (FI-6)

The C.3 run judged faithfulness on the answer's **self-consistency** because the retrieved
passage *text* wasn't captured anywhere (only citation doc_ids in the `CSHUB_QA` log). That is
the online half of **FI-4**. We closed it by instrumenting the query Lambda with
**OpenTelemetry GenAI tracing** (**FI-6**): each query now emits a content-carrying `rag.query`
span to **CloudWatch Transaction Search** (the `aws/spans` log group) that includes the
**real retrieved chunks** (`cshub.chunk.N.{id,doc_id,score,text}` + a joined
`cshub.retrieved_context`), the question, and the answer — keyed by `cshub.request_id`.

`score_online.py` now reads that span and judges faithfulness against **what retrieval actually
returned**, the same rigour as the offline gate — on live traffic.

### Trace-grounded result (`Config=phase1-online-traced`, 6 live queries)
| Metric | Value | Basis |
|---|---|---|
| Faithfulness | **1.00** | judged against **real retrieved context** on **6/6** records (`basis=retrieved_context`) |
| Answer relevancy | **0.833** | two "what encryption does KMS support" answers scored 0.40 / 0.65 — a genuine relevancy signal, not a scorer artifact |
| grounded_on_real_context | **6/6** | every record scored against actual passages, none fell back to self-consistency |

Faithfulness rising to 1.00 is expected and *correct*: when the judge sees the exact passages
the model was given, well-grounded answers score fully — the earlier 0.75–0.95 spread was the
self-consistency proxy being conservative without the context. The relevancy dip on the KMS
question is a real quality signal the trace-grounded eval surfaced.

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
# score straight from the trace spans (last 60 min):
python evals/online/score_online.py --from-traces --minutes 60 \
    --config phase1-online-traced \
    --out evals/results/phase1-online-traced.json --emit-cloudwatch

# or enrich a CSHUB_QA export with real context joined by request_id:
python evals/online/score_online.py --qa <live-qa.json> --minutes 120 \
    --config phase1-online --out evals/results/phase1-online.json --emit-cloudwatch
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
