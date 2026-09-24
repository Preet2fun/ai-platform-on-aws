# Query Service (P2) — online, Phase 1 baseline

The online RAG pipeline behind `POST /query`. Ships the **Phase 1 baseline** (deliberately
simple, so it can be measured), with **Phase 2** advanced stages gated behind feature flags.

## Phase 1 baseline flow (what ships now)
```
input guardrails → embed query (Titan v2) → dense retrieval (pgvector top-K)
  → build cited prompt → Claude generation → output guardrails → response + citations
```
Establish baseline eval scores (faithfulness, answer relevance, context precision/recall,
latency, cost) on the golden set. Everything in Phase 2 is a measured delta vs this.

## Phase 2 flag points (added ONE at a time, A/B measured)
Flags live in `common/config.py` (env vars, all `false` in the baseline). Hook points are
marked in `app.py`:

| Flag | Stage | Where it plugs in |
|---|---|---|
| `ENABLE_HYBRID` | dense + full-text + RRF | replace `dense_search` with dense+`fulltext_search` → `reciprocal_rank_fusion` |
| `ENABLE_RERANK` | Cohere Rerank | re-order candidates before prompt build |
| `ENABLE_QUERY_TRANSFORM` | multi-query / decomposition / HyDE | expand the question before retrieval |
| `ENABLE_CHAIN_OF_NOTE` | per-chunk notes | note relevance/support before generation |
| `ENABLE_CRAG` | grade + refine/fallback | grade hits; refine or web-fallback if weak |

Turn a flag on in a test env, run the eval suite, record the delta, keep if it helps.

## Layout
```
query-service/
├── app.py                # Lambda handler + run_pipeline (baseline + Phase-2 hooks)
├── common/
│   ├── config.py         # Settings + feature flags
│   ├── retrieval.py      # pgvector dense SQL, full-text SQL, RRF (pure builders + DB access)
│   ├── bedrock.py        # embed (Titan), generate (Claude), guardrails, (Phase 2) rerank
│   └── prompt.py         # cited prompt builder + citation payload (grounding-first)
├── requirements.txt
└── tests/                # offline unit tests (mocked Bedrock/DB)
```

## Grounding & safety
- The prompt instructs the model to answer **only** from retrieved context and to say
  "I don't have enough information..." when unsupported — no guessing (critical for security).
- Answers include **citations** ([n] → source) so users can verify.
- **Guardrails** are applied on input and output; if `GUARDRAIL_ID` is empty the baseline
  still runs (guardrail step is a no-op allow) so you can wire guardrails when ready.

## Test locally (no AWS)
```bash
python -m pytest tests -q
```
Tests mock Bedrock + DB, so they validate SQL builders, RRF, prompt/citation building, and
the pipeline orchestration (happy path, input-blocked, bad-request) offline.

## API
`POST /query` (JWT-authed via Cognito) with body `{"question": "..."}` →
`{ "answer", "citations": [{n,chunk_id,doc_id,source}], "retrieved", "latency_ms", "blocked" }`.

## Phase 1 vs Phase 2 (this folder)
> Canonical run log: [`../docs/phase-1/`](../docs/phase-1/) · next phase: [`../docs/phase-2/`](../docs/phase-2/).

| | **Phase 1 (shipped + live)** | **Phase 2 (planned)** | Why / what was missing |
|---|---|---|---|
| Retrieval | Dense-only pgvector top-6 (cosine) | Hybrid+RRF → rerank → query-transform | **FI-5**: dense-only regressed as the corpus grew (an IAM golden Q that scored ~1.0 now deflects — the answering chunk got crowded out of top-6). Needs hybrid recall + reranking. |
| Generation | Claude Sonnet 4.5, cited, grounding-first | Chain-of-Note, CRAG | Better faithfulness / honest "I don't know" and out-of-corpus fallback. |
| Tracing/eval | **OTel GenAI content spans (FI-6)** → trace-grounded online eval | Automated sampler + drift alarms | Phase-1 online eval was a manual run; the trace foundation is now live for Phase 2 to A/B each stage against real retrieved context. |

**Phase-1 status: this service is deployed and live** (`cshub-dev-query`), all Phase-2 flags OFF.
Strategy detail: [`../docs/phase-1/05-chunking-and-retrieval.md`](../docs/phase-1/05-chunking-and-retrieval.md).
Findings driving Phase 2: [`../docs/phase-1/FUTURE-IMPROVEMENTS.md`](../docs/phase-1/FUTURE-IMPROVEMENTS.md) (FI-5, FI-6).

## Notes / caveats
- **Deployed and live** as `cshub-dev-query` (Phase 1). Instrumented with OpenTelemetry GenAI
  tracing (FI-6): layer `aws-otel-python-amd64-ver-1-25-0`, exec wrapper `/opt/otel-instrument`,
  bundled `collector.yaml` (otlp→awsxray), `OTEL_TRACES_SAMPLER=always_on`. Content spans land
  in CloudWatch Transaction Search (`aws/spans`).
- Lambda code is packaged/zipped with `common/` + `psycopg` (+ `collector.yaml`) and uploaded to the code bucket.
- The CORS `AllowOrigins:*`, Cognito callback URLs, and WAF rate limits are placeholders —
  tighten to the real UI domain in P4.
- Bedrock model id defaults to a Claude Sonnet inference profile; confirm the exact id/profile
  available in the account before deploy.
