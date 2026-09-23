# Cloud Security Knowledge Hub — Implementation & Deployment Plan

> **Purpose:** a phase-wise, executable runbook to build and deploy the Hub on AWS account
> `001961766007` (`us-east-1`). Unlike `PLAN.md` (the design) this is the **do-list**: what to
> check, what to change, what to deploy, and how to verify each step before moving on.
>
> **Important context:** most of the code already exists (`infra/`, `ingestion/`,
> `query-service/`, `ui/`, `evals/`, CI workflow). So this is largely a **validate → fix known
> gaps → deploy → verify** effort, not a greenfield build. Every phase below marks whether the
> artifact is ✅ already written or 🔧 needs work.

---

## 0. Prerequisite validation (done — results captured)

Checked live against the account with the `agentcore` CLI profile on **2026-09-11**:

| Prerequisite | Required | Live status | Action |
|---|---|---|---|
| AWS account / region | `001961766007` / `us-east-1` | ✅ confirmed (`agentcore` profile, user `pratik.patel@motadata.com`) | Use `AWS_PROFILE=agentcore AWS_REGION=us-east-1`. |
| Bedrock — Titan Embeddings v2 | `amazon.titan-embed-text-v2:0` | ✅ available | none |
| Bedrock — Claude Sonnet (generation) | a Sonnet model | ✅ `anthropic.claude-sonnet-4-5-20250929-v1:0` (and `-4`) available | Pin the exact model id in `query-service` config. |
| Bedrock — Cohere Rerank (Phase 2) | a rerank model | ✅ `cohere.rerank-v3-5:0` available | Use in P3 (2.2). |
| Bedrock **model access enabled** for the above | access granted in console | ⚠️ **verify** (list ≠ access) | Confirm in Bedrock → Model access; request if any show "Available to request". |
| GitHub OIDC provider | may already exist | ✅ **none exists** | Keep `CreateOidcProvider=true`. |
| Existing `cshub-*` stacks | should be none | ✅ none deployed | Clean slate. |
| **Aurora PostgreSQL engine version** | `params/dev.json` says `16.4` | 🔴 **`16.4` standard NOT available** (only `16.4-limitless`) | **Change `EngineVersion` to `16.8`** (valid: 16.8/16.9/16.10/16.11/16.13/16.14). |
| Tooling | awscli v2, jq, bash | ✅ awscli 2.36, jq present | none |
| Docker (for Lambda/Fargate image builds) | needed P1/P2 build | ⚠️ verify locally | `docker version` before P1. |

### 0.1 Blockers to clear before P0 (must-fix) — ✅ CLEARED 2026-09-11

1. ✅ **Aurora version fixed** — `infra/params/dev.json` `EngineVersion` set to `16.8`
   (confirmed `available` in us-east-1, family `aurora-postgresql16`).
