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

## Notes / caveats
- **Not deployed.** Templates + code authored and unit-tested only.
- The `chunks.tsv` full-text column is maintained by a **DB trigger** (from the P0 pgvector
  bootstrap), so ingestion writes only `embedding` + `chunk_text` + `metadata`.
- Bedrock (Titan) + Aurora access happen at runtime via VPC endpoints + the DB secret; no
  keys in code.
- v1 rejects non-text/PDF types; the video path (Transcribe) is a later phase.

## Ingestion evals (per AI-SDLC-AND-EVALS.md)
The Manifest step enforces: chunks produced, all embedded rows upserted, and DB count matches
`chunk_count`. Extend with coverage stats (docs→chunks) and chunk-size distribution as the
corpus grows.
