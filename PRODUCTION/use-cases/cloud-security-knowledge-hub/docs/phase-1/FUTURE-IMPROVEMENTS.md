# Phase 1 — Future Improvements / Findings Register

Running log of issues surfaced during the Phase-1 walkthrough, each with a problem statement,
proposed solution, and current status (Done / Pending / Partial). Ordered as discovered.

---

## FI-1 — Embedding throttling on large documents (ingestion)

**Problem statement.** The offline ingestion pipeline embeds chunks **one Titan `InvokeModel`
call per chunk in a tight loop** (`ingestion/common/embed.py` → `embed_text`, called from
`ingestion/handlers/embed_upsert.py`). Small text/markdown docs (2 chunks) are fine, but a
large PDF produces hundreds–thousands of chunks (observed live: `aws-security-reference-
architecture-v4.pdf` → **306 chunks**, `kms-dg.pdf` → **2,213 chunks**). Embedding them in a
rapid loop bursts past Bedrock's on-demand throughput and returns
`ThrottlingException (reached max retries: 4)` — which **failed the entire Step Functions
execution** for both large PDFs. Surfaced during the Phase-1 Stage-A ingestion walkthrough.

**Proposed solution.**
1. **Retry-with-backoff + gentle inter-call pacing** (quick, robust): wrap the single Titan
   call in exponential backoff on throttling, and add a small pause every N chunks so a big doc
   doesn't burst the account's TPS limit. Absorbs transient throttling without failing the run.

**Status: ✅ DONE.** Implemented exponential backoff (1→20s, 6 attempts) in `embed_text`, and a
`sleep(1)` every 20 chunks in the `embed_upsert` loop. Repackaged + redeployed the
`cshub-dev-ingest-embed-upsert` Lambda. This fixes throttling-induced failures for
moderately-sized docs.

> **Note / caveat:** backoff alone does **not** make *very* large docs (e.g. the 2,213-chunk
> KMS guide) finish inside the Lambda's **900s max timeout** — the sequential per-chunk loop is
> the bottleneck at that scale. That is addressed by FI-2.

---

## FI-2 — Scale embedding for large docs via batching / Fargate

**Problem statement.** Even with backoff (FI-1), embedding is **sequential, one chunk at a
time, inside a Lambda** capped at a 900s timeout. A 2,000+ chunk document cannot complete in
that window. The original architecture anticipated this and reserved an **AWS Fargate
"heavy-embed" task** (no Lambda timeout) for large batches — but that path was **deferred in
Phase 1** (the Fargate ECR image was intentionally not built). So large PDFs currently have no
viable ingestion path.

**Proposed solution.**
1. **Batch/throttle embeddings** — reduce per-chunk overhead and stay under TPS (e.g. bounded
   concurrency with a token-bucket rate limiter), and/or
2. **Build the deferred Fargate heavy-embed path** — build + push the ARM64 image, and route
   documents above a chunk-count threshold from the Step Functions state machine to the Fargate
   task instead of the EmbedUpsert Lambda (the task definition already exists in
   `infra/02-ingestion.yaml`; only the image + the routing choice are missing).

**Status: ⏳ PENDING.** Deferred to Phase-1 hardening / Phase 2. For the Phase-1 walkthrough we
proceed with appropriately-sized documents; large multi-hundred-page AWS reference PDFs are out
of scope for the Lambda path until Fargate (or batching) lands.

---

## FI-3 — Per-chunk service metadata for large multi-service documents

**Problem statement.** The metadata classifier assigns **one `service` per document** (filename
first, then body-frequency fallback). This works for single-topic docs, but a large
multi-service document breaks it: the AWS Security Reference Architecture PDF
(`aws-security-reference-architecture-v4.pdf`, 307 chunks) has **no service keyword in its
filename**, so it fell to body-frequency, and across a 100-page doc that touches every service
"IAM" is the most-mentioned term → **all 307 chunks were tagged `iam`**. Observed live: corpus
`service_coverage` shows `iam: 309` after ingesting the SRA. The `service` tag is therefore
misleading for broad reference documents, which would weaken metadata-filtered retrieval.