2. ✅ **GitHub org set** — `GitHubOrg=Preet2fun`, `GitHubRepo=ai-platform-on-aws`,
   `GitHubRef=refs/heads/main` (repo: https://github.com/Preet2fun/ai-platform-on-aws).
3. ✅ **Bedrock model access** — the Bedrock *Model access* page is **retired**; serverless
   foundation models are auto-enabled on first invocation. No manual grant needed.
   *(Caveat: first-time Anthropic use may require a one-time use-case submission; surfaces only
   as an access error on invoke, handled if it occurs.)*

### 0.2 Known code gaps to be aware of (documented, not blockers for P0 skeleton)

- ✅ **pgvector bootstrap now runs for real** (`02-pgvector-bootstrap.yaml`, done 2026-09-11).
  The inline handler installs `pg8000` into `/tmp` at runtime, connects to Aurora, and executes
  the idempotent DDL (enable `vector`; create `documents`/`chunks`; HNSW + GIN indexes; `tsv`
  trigger). No CI/layer/S3 packaging needed — deploys via `deploy.sh`. First invoke adds ~10–20s
  for the one-time pip install (Lambda timeout raised to 300s).
- **CI/CD deploy role is broad** (`PowerUserAccess` + IAM) for bootstrap convenience — tighten to
  least-privilege in P5.
- **S3 buckets are `Retain`, Aurora is `Snapshot`** on stack delete — data survives a teardown by
  design; clean up manually if you truly want it gone.

---

## Phase map (at a glance)

| Phase | Goal | Main artifacts | Deploy target |
|---|---|---|---|
| **P0** | Foundation: network, data, pgvector schema, CI/CD role | `00`,`01`,`02-pgvector`,`06` | 4 CFN stacks |
| **P1** | Ingestion: index a first corpus (text+PDF) | `02-ingestion.yaml`, `ingestion/` | Step Functions + Lambda/Fargate |
| **P2** | Baseline online query + UI | `03-query-service.yaml`, `04-edge-ui.yaml`, `query-service/`, `ui/` | Lambda + API GW + CloudFront |
| **P3** | Advanced RAG, one stage at a time (measured) | `query-service/` flags | same, feature-flagged |
| **P4** | Golden set + continuous eval + observability | `evals/`, `05-observability.yaml`, CI gate | CloudWatch + GH Actions |
| **P5** | Hardening + (later) video ingestion | least-privilege, cost, Transcribe branch | — |

Each phase: **validate inputs → apply fixes → deploy → verify exit criteria → stop.** Do not start a
phase until the previous phase's exit criteria pass.

---

## P0 — Foundation

**Status:** infra templates ✅ written · params 🔧 need 2 edits · pgvector schema 🔧 needs packaging.

### Steps
1. **Edit params** (`infra/params/dev.json`): set `EngineVersion=16.8`, set real `GitHubOrg`.
2. **Auth**: `export AWS_PROFILE=agentcore AWS_REGION=us-east-1` and confirm
   `aws sts get-caller-identity` → account `001961766007`.
3. **Validate templates** (no-cost sanity):
   ```bash
   cd infra
   for t in 00-network 01-data-stores 02-pgvector-bootstrap 06-cicd; do
     aws cloudformation validate-template --template-body file://$t.yaml >/dev/null && echo "ok $t";
   done
   ```
4. **Deploy P0 stacks** (network → data → pgvector → cicd):
   ```bash
   AWS_PROFILE=agentcore AWS_REGION=us-east-1 ./deploy.sh dev
   ```
   *(If not wiring GitHub yet, deploy stacks 1–3 individually and defer `06-cicd`.)*
5. **pgvector schema — created automatically.** The `cshub-dev-pgvector` stack's custom-resource
   Lambda installs `pg8000` at runtime and runs the DDL on deploy (no manual step). After the
   stack completes, check its CloudWatch logs for `pgvector bootstrap applied N DDL statements`.
   If it ever fails (e.g. PyPI unreachable), the stack surfaces the error — re-run after fixing egress.
6. **Verify** (exit criteria):
   ```bash
   aws cloudformation describe-stacks --stack-name cshub-dev-data \
     --query "Stacks[0].Outputs" --output table          # note DbEndpoint, DbSecretArn, buckets
   # confirm schema exists:
   #   \dx        → 'vector' listed
   #   \dt        → chunk/doc tables present
   ```

**Exit criteria:** 4 stacks `CREATE_COMPLETE`; Aurora reachable; **`vector` extension + hybrid schema
actually created** (not the no-op); exports (`VpcId`, `DbEndpoint`, `DbSecretArn`, `RawBucket`,
`ProcessedBucket`, `ArtifactsBucket`, `KmsKeyArn`, `DeployRoleArn`) present.

> ✅ **P0 DEPLOYED & VERIFIED 2026-09-17** (account `001961766007`, us-east-1).
> - Stacks `CREATE_COMPLETE`: `cshub-dev-network`, `cshub-dev-data`, `cshub-dev-pgvector`, `cshub-dev-cicd`.
> - Aurora PostgreSQL **16.8** Serverless v2 `available`; endpoint
>   `cshub-dev-data-dbcluster-z5czsyjhwiyb.cluster-cc3w0mm4u6cm.us-east-1.rds.amazonaws.com`.
> - pgvector schema created — bootstrap Lambda logged **"applied 8 DDL statements"** (vector ext,
>   `documents`, `chunks`, HNSW + GIN indexes, tsv trigger).
> - CI/CD deploy role: `arn:aws:iam::001961766007:role/cshub-dev-gha-deploy`; GitHub OIDC provider created.
> - Buckets: `cshub-dev-{raw,processed,artifacts}-001961766007`; KMS `alias/cshub-dev`.
> - **Tagging:** 32 resources carry `usecase=rag-prod` (+ `project=cshub`, `env=dev`), verified via
>   Resource Groups Tagging API.
> - Known deploy note: the pgvector bootstrap needed one fix — install pg8000 then
>   `importlib.invalidate_caches()` before import (first attempt failed on stale import cache).

---

## P1 — Ingestion (text + PDF)

**Status:** `ingestion/` code ✅ (handlers: extract/clean/chunk/embed_upsert/manifest, common libs,
tests, Dockerfile, `dry_run.py`) · `02-ingestion.yaml` ✅.

### Steps
1. **Local sanity** (no AWS): run unit tests and the dry run.
   ```bash
   cd ingestion && pip install -r requirements.txt
   pytest -q                       # chunking / metadata / db+clean tests
   python dry_run.py sample.pdf    # exercises extract→clean→chunk→metadata locally
   ```
2. **Build the heavy-embed image** (Fargate path) and push to ECR (repo created by the stack or
   pre-create one). Confirm `docker version` first.
3. **Deploy ingestion stack:**
   ```bash
   aws cloudformation deploy --stack-name cshub-dev-ingestion \
     --template-file infra/02-ingestion.yaml --capabilities CAPABILITY_NAMED_IAM \
     --parameter-overrides ProjectName=cshub EnvName=dev \
     --tags project=cshub env=dev usecase=rag-prod   # keep the tag on every stack
   ```
4. **Seed a small corpus**: upload 5–10 AWS security docs (text/PDF) to the **raw** S3 bucket →
   EventBridge triggers Step Functions.
5. **Verify**: Step Functions execution succeeds end-to-end; rows land in Aurora with non-null
   `vector(1024)` embeddings + populated `tsvector`; ingestion **manifest** written to artifacts
   bucket; embedding failure rate ≈ 0.

**Exit criteria:** first corpus searchable in Aurora; manifest passes; a manual
`SELECT` with `<->` (cosine) returns sensible nearest chunks.

> ✅ **P1 DEPLOYED & VERIFIED 2026-09-17** (account `001961766007`, us-east-1).
> - Local: 13/13 unit tests pass; `dry_run.py` produced correct chunks/metadata.
> - Packaged the 5 handler zips with `ingestion/package.sh` — deps cross-built for the Lambda
>   target (linux / py3.12 / x86_64) incl. `psycopg` native `.so`; uploaded to
>   `s3://cshub-dev-artifacts-001961766007/ingestion/`. `LambdaCodeBucket=cshub-dev-artifacts-001961766007`.
> - Stack `cshub-dev-ingestion` `CREATE_COMPLETE`: 5 Lambdas (py3.12), Step Functions
>   `cshub-dev-ingestion`, EventBridge rule `cshub-dev-ingest-on-upload` (ENABLED), ECS cluster +
>   heavy-embed task def. All tagged `usecase=rag-prod`.
> - Seeded 3 AWS-security docs (S3 config, EC2 IMDS SSRF, RDS public exposure) → 3 Step Functions
>   executions **SUCCEEDED**. Manifests show `chunk_count == upserted == db_count == 2`,
>   `checks_passed: true` for each → **6 chunks with Titan v2 embeddings live in Aurora**.
> - Fargate ECR image intentionally **not built** (heavy-doc path only; not needed for this corpus).
> - Seed docs kept in `ingestion/samples/`; packaging build dir `ingestion/.build/` is local-only.

---

## P2 — Baseline online query + UI

**Status:** `query-service/` code ✅ (app + common: bedrock/config/prompt/retrieval, tests) ·
`03-query-service.yaml` ✅ · `ui/` ✅ · `04-edge-ui.yaml` ✅.

### Steps
1. **Pin models** in `query-service/common/config.py`: embeddings `amazon.titan-embed-text-v2:0`,
   generation `anthropic.claude-sonnet-4-5-20250929-v1:0`. Confirm the **Bedrock Guardrail** id/params
   the template expects (create a guardrail if the stack references one by id).
2. **Local tests:** `cd query-service && pip install -r requirements.txt && pytest -q`
   (retrieval + prompt/pipeline tests).
3. **Deploy query service** (`03-query-service.yaml`): API Gateway HTTP API + query Lambda + **new
   Cognito user pool** + WAF. Then **deploy edge/UI** (`04-edge-ui.yaml`): CloudFront + S3 site.
4. **Wire the UI**: copy `ui/config.js.template` → `config.js`, fill `userPoolId`,
   `userPoolClientId`, `apiEndpoint` (from `03` outputs), `cognitoDomain`, and `redirectUri`
   (CloudFront URL from `04`). Sync `ui/` to the site bucket; invalidate CloudFront.
5. **Cognito callback/logout URLs**: replace the `https://localhost/...` placeholders on the user-pool
   client with the real CloudFront URL.
6. **Verify (smoke)**: sign in via Hosted UI → ask "How do I securely configure an S3 bucket?" →
   get a **cited** answer from the seeded corpus; input/output guardrails active; X-Ray trace shows
   the stages; CloudWatch logs clean.

**Exit criteria:** end-to-end Q&A works through the browser with citations and guardrails; **baseline
eval scores recorded** (see P4 harness) — this is the reference point for all P3 deltas.

> ✅ **P2 DEPLOYED & VERIFIED 2026-09-21** (account `001961766007`, us-east-1).
> - query-service: 9/9 unit tests pass. Packaged `query.zip` (app.py + common/ + psycopg native
>   .so) via `query-service/package.sh` → `s3://cshub-dev-artifacts-001961766007/query-service/`.
> - Bedrock Guardrail `cshub-dev-guardrail` (id `lllxsq3sufc1`, v1): content filters +
>   prompt-injection on input + AWS-key/password PII block on output. Wired into the query Lambda.
> - Stack `cshub-dev-query-service` `CREATE_COMPLETE`: Cognito pool `us-east-1_1o9PFMMuq` + web
>   client `6jp3skq940sk147nvejeml3r97`, HTTP API `https://6cg5i5593i.execute-api.us-east-1.amazonaws.com/query`,
>   in-VPC query Lambda, stage throttling.
> - Stack `cshub-dev-edge-ui` `CREATE_COMPLETE`: CloudFront **https://d1s8aphl5ns4nb.cloudfront.net**
>   (dist `E277118XW0GMRN`) over private S3 site bucket `cshub-dev-ui-001961766007`.
> - Cognito Hosted UI domain `https://cshub-dev-001961766007.auth.us-east-1.amazoncognito.com`;
>   callback/logout point at CloudFront; `ui/config.js` rendered + synced; CloudFront invalidated.
> - **Smoke test passed:** in-corpus S3 question → grounded cited answer (6 passages, ~7s);
>   out-of-corpus → correct "I don't have enough information"; no-auth → 401.
> - **Two template bugs found & fixed (committed to templates):**
>   1. WAF cannot attach to an API Gateway v2 HTTP API — removed the `WebACL`/association;
>      API protected by stage throttling now + CloudFront WAF later (P5).
>   2. Claude Sonnet 4.5 requires an **inference profile** for on-demand invoke — changed
>      `GenerationModelId` default to `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (template + code).
> - Smoke-test artifacts cleaned up: app client reverted to SRP-only; test user deleted.
> - ⏭️ Baseline eval scores are recorded in **P4** (the eval harness + golden set are built there).

---

## P3 — Advanced RAG (add ONE stage at a time, measure each)

**Status:** baseline retrieval ✅; advanced stages 🔧 added behind flags in `query-service/`.

For each stage: enable flag in dev → run RAGAS suite on the golden set → record quality delta +
latency/cost delta → **keep only if the gain justifies the cost** → document the decision.

| Order | Stage | Should improve | Metric that must move |
|---|---|---|---|
| 3.1 | Hybrid retrieval (pgvector + full-text) + **RRF** | recall on exact terms (service/CVE) | Context Recall, Hit Rate@K |
| 3.2 | **Cohere Rerank** (`cohere.rerank-v3-5:0`) | precision (right chunk first) | Context Precision, MRR/NDCG |
| 3.3 | Query transformation (multi-query → decomposition → HyDE) | recall on ambiguous/multi-hop | Context Recall (hard subset) |
| 3.4 | Chain-of-Note | groundedness; fewer hallucinations | Faithfulness, hallucination rate |
| 3.5 | CRAG grade (+ optional web fallback) | robustness on weak/stale retrieval | Correctness (out-of-corpus) |

**Exit criteria:** an evidence table of per-stage deltas; only justified stages remain enabled.

---

## P4 — Golden set + continuous eval + observability

**Status:** `evals/` harness ✅ (`run_eval.py`, `gate.py`, `report.py`, `thresholds.json`,
`golden/` schema+seed+generator) · CI `.github/workflows/eval-gate.yml` ✅ ·
`05-observability.yaml` ✅.

### Steps
1. **Build the golden set** (~100–200 pairs): use `evals/golden/generate_golden.py` on the loaded
   corpus (LLM-generated, human-reviewed) across config/attack/prevention question types; commit to
   `evals/golden/`.
2. **Run the harness**: `cd evals && pip install -r requirements.txt && python run_eval.py`; then
   `gate.py` (floors + max-regression + system ceilings) and `report.py` (baseline vs candidate).
3. **Deploy observability** (`05-observability.yaml`): CloudWatch dashboards/alarms, X-Ray, log
   groups, Bedrock invocation logging, budget alarm.
4. **Wire CI gate**: ensure `06-cicd` OIDC role is deployed and the repo secrets/vars are set so
   `eval-gate.yml` can assume the role and fail PRs on regression.

**Exit criteria:** regression gate live in CI; dashboards populated; budget alarm active.

> ✅ **P4 EXECUTED & ITERATION-1 BASELINE RECORDED 2026-09-22** (account `001961766007`, us-east-1).
> - **Corpus** expanded to 16 AWS-security docs / 27 chunks (all Step Functions runs SUCCEEDED).
> - **Observability** deployed (`cshub-dev-observability`): dashboard `cshub-dev-hub`, alarms
>   (query errors, p95 latency, API 5xx), SNS alerts (email needs confirm-click), $300 budget.
> - **Golden set**: 38 human-reviewed pairs (`evals/golden/golden.jsonl`), balanced across
>   config/attack/prevention and all 16 services.
> - **Baseline eval (Advanced RAG OFF)** — offline accuracy + online performance:
>   faithfulness **0.984**, answer_relevancy **0.976**, context_precision **0.940**,
>   context_recall **0.947**; p50 5,752ms / p95 **7,046ms** / avg 5,611ms; 0 errors.
>   Gate: accuracy PASSES all floors; p95 latency FAILS the 6,000ms ceiling (generation-time,
>   a known baseline characteristic — quality is unaffected).
> - **Key finding + fix:** the Bedrock Guardrail MISCONDUCT filter was false-blocking
>   legitimate "how does X attack work" questions (all 12 attack Qs scored 0.00). Created
>   **guardrail v2** (MISCONDUCT/VIOLENCE input→NONE, kept PROMPT_ATTACK + PII output block);
>   verified attack Qs pass and prompt-injection is still blocked. Query-service pinned to v2
>   (template default updated).
> - **New eval tooling:** `evals/collect_online.py` (live-API collection) + `evals/score_offline.py`
>   (Bedrock LLM-as-judge, since local Python 3.8 < RAGAS's 3.9 requirement). Scores emitted to
>   CloudWatch `CSHub/Eval`. Report: **`evals/reports/ITERATION-1-BASELINE.md`**.
> - Cleanup: eval Cognito user deleted, app client reverted to SRP-only.
> - ⏭️ **CI regression gate** (GitHub Actions assuming the OIDC role) is the one remaining P4
>   sub-item; deferred until we run in CI. Iteration-2 (Advanced RAG / P3) will re-run this exact
>   harness and record per-stage deltas vs this baseline.

---

## P5 — Hardening + (later) video ingestion

- **Least-privilege**: replace `PowerUserAccess` on the CI/CD role with a scoped policy (only the
  services these stacks touch), per `AI-PLATFORM/guardrails`.
- **Cost tuning**: keep Aurora `MinAcu=0.5`; consider 1 unit of Lambda provisioned concurrency only
  if cold-start hurts UX; set CloudWatch log retention.
- **Security review**: WAF rules, CORS tightened to the CloudFront origin (template note in `ui/README`),
  CSP header, KMS CMK coverage.
- **Video (deferred)**: add an Amazon Transcribe branch (video/audio → transcript → same chunk/embed
  path) to the ingestion Step Functions.

---

## Quick reference — deploy order & stack names

```
P0: cshub-dev-network → cshub-dev-data → cshub-dev-pgvector → cshub-dev-cicd
P1: cshub-dev-ingestion
P2: cshub-dev-query-service → cshub-dev-edge-ui
P4: cshub-dev-observability
```

## Immediate next actions (before any deploy)
1. `infra/params/dev.json`: `EngineVersion` `16.4` → **`16.8`**; set real **`GitHubOrg`**.
2. Confirm **Bedrock model access** (console) for Titan v2, Claude Sonnet, Cohere Rerank.
3. Decide the **pgvector bootstrap approach** (package driver layer vs one-time manual DDL).
4. Then run P0 step 3 (validate) → step 4 (deploy).

> When you're ready, say the word and we'll start P0: I'll make the two `params/dev.json` edits,
> validate the templates, and walk the deploy stack-by-stack, verifying each exit criterion.
