# Phase 1 · Stage D — Observability Deep-Dive

> This is the cross-cutting observability record for the whole Phase-1 run: **what telemetry
> exists, where it lives, its current sample values, and how to navigate it in the AWS
> console.** It also answers two questions raised during the run: *how do I see these metrics in
> the console?* and *can I see the chunks and their metadata in the console?*
>
> Infra source: `../../infra/05-observability.yaml` (stack `cshub-dev-hub` resources).
> Account `001961766007` · region `us-east-1` · profile `agentcore` · tag `usecase=rag-prod`.
> Values below are **samples captured 2026-09-23** — point-in-time, not live guarantees.

## D.0 — Three layers of telemetry
The system separates **operational** signals (is it up / fast / erroring?) from **quality**
signals (is it *good*?). Quality further splits into pre-release and live:

| Layer | Question it answers | Where | Namespace |
|---|---|---|---|
| Operational | up / fast / erroring? | CloudWatch built-ins + X-Ray | `AWS/Lambda`, `AWS/ApiGateway`, `AWS/RDS`, `AWS/States` |
| Ingestion quality | is the index clean? | custom metrics on each ingestion run | `CSHub/Ingestion` |
| Offline eval (pre-release gate) | good enough to ship? | custom metrics from the golden-set run | `CSHub/Eval` |
| Online eval (live traffic) | still good on real questions? | custom metrics from the online scorer | `CSHub/OnlineEval` |
| Raw Q&A record | what did users actually ask/get? | structured log line | CloudWatch Logs `/aws/lambda/cshub-dev-query` |

## D.1 — Custom metric inventory + current sample values

### `CSHub/Ingestion` (14 metrics — emitted by the `manifest` handler per ingestion run)
Per-document and corpus-wide gauges.

| Metric | Sample value | Meaning |
|---|---|---|
| `corpus_docs` | 20* → **30**† | distinct documents in the index |
| `corpus_chunks` | 644* → **534**† | total chunks in the index |
| `corpus_avg_chunk_chars` | 975.2* | mean chunk size |
| `services_covered` | 17 | distinct AWS services represented |
| `corpus_chunks_per_doc` | 32.2* | chunks ÷ docs |
| `corpus_null_embedding_rate` | 0.0 | fraction of chunks with a null embedding |
| `corpus_empty_chunk_rate` | 0.0 | fraction of empty chunks |
| `null_embedding_rate` / `empty_chunk_rate` / `duplicate_chunk_rate` / `oversized_chunk_rate` / `undersized_chunk_rate` | 0.0 | per-run quality rates |
| `chunk_count` / `avg_chunk_chars` | per-doc | last-ingested doc's stats |

> **\* Gauge drift — an observability finding.** These corpus gauges read **20 docs / 644
> chunks**, but the true clean corpus after Stage-A cleanup is **19 docs / 337 chunks**. Cause:
> corpus metrics are only re-emitted **when an ingestion pipeline runs** (the `manifest`
> handler). The 644 figure is the pre-cleanup peak (SRA + the partial KMS attempt + the
> duplicate `yourfile.pdf`). The cleanup was done **out-of-band** (a one-off Lambda + direct
> row deletes), which does not trigger `manifest`, so the gauge never refreshed. Logged as a
> Phase-1 observability gap (see D.5). Fix: re-emit corpus metrics after any deletion, or run a
> scheduled corpus-snapshot Lambda independent of ingestion.
>
> **† Gauge drift self-corrected (2026-09-28).** For the final Phase-1-vs-Phase-2 re-test the
> corpus was enlarged (11 new PDFs) and all 19 pre-existing docs re-ingested for FI-3. Those 30
> ingestion runs re-fired the `manifest` handler, so the corpus gauges refreshed to the **true**
> current state — **30 docs / 534 chunks / 17 services / 0.0 null-embedding**. This incidentally
> confirms the root cause above: the gauges are accurate whenever ingestion actually runs; they
> only go stale after out-of-band edits. The standing fix (scheduled snapshot Lambda) is still
> the right long-term answer.

### `CSHub/Eval` (4 metrics — offline golden-set gate, dimension `Config`)
Canonical run `Config=phase1-final` (61-pair golden, 30-doc/534-chunk corpus, scored against
real FI-6 trace context):

| Metric | All 61 (in CloudWatch) | In-corpus 58 (headline) |
|---|---|---|
| `faithfulness` | 0.938 | **0.969** |
| `answer_relevancy` | 0.884 | **0.930** |
| `context_precision` | 0.811 | **0.849** |
| `context_recall` | 0.818 | **0.845** |

