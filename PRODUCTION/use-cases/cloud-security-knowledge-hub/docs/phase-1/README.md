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