**Proposed solution.** Classify `service` **per chunk from the chunk's own text** (the pipeline
already builds per-chunk metadata in `chunk.py`), and only use the filename as a hint when the
chunk text is ambiguous. Optionally drop the whole-doc `service` for multi-service docs (set it
to `mixed`/null) and rely on the per-chunk tags. For higher accuracy, consider an
embedding/LLM classifier instead of keyword matching.

**Status: ⏳ PENDING.** Documented as a finding from the SRA ingestion. Not blocking — dense
retrieval (the Phase-1 baseline) does not use the `service` filter; it matters when
metadata-filtered / hybrid retrieval is enabled in Phase 2.

---

## FI-4 — Offline scorer reconstructs context from local samples, not the real retrieval

**Problem statement.** `evals/offline/score.py` reconstructs the "retrieved context" for the
LLM-judge by reading the **local corpus** (`ingestion/samples/*.md`) by `doc_id`. This works
only for docs that exist as local sample files. The SRA PDF was uploaded **straight to S3**
(never a local sample), so the scorer found no local text for
`docs/aws-security-reference-architecture-v4.pdf` → judged the 4 SRA questions with **empty
context → 0.00 on all metrics** — even though the live answers were actually correct and
grounded (verified from the collected records). A **false negative in the scorer**, not a real
quality failure.

