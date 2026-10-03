# Phase 1 — Run Log & Reports

This folder documents the **Phase 1** run of the Cloud Security Knowledge Hub end-to-end:
offline ingestion, offline (golden-set) evaluation, live online testing, observability, and a
conclusion. Each stage is walked through step-by-step with real numbers and live AWS evidence.

## Contents (in run order)

| Doc | Stage | What it covers |
|---|---|---|
| `01-offline-ingestion-walkthrough.md` | A | Every step of the offline ingestion pipeline for the newly uploaded docs, with observability |
| `02-offline-eval.md` | B | The golden-set offline eval (pre-release quality gate) on the current corpus |
| `03-online-testing.md` | C | Live UI testing + online eval measured from production traces/logs |
| `04-observability.md` | D | Cross-cutting observability: metric inventory, live sample values, console navigation |
| `05-chunking-and-retrieval.md` | ref | Chunking strategy + retrieval strategy (baseline params + Phase-2 hooks) |
| `FUTURE-IMPROVEMENTS.md` | all | Findings register (FI-1…FI-6): problem → solution → status |
| `PHASE-1-CONCLUSION.md` | F | Results summary, headline finding, findings/gaps, handoff to Phase 2 |

**Start here:** read `PHASE-1-CONCLUSION.md` for the summary, then `01→04` for the detail.

Related, elsewhere in the repo:
- AI-SDLC & eval plan (with §9 *as-run reality*): `../../AI-SDLC-AND-EVALS.md`
- Baseline offline eval report: `../../evals/reports/ITERATION-1-BASELINE.md`
- Ingestion quality report: `../../evals/reports/INGESTION-QUALITY-REPORT.md`
- Architecture diagrams: `../../diagrams/04-phase1-*`
- Online-eval design: `../../evals/ONLINE-EVAL-PLAN.md`
- Next phase: `../phase-2/README.md`

## Environment (this run)
- Account `001961766007` · region `us-east-1` · profile `agentcore`
- 8 CloudFormation stacks (`cshub-dev-*`) · tag `usecase=rag-prod`
- UI: `https://d1s8aphl5ns4nb.cloudfront.net` · API: `https://6cg5i5593i.execute-api.us-east-1.amazonaws.com/query`

## BEFORE snapshot (corpus state prior to Phase-1 PDF uploads)
Captured 2026-09-23, before any new documents were added:

| Metric | Value |
|---|---|
| Documents | 18 |
| Chunks | 30 |
| Avg chunk chars | 869.3 |
| Services covered | 17 |
| Empty-chunk rate | 0.0 |
| Null-embedding rate | 0.0 |

Service coverage: `rds 3 · cognito/s3/lambda/apigateway/iam/vpc/eks/dynamodb/kms/secretsmanager/ec2 = 2 each · guardduty/route53/cloudtrail/sns/ebs = 1 each`.

The offline-ingestion walkthrough (`01-...`) shows the **delta** from this baseline after the
new PDFs are ingested.

## AFTER snapshot (corpus state at end of Phase 1)
After ingesting the AWS Security Reference Architecture PDF and cleaning up the partial
KMS/duplicate artifacts:

| Metric | Before | After |
|---|---|---|
| Documents | 18 | **19** |
| Chunks | 30 | **337** |
| Services covered | 17 | 17 |
| Null-embedding rate | 0.0 | 0.0 |
| Empty-chunk rate | 0.0 | 0.0 |

> Note: the CloudWatch `corpus_*` gauges may read higher (20 docs / 644 chunks) — a **gauge
> drift** because those metrics only refresh when an ingestion pipeline runs, and the cleanup
> was out-of-band. The **337 / 19** figures above are the true post-cleanup state. See
> `04-observability.md` §D.1.

## ENLARGED corpus (final Phase-1-vs-Phase-2 re-test)
Before the final head-to-head comparison, the corpus was **deliberately enlarged** so the
Phase-2 features are tested against real breadth (multiple docs per service, multi-topic PDFs,
and near-synonym filenames) rather than a thin small-corpus. This snapshot is the shared input
for **both** the Phase-1 baseline and the Phase-2 all-on runs — ingestion is identical for both
phases; only the *query-time* flags differ.

| Metric | Phase-1 end | Enlarged (this re-test) |
|---|---|---|
| Documents | 19 | **30** (+11 new PDFs) |
| Chunks | 337 | **534** |
| Services covered | 17 | **17** |
| Null-embedding rate | 0.0 | **0.0** |
| Empty-chunk rate | 0.0 | **0.0** |

**What was added (11 PDFs):** `security-best-practices`, `bucket-encryption`, `data-protection`,
`microvms-security`, `data-protection-encryption`, `data-protection-summary`,
`security-iam-service-with-iam`, `overview-encryption`, `rds-ssl-tls-encrypt-connection`,
`eks-security-best-practices`, `eks-pod-security`. They skew the corpus toward
**encryption / data-protection / EKS / RDS-TLS**, which is where the new golden pairs focus.

**FI-3 applied to the whole corpus (per-chunk service tagging).** After deploying the FI-3 fix,
all 19 pre-existing docs were **re-ingested in place** (same S3 keys → same `doc_id` → same
`chunk_id`s → `ON CONFLICT DO UPDATE`, so no duplication; corpus stayed at 534). This re-tagged
every chunk with a service classified from *its own text* instead of one clobbered per-doc tag.

Proof (from the chunk handler's ground-truth JSONL in the processed bucket, pre-DB-upsert):
- **SRA** (`aws-security-reference-architecture-v4.pdf`) — its 306 chunks now span **19 distinct
  services** (`iam 135 · s3 28 · ec2 25 · vpc 24 · config 15 · securityhub 14 · kms 12 · waf 12
  · guardduty 11 · cloudtrail 8 · route53 6 · secretsmanager 4 · cognito 4 · lambda 3 · ebs 2 ·
  eks 1 · cloudwatch 1 · apigateway 1 · rds 1`). Previously **all 307 were clobbered to `iam`** —
  the exact cause of the FI-5 metadata-filter failure.
- `data-protection.pdf` — correctly multi-service (`ec2, ebs, iam, cloudtrail, vpc`).
- `security-iam-service-with-iam.pdf` — correctly stays **all IAM** (genuinely single-service).
- `iam-least-privilege.md` (the FI-5 target doc) — correctly `iam`.

**Duplicate check across near-synonym docs:** the `data-protection*` / `*-encryption` family
(57 chunks total) has **zero byte-identical chunks shared across docs** — similar filenames but
genuinely distinct content, so the enlargement adds real coverage, not accidental duplicates.

> The FI-3 metadata filter is **query-time gated** (`ENABLE_METADATA_FILTER`, default off). The
> per-chunk tags above are a shared data-quality improvement; whether a query *uses* them to
> filter is a Phase-2-only behavior. The Phase-1 dense path is byte-identical with the flag off.
