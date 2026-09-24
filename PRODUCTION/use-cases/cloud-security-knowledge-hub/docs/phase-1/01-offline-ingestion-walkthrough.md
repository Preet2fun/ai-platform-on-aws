# Phase 1 · Stage A — Offline Ingestion Walkthrough

> Step-by-step trace of the **offline ingestion pipeline** run live during Phase 1, with AWS
> observability at each step. Pipeline: `S3 raw → EventBridge → Step Functions → Extract →
> Clean → Chunk → EmbedUpsert → Manifest → Aurora (pgvector)`.
>
> **Document ingested this run:** `aws-security-reference-architecture-v4.pdf` (AWS Security
> Reference Architecture, native text PDF, 1.6 MB). A second PDF (`kms-dg.pdf`, KMS Developer
> Guide, 11 MB) was attempted and surfaced a scaling boundary — see §A.10 + FI-2.

## A.0 — Starting point (BEFORE)
18 docs / 30 chunks / 17 services / 0% empty · 0% null-embedding (see `README.md`).

## A.1 — Upload → S3 raw
Uploaded to `s3://cshub-dev-raw-001961766007/docs/aws-security-reference-architecture-v4.pdf`
(1,607,128 bytes). The `Object Created` event is what drives everything downstream.

> **Real gotcha observed:** the first uploads used the same destination key
> (`docs/yourfile.pdf`), so the second overwrote the first and both fired ingestions on one
> object. Fix: upload each file under its own key (`docs/<real-name>.pdf`). The stray
> `yourfile.pdf` (raw object + 307 Aurora chunks) was cleaned up afterward. Lesson: the S3 key
> **is** the document identity and the metadata classifier's primary signal — name it correctly.

## A.2 — EventBridge → Step Functions
S3 `Object Created` → EventBridge rule `cshub-dev-ingest-on-upload` → `StartExecution` on the
`cshub-dev-ingestion` state machine (one execution per object). Verified via
`stepfunctions list-executions` (input `{bucket, object.key}`).

## A.3 — Step 1: Extract
- Path taken: **native `pypdf`** (the PDF has an embedded text layer; Textract fallback not
  needed — it only triggers when extracted text < 100 chars).
- **~246,929 characters** extracted → written to
  `s3://cshub-dev-processed-001961766007/text/docs/aws-security-reference-architecture-v4.pdf.txt`.

## A.4 — Step 2: Clean
Normalized whitespace / de-hyphenation while preserving paragraph structure → `clean/…txt`.

## A.5 — Step 3: Chunk + metadata
- **307 chunks** produced (structure-aware), avg **980 chars/chunk**.
- Metadata classification: the SRA filename has **no service keyword**, so `infer_service` fell
  back to body-frequency and tagged the doc `iam` (IAM is the most-mentioned term across this
  multi-service reference). See **FI-3** — a large multi-service doc needs per-chunk service
  tagging, not one per-doc tag.

## A.6 — Step 4: EmbedUpsert
- Titan Text Embeddings v2, **1024-dim**, one call per chunk.
- **First attempt FAILED** with `ThrottlingException` (307 rapid Titan calls burst past
  on-demand TPS). → Fixed with exponential backoff + pacing (**FI-1**), redeployed the Lambda.
- **Second attempt SUCCEEDED**: all **307 chunks embedded and upserted** into Aurora.
- Note: EmbedUpsert commits once at the end of the loop, so a failed/stopped run commits
  **nothing** (all-or-nothing) — which is why the abandoned KMS run left no partial rows.

## A.7 — Step 5: Manifest (integrity + quality eval)
- **Integrity (gates):** `chunk_count 307 == upserted 307 == db_count 307` → **checks_passed = true**.
- **Quality (advisory, → `CSHub/Ingestion`):** avg_chunk_chars **980.4**, empty **0.0**,
  null_embedding **0.0**, duplicate **0.0**, oversized **0.0** → healthy.

## A.8 — Observability check
- **Step Functions**: execution history shows Extract→Clean→Chunk→EmbedUpsert→Manifest; the
  failed attempt's `ExecutionFailed` event carried the `ThrottlingException` + stack trace
  pointing at `embed_upsert.py:34 → embed.py:26 invoke_model` — this is how we root-caused FI-1.
- **CloudWatch**: per-Lambda log groups `/aws/lambda/cshub-dev-ingest-*`; ingestion-quality
  metrics in namespace `CSHub/Ingestion`; alarm `cshub-dev-ingestion-quality` = **OK**.

## A.9 — AFTER snapshot + delta
| Metric | BEFORE | AFTER | Δ |
|---|---|---|---|
| Documents | 18 | **19** | +1 (SRA) |
| Chunks | 30 | **337** | +307 (SRA) |
| Services covered | 17 | 17 | — |
| Avg chunk chars | 869.3 | 970.5 | +101 (PDF chunks larger) |
| Null-embedding rate | 0.0 | 0.0 | — |

Service coverage after: `iam 309` (307 from the SRA — see FI-3), then the per-topic md docs
(rds 3, and 1–2 each for the rest).

## A.10 — Findings (all logged in `FUTURE-IMPROVEMENTS.md`)
- **FI-1 (✅ Done):** embedding throttling on large docs → fixed with backoff + pacing; **proven
  live** (SRA failed before, succeeded after).
- **FI-2 (⏳ Pending):** the KMS Dev Guide → **2,213 chunks**, which cannot finish inside the
  EmbedUpsert Lambda's 900s timeout (sequential per-chunk embedding). This is the case the
  architecture reserved **Fargate** for (deferred in P1). The KMS run was stopped; it committed
  no rows. Large multi-hundred-page PDFs need the Fargate/batching path.
- **FI-3 (⏳ Pending):** per-doc `service` tag mislabels a large multi-service doc (SRA → all
  `iam`). Needs per-chunk service classification.

## Net result
**Offline ingestion for an appropriately-sized PDF works end-to-end and is fully observable.**
Corpus is clean at **19 docs / 337 chunks**, 0% null/empty, integrity + quality both green. The
SRA is our successfully-ingested large-PDF evidence; KMS is the documented scaling boundary.