**Proposed solution.** Score against the **actual retrieved context**, not the local corpus.
The retrieved passage text is **already available** — `retrieval.dense_search` returns
`Hit.text` (the full chunk text) in memory at answer time; it is simply not persisted. So the
fix is to *capture what we already have*:
1. **(Preferred)** Include the retrieved passage text (or a bounded snippet + `chunk_id`) in the
   per-query record — either added to the `CSHUB_QA` log line, or written to the DynamoDB
   request table (the online-eval plan's optional store, better for large context). Then both
   the offline and online scorers judge against real context.
2. **(Alternative)** Have the scorer fetch chunk text from Aurora by `chunk_id` after the fact.
3. **Automation:** once context is captured, this drops straight into the scheduled
   **EventBridge → sampler Lambda** (Step 2 of `evals/ONLINE-EVAL-PLAN.md`) so scoring runs
   continuously and feeds drift alarms (Step 5) — no manual step.

Until then, restrict the golden set to docs present locally, or treat 0.00-with-a-real-answer as
"unscored".

**Status: ✅ DONE (both halves) — closed in Phase-2 Stage 0.**
- **Online path (FI-6):** the `rag.query` trace span carries the real retrieved passage text
  (`cshub.retrieved_context` + per-chunk `cshub.chunk.N.text`); `evals/online/score_online.py`
  scores faithfulness against it. Verified 6/6 live answers on `basis=retrieved_context`.
- **Offline path (Phase-2 Stage 0):** `evals/offline/collect.py` + `collect_invoke.py` now
  capture the API `request_id`, and `evals/offline/score.py` joins the real
  `cshub.retrieved_context` from the `aws/spans` trace by `request_id` (local-sample
  reconstruction kept only as a fallback). Re-ran the full golden set: **42/42 scored on real
  trace context**, and the 4 SRA questions that used to false-0.00 now score 0.75–1.00. This
  produced the clean Phase-2 baseline (faith 0.992 / rel 0.958 / cp 0.908 / cr 0.919). Offline
  and online eval now share the **same real-context source**. See
  `docs/phase-2/01-hybrid-retrieval.md` (Stage 0).

---

## FI-5 — Corpus growth degraded IAM retrieval (a genuine regression)

**Problem statement.** After ingesting the SRA PDF (307 IAM-tagged, IAM-heavy chunks), the
golden question `iam-config-001` ("secure way to grant an app on EC2 access to AWS services")
— which **scored ~1.0 in the Iteration-1 baseline** — now returns **"I don't have enough
information"** (0.00). Root cause: the 307 new IAM-related chunks **crowd the top-6 dense
retrieval** for IAM queries, pushing out the specific `iam-least-privilege.md` chunk that used
to answer it. This is a real retrieval regression caused by corpus growth + the dense-only
baseline having no re-ranking (and compounded by FI-3's mono-service tagging).

**Proposed solution.** This is exactly what **Phase-2 advanced RAG** targets: hybrid retrieval
+ **re-ranking** (surface the most relevant chunk regardless of how many similar ones exist),
and larger/adaptive top-K. Also mitigated by FI-3 (accurate per-chunk service tags enabling
metadata-filtered retrieval).

**Status: ⏳ PENDING (Phase 2 in progress).** Quantified against real context in Phase-2
Stage 0 (iam-config-001: answer_relevancy 0.00 / context_precision 0.30 / context_recall 0.20,
deflects) — a genuine retrieval failure, not a scorer artifact.

**Phase-2 Stage 1 (hybrid + RRF) did NOT fix it.** Hybrid retrieved the same SRA-crowded top-6
and still deflected (cp 0.30 / cr 0.15). Root cause, proven from trace spans: FI-5 is a
**semantic crowding** problem — the answering chunk (`iam-least-privilege.md`) is semantically
related but **lexically dissimilar** to the question, so full-text adds nothing and the 307 SRA
IAM-vectors still out-compete it in dense space. See `docs/phase-2/01-hybrid-retrieval.md`.

**Phase-2 Stage 2 (reranking) fixes the deflection — with caveats.**
- Rerank at `candidate_k=20` did **not** help: all 20 dense candidates were SRA chunks, so the
  answer chunk was crowded out of the pool the reranker never saw it.
- Rerank at **`candidate_k=60`** (Cohere Rerank 3.5) **stopped the deflection**: `iam-config-001`
  went from IDK / answer_relevancy 0.00 → **answering / 0.75**, and all four aggregate metrics
  improved slightly (faith 0.993 / rel 0.971 / cp 0.914 / cr 0.925).
- **Caveats:** its context precision/recall stayed low (0.20 / 0.15) — the reranker answered
  from *adjacent* SRA IAM passages, not the ideal `iam-least-privilege.md` chunk, so retrieval
  quality on that question is only **partially** fixed. And `candidate_k=60` pushed **p95 latency
  7.7s → 21.5s** (blows the 6s gate ceiling).

**Status: ◑ PARTIAL.** Deflection resolved (rerank kept enabled on the live service for now).
Remaining for the end-of-Phase-2 comparison: tune `RERANK_CANDIDATE_K` for the quality/latency
knee, add **FI-3** (per-chunk service tags → metadata-filtered retrieval, the structural fix for
the crowding), test hybrid+rerank together, and re-run after the next corpus upload. See
`docs/phase-2/02-reranking.md`.

---

## FI-6 — OpenTelemetry (OTel) instrumentation for content-carrying traces

**Problem statement.** The query Lambda has **AWS X-Ray tracing = Active**, but that is
**plain X-Ray auto-tracing** (no ADOT/OTel layer attached — verified: `Layers = null`, no
`AWS_LAMBDA_EXEC_WRAPPER`). Plain X-Ray records **timing and call structure only** — a trace
shows how long retrieve → Bedrock → guardrails took, but **not** the user question, the model
answer, or the retrieved chunks. Verified live in the console: Lambda → `cshub-dev-query` →
Monitor → X-Ray shows a service map + trace waterfalls, but no Q&A content. Consequently, eval
today can only be driven from the `CSHUB_QA` **log line**, not from the traces — and there is no
single per-conversation record that ties the question, the exact retrieved context, and the
answer together as one span tree.

**Proposed solution.** Instrument the pipeline with **OpenTelemetry GenAI tracing**:
1. Add the **AWS Distro for OpenTelemetry (ADOT)** Lambda layer (or an OTel/OpenInference/
   OpenLLMetry SDK) and set the exec wrapper so the handler is auto-traced.
2. Emit **GenAI spans** per turn that carry the **user query**, the **retrieved chunks**
   (`chunk_id` + text/snippet + score), and the **model answer** as span attributes/events —
   following the OTel GenAI semantic conventions. One trace = one full conversation turn, content
   included.
3. Export to **CloudWatch/X-Ray** (or an OTel-compatible backend). An eval job then reads spans
   and scores faithfulness/relevancy **against the real retrieved context** straight from the
   trace — the trace-based route to the **FI-4** fix and to continuous online eval.

**Why this matters.** It is the industry-standard "logs **and** trace-based eval" pattern: the
structured log gives cheap behavioural proxies, while content-carrying traces give
per-conversation, retrieved-context-grounded quality scoring and full request lineage for debug.
It also overlaps with FI-4 (both need the retrieved text captured) — OTel is the tracing-based
way to satisfy it, logging/DynamoDB the simpler way; they can coexist.

**Status: ✅ DONE (implemented + verified live).** The query Lambda `cshub-dev-query` is now
instrumented and emits content-carrying `rag.query` spans to **CloudWatch Transaction Search**
(the `aws/spans` log group). Verified a real span carrying `cshub.question`,
`cshub.request_id`, `cshub.retrieved_count`, per-chunk `cshub.chunk.N.{id,doc_id,score,text}`
(real passages, incl. the SRA PDF), `cshub.retrieved_context`, `cshub.answer`, and the
`gen_ai.*` semantic-convention attributes. `evals/online/score_online.py --from-traces` reads
these spans and scored 6/6 live answers against **real retrieved context**.

What it took (recorded so it's repeatable — this was the hard part):
1. **Code:** `query-service/common/tracing.py` (optional/non-fatal OTel helper) + spans wired
   into `run_pipeline`. Handler threads `request_id` into the span so it joins the `CSHUB_QA`
   log.
2. **Layer + wrapper:** ADOT Python layer (`aws-otel-python-amd64-ver-1-25-0:1`) with
   `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`.
3. **Sampler:** `OTEL_TRACES_SAMPLER=always_on` — without it the parent-based sampler drops
   spans when there's no sampled upstream trace (e.g. a direct invoke), so nothing reaches the
   collector.
4. **Collector config:** a minimal bundled `collector.yaml` (`otlp -> awsxray`, **no `batch`
   processor** — the reduced Lambda collector doesn't ship it; including it crashes the
   extension at init).
5. **Transaction Search (the real blocker):** current AWS-managed ADOT layers route the
   `awsxray` exporter to **CloudWatch Transaction Search** (`aws/spans`), not the classic
   `PutTraceSegments` API. The X-Ray trace-segment destination was already `CloudWatchLogs`,
   but the **CloudWatch Logs resource policy** allowing `xray.amazonaws.com` to
   `logs:PutLogEvents` on `aws/spans` was missing → every export failed with
   `InvalidRequestException` **and blocked the invocation for 35–48s**. Fixed with
   `aws logs put-resource-policy --policy-name CshubTransactionSearchXRay` (allow
   `xray.amazonaws.com` `logs:PutLogEvents` on `aws/spans:*` + `/aws/application-signals/data:*`,
   scoped by `SourceAccount`). After that, latency returned to normal (~3–8s) and spans landed.
6. **IAM:** `AWSXRayDaemonWriteAccess` added to the query Lambda role.

**Enabling Transaction Search is an account-level, one-time prerequisite** (the resource policy
+ `xray update-trace-segment-destination --destination CloudWatchLogs`). It has an indexed-span
cost profile; keep the indexing sampling rate modest for cost.

**Phase-2 note:** this trace-eval foundation is exactly what Phase 2 will lean on — every
advanced-RAG stage (hybrid/rerank/CoN/CRAG) can be A/B-measured from the spans with real
retrieved context, per conversation.

---

## How to read status
- **✅ Done** — implemented, deployed, verified.
- **⏳ Pending** — agreed direction, not yet implemented.
- **◑ Partial** — partially addressed; residual work noted.
