# Ingestion Quality Eval + Continuous Monitoring

Quality evaluation for the **offline (ingestion) pipeline** — distinct from the per-doc
**integrity** check that already existed. Integrity asks *"did every chunk make it into Aurora
intact?"*; quality asks *"is the ingested corpus actually good for retrieval?"*

## Where the code lives (and why it's not a standalone script here)

Aurora is in a **private VPC** (unreachable from a laptop or from GitHub Actions without VPC
wiring). So the ingestion-quality metrics are computed **in-VPC**, inside the ingestion
pipeline itself, by the **Manifest Lambda** — which already connects to Aurora on every run:

- **`../../ingestion/common/ingestion_metrics.py`** — pure SQL builders + metric derivations
  (unit-tested in `../../ingestion/tests/test_ingestion_metrics.py`).
- **`../../ingestion/handlers/manifest.py`** — runs the metrics after the integrity check and
  emits them to CloudWatch (see below). Quality is **advisory** (logged + alarmed); integrity
  still **gates** the run.

This folder holds the docs/spec; the executable code sits with the pipeline it measures.

## Metrics (per document + corpus-wide)

Emitted to CloudWatch namespace **`CSHub/Ingestion`** on every ingestion run:

| Metric | Meaning | Why it matters |
|---|---|---|
| `chunk_count` / `avg_chunk_chars` | per-doc size | too-small/large chunks hurt retrieval |
| `empty_chunk_rate` | fraction of blank chunks | extraction/chunking failure |
| `undersized_chunk_rate` / `oversized_chunk_rate` | outside `[200, 2000]` chars | retrieval quality |
| `null_embedding_rate` | chunks with no vector | embedding step failed |
| `duplicate_chunk_rate` | exact-duplicate texts in a doc | index bloat / skew |
| `corpus_docs` / `corpus_chunks` / `corpus_chunks_per_doc` | corpus size | coverage/growth |
| `corpus_avg_chunk_chars` | corpus size profile | drift over time |
| `services_covered` | distinct AWS services in the corpus | breadth |

Full per-doc + corpus detail is also written to the ingestion **manifest** JSON in the
artifacts bucket (`manifests/<doc_id>.json` → `quality` + `corpus` fields).

## Continuous monitoring

- **Dashboard** (`cshub-dev-hub`): two ingestion-quality widgets — chunk-rate quality and
  corpus size/coverage (see `infra/05-observability.yaml`).
- **Alarm** (`cshub-dev-ingestion-quality`): fires if `null_embedding_rate > 0` on any run
  (i.e. the index contains chunks with no vector — a real defect), routed to the SNS alert topic.
- **IAM:** the Manifest Lambda has scoped `cloudwatch:PutMetricData` on the `CSHub/Ingestion`
  namespace only.

## Advisory vs gating

- **Integrity** (chunks produced · all embedded · DB count matches) → **fails the run**.
- **Quality** (rates above) → **advisory**: emitted as metrics, flagged in the manifest
  (`quality_problems`), and alarmed — but does not fail the run. This keeps a single bad chunk
  from blocking an otherwise-good ingestion while still surfacing the issue.

## Thresholds (tune in code)

`MIN_CHUNK_CHARS = 200`, `MAX_CHUNK_CHARS = 2000` in `ingestion_metrics.py`; quality-problem
flags in `quality_problems()` (empty > 0, null embeddings > 0, duplicates > 20%, oversized >
30%). Adjust as the chunker and corpus evolve.

## Test locally (no AWS)

```bash
python -m pytest ../../ingestion/tests -q   # includes test_ingestion_metrics.py
```