> The all-61 numbers are what's stored in CloudWatch; they're dragged down by the **3
> out-of-corpus pairs** the offline judge penalizes for refusing (**FI-7** — the answers are
> correct refusals). The **in-corpus 58** column is the headline. FI-4 is fixed: every record is
> scored against the real retrieved passage text via FI-6 trace spans (61/61), so PDF-sourced
> content no longer false-0.00s. See `02-offline-eval.md` §B.3.

### `CSHub/OnlineEval` (8 metrics — live traffic, dimension `Config=phase1-final-online`)
From the 13-question live run (scored 13/13 on real trace context):

| Metric | Value |
|---|---|
| `faithfulness` | 0.955 |
| `answer_relevancy` | 0.873 |
| `deflection_rate` | 0.231 (3/13, all out-of-corpus) |
| `guardrail_block_rate` | 0.0 |
| `full_retrieval_rate` | 1.0 |

`citation_coverage`/`avg_latency_ms`/`p95_latency_ms` read 0 on the `--from-traces` path (those
come from the `CSHUB_QA` log, not the span). See `03-online-testing.md` §C.2/§C.6.

## D.2 — Alarms (stack `cshub-dev-hub`, all currently **OK**)
| Alarm | Metric | Threshold | Fires when |
|---|---|---|---|
| `cshub-dev-query-errors` | `AWS/Lambda Errors` (query) | > 3 / 5 min | query Lambda erroring |
| `cshub-dev-query-p95-latency` | `AWS/Lambda Duration` p95 | > 6,000 ms / 3×5 min | queries slow |
| `cshub-dev-api-5xx` | `AWS/ApiGateway 5xx` | > 5 / 5 min | API server errors |
| `cshub-dev-ingestion-quality` | `CSHub/Ingestion null_embedding_rate` | > 0 / day | ingestion produced null embeddings |

All alarm actions route to the SNS topic **`cshub-dev-alerts`** (email subscription). There is
also a **monthly cost Budget** `cshub-dev-monthly` (default \$300) with 50% / 80% actual and
100% forecasted alerts, filtered by the project cost tag.

> **Gap:** there are **no alarms on `CSHub/Eval` or `CSHub/OnlineEval`** yet — quality drift is
> measured but not alerted. This is Step 5 of `../../evals/ONLINE-EVAL-PLAN.md`, deferred to
> Phase 2.

## D.3 — Dashboard `cshub-dev-hub` (7 widgets)
1. Query Lambda — invocations & errors
2. Query Lambda — duration p50 / p95
3. Aurora Serverless v2 — capacity (ACU)
4. Ingestion — Step Functions executions (succeeded / failed)
5. Offline eval scores (RAGAS)
6. Ingestion quality — chunk rates (empty / null / duplicate / oversized)
7. Ingestion corpus — size & coverage (chunks / docs / services / avg chars)

> **Gaps found in Phase 1:**
> - Widget 5 is **hardcoded to `Config=baseline`** — it will not show the `phase1-final`
>   run. Either standardise the config label per release or add a per-config widget.
> - There is **no `CSHub/OnlineEval` widget** — the online-eval metrics exist but aren't on the
>   dashboard yet. Add an "Online quality" row (Step 5 of the online-eval plan).

## D.4 — How to navigate this in the AWS console

**See the dashboard (start here):**
CloudWatch → **Dashboards** → `cshub-dev-hub`. All 7 widgets on one page. Set the time range
(top-right) wide enough — eval/corpus metrics use a 1-day period, so pick "1w" or "2w" or they
look empty.

**See a specific custom metric / pick your own stat:**
CloudWatch → **Metrics → All metrics** → under **Custom namespaces** choose `CSHub/Ingestion`,
`CSHub/Eval`, or `CSHub/OnlineEval` → tick the metric(s). For `Eval`/`OnlineEval` you'll first
pick the `Config` dimension (e.g. `phase1-final`, `phase1-final-online`). Use the **Graphed
metrics** tab to change statistic (Average/Maximum/p95) and period.
> Tip: corpus gauges (`corpus_docs`, `corpus_chunks`) are point-in-time snapshots — graph them
> with **Maximum** over a wide window, not Average over 5 min, or you'll see gaps.

**See alarms:** CloudWatch → **Alarms** → filter `cshub`. Green = OK. Click one to see its
history and the SNS action.

