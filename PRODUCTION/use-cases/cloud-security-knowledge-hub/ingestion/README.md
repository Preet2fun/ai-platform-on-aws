# Ingestion Pipeline (P1) — offline, v1: text + PDF

Offline pipeline that turns source documents into searchable knowledge in Aurora
(dense pgvector + sparse full-text). Orchestrated by Step Functions; triggered on S3 upload.

## Flow

```
S3 upload (raw) → EventBridge → Step Functions:
  Extract → Clean → Chunk → EmbedUpsert → Manifest
```

| Step | Handler | Does |
|---|---|---|
| Extract | `handlers/extract.py` | text/md read; PDF via pypdf, Textract fallback for scanned |
| Clean | `handlers/clean.py` | normalize whitespace, de-hyphenate, keep paragraph structure |
| Chunk | `handlers/chunk.py` | structure-aware chunking + per-chunk metadata → JSONL |
| EmbedUpsert | `handlers/embed_upsert.py` | Titan v2 embed + upsert to Aurora (`documents`, `chunks`) |
| Manifest | `handlers/manifest.py` | ingestion-quality checks + audit manifest (fails run if bad) |

Large docs can route to the **Fargate** `heavy_embed.py` task (no Lambda timeout).

## Layout
```
ingestion/
├── common/          # shared lib: chunking, metadata, embed (Titan), db (Aurora/pgvector)
├── handlers/        # the 5 Step Functions Lambda handlers
├── heavy_embed.py   # Fargate entrypoint for large batches
├── Dockerfile       # ARM64 image for the Fargate task
├── requirements.txt
├── dry_run.py       # local, no-AWS chunking/metadata preview
└── tests/           # offline unit tests (13, all passing)
```

## Test locally (no AWS)
```bash
python -m pytest tests -q          # unit tests
python dry_run.py sample.txt       # preview chunking + metadata for a file
```

## Packaging (CI, later)
- Each handler is zipped with `common/` + deps (`psycopg`, `pypdf`) and uploaded to the
  Lambda code bucket; `infra/02-ingestion.yaml` params (`ExtractKey`, etc.) point at them.
- The Fargate image is built from `Dockerfile`, pushed to ECR
  (`<acct>.dkr.ecr.<region>.amazonaws.com/cshub-<env>-ingest:latest`).

## Phase 1 vs Phase 2 (this folder)
> Canonical run log: [`../docs/phase-1/`](../docs/phase-1/) · next phase: [`../docs/phase-2/`](../docs/phase-2/).

| | **Phase 1 (shipped + live)** | **Phase 2 (planned)** | Why / what was missing |
|---|---|---|---|
| Chunking | Structure-aware, ~1200-char paragraph packing + 200 overlap | Per-chunk service classification; semantic / multi-representation chunking | **FI-3**: a large multi-service doc (the SRA PDF) gets one body-frequency `service` tag (all 307 chunks tagged `iam`), weakening metadata-filtered retrieval. |
| Large docs | Lambda path only (native-text PDF OK; SRA PDF = 307 chunks) | Build the deferred **Fargate** heavy-embed path | **FI-2**: a 2,000+ chunk PDF (KMS guide) can't finish inside the 900s Lambda timeout — the Fargate route was deferred. |
| Embedding throughput | Retry-with-backoff + inter-call pacing | Batched / rate-limited embedding | **FI-1 (done)**: throttling on large docs fixed with backoff; batching is the scale follow-up. |

**Phase-1 status: the pipeline is deployed and has ingested a live corpus** (19 docs / 337
chunks incl. the SRA PDF). Walkthrough with real numbers:
[`../docs/phase-1/01-offline-ingestion-walkthrough.md`](../docs/phase-1/01-offline-ingestion-walkthrough.md).
Chunking strategy detail: [`../docs/phase-1/05-chunking-and-retrieval.md`](../docs/phase-1/05-chunking-and-retrieval.md).
Findings: [`../docs/phase-1/FUTURE-IMPROVEMENTS.md`](../docs/phase-1/FUTURE-IMPROVEMENTS.md) (FI-1, FI-2, FI-3).

## Notes / caveats
- **Deployed** (Step Functions pipeline live; corpus ingested). The **Fargate heavy-embed
  path is not built yet** (FI-2) — large multi-hundred-page PDFs use the Lambda path only.
- The `chunks.tsv` full-text column is maintained by a **DB trigger** (from the P0 pgvector
  bootstrap), so ingestion writes only `embedding` + `chunk_text` + `metadata`.
- Bedrock (Titan) + Aurora access happen at runtime via VPC endpoints + the DB secret; no
  keys in code.
- v1 rejects non-text/PDF types; the video path (Transcribe) is a later phase.

## Ingestion evals (per AI-SDLC-AND-EVALS.md)
The Manifest step enforces: chunks produced, all embedded rows upserted, and DB count matches
`chunk_count`. Extend with coverage stats (docs→chunks) and chunk-size distribution as the
corpus grows.