**See the raw production Q&A (the `CSHUB_QA` log line):**
CloudWatch → **Logs → Logs Insights** → select log group `/aws/lambda/cshub-dev-query` → run:
```
fields @timestamp, @message
| filter @message like /CSHUB_QA/
| sort @timestamp desc
| limit 50
```
Each line is one question/answer with citations, latency, `is_idk`, `blocked`, and `flags`.
This is the source for online eval (`03-online-testing.md`).

**See request-level tracing:** X-Ray (or CloudWatch → **Traces**) for the query Lambda —
segment breakdown across retrieval → Bedrock generation, useful for latency root-cause.

**See content-carrying GenAI traces (FI-6):** the query Lambda is now instrumented with
OpenTelemetry, so each turn also emits a `rag.query` span with the **question, retrieved chunk
text, and answer**. These land in **CloudWatch Transaction Search** — CloudWatch → **Transaction
Search** (or the `aws/spans` log group in Logs Insights). Query them by content, e.g.
`fields @message | filter @message like /cshub.question/`. This is the source for the
trace-grounded online eval in `03-online-testing.md` §C.7.

## D.5 — "Can I see the chunks and their metadata in the AWS console?"
**Short answer: not directly, and that's by design.** The chunks + embeddings + metadata live
in **Aurora PostgreSQL (pgvector)**, and this cluster is **private** (no public endpoint, in
private subnets). So there is **no console table-browser** for them:

- The RDS console shows the **cluster** (`cshub-dev-data-dbcluster-...`): status, ACU capacity,
  connections, CPU — **operational** metrics, **not row data**.
- The **RDS Query Editor** (console SQL) requires the **RDS Data API**, which is **off** on this
  cluster (Data API enable didn't flip during the run — see `01-...` note). So you can't browse
  chunk rows from the console today.
- To actually read chunk rows/metadata you go through the VPC: a Lambda/bastion in the private
  subnets running SQL against `chunks` (this is how the corpus snapshots and Stage-A verification
  were done — a temporary in-VPC Lambda).

**What you _can_ inspect from the console without the DB:**
- **Chunk & text artifacts in S3** — the processed bucket `cshub-dev-processed-001961766007`
  holds intermediate `chunks/`, `text/`, and `clean/` objects per document. Open them in the S3
  console to see the chunk text and structure before embedding.
- **Manifests** — the artifacts bucket `cshub-dev-artifacts-001961766007` under `manifests/`
  records per-document ingestion results (counts, quality rates).
- **Corpus size/coverage** — the `CSHub/Ingestion` corpus gauges on the dashboard (subject to
  the D.1 drift caveat).

> If browsing chunk rows from the console is wanted later, the low-risk options are: enable the
> **RDS Data API** + Query Editor (read-only role), or add a tiny **internal "corpus inspector"**
> read endpoint. Both are Phase-2 conveniences, not Phase-1 blockers.

## D.6 — Observability gaps carried forward (summary)
| # | Gap | Impact | Where tracked |
|---|---|---|---|
| 1 | Corpus gauges drift after out-of-band deletes (only refresh on ingestion) | dashboard shows 20/644 vs real 19/337 | this doc D.1 |
| 2 | Dashboard eval widget hardcoded to `Config=baseline` | latest eval run not shown | this doc D.3 |
| 3 | No `CSHub/OnlineEval` dashboard widget | online quality not visualised | online-eval plan Step 5 |
| 4 | No alarms on `CSHub/Eval` / `CSHub/OnlineEval` | quality drift measured, not alerted | online-eval plan Step 5 |
| 5 | Chunk rows not console-browsable (private Aurora, Data API off) | must use in-VPC SQL to inspect index | this doc D.5 |

These are **observability** improvements (visibility of an otherwise-healthy system), distinct
from the pipeline findings **FI-1…FI-6** in `FUTURE-IMPROVEMENTS.md`. (FI-6 — OTel
content-carrying traces — is now **implemented**: the query Lambda emits `rag.query` spans with
the question, retrieved chunk text, and answer to CloudWatch Transaction Search, which powers
the trace-grounded online eval. See `03-online-testing.md` §C.7.)

> **Telemetry-layer update (FI-6).** The D.0 table's "Operational · X-Ray" row is now
> supplemented by a **content** trace layer: `rag.query` GenAI spans in the `aws/spans` log
> group (CloudWatch Transaction Search) carrying query + retrieved context + answer per turn.
> This is a fourth telemetry source alongside the three CloudWatch custom namespaces.
