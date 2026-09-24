# Diagrams

Architecture and flow diagrams for the Cloud Security Knowledge Hub. Rendered PNGs live here;
their editable sources are in [`../_diagram-src/`](../_diagram-src/) (HTML) and `*.mmd` (Mermaid).

## Phase 1 vs Phase 2 (this folder)
> Canonical run log: [`../docs/phase-1/`](../docs/phase-1/) · next phase: [`../docs/phase-2/`](../docs/phase-2/).

The diagrams below depict the **Phase-1 baseline** architecture and flows. When Phase 2 lands
(advanced retrieval + automated online-eval infra), add `05-phase2-*` diagrams here and index
them in the Phase-2 section — do **not** overwrite the Phase-1 ones, so the two phases stay
comparable for future reference.

## Index (Phase 1)

| File | Shows |
|---|---|
| `01-offline-ingestion.png` | Offline ingestion pipeline: S3 upload → Step Functions (Extract → Clean → Chunk → EmbedUpsert → Manifest) → Aurora/pgvector. |
| `02-online-query-phases.png` | Online query pipeline phases: guardrails → embed → dense retrieval → cited generation → guardrails. |
| `03-ecosystem.png` | Overall ecosystem / service map (how the components fit together). |
| `04-phase1-aws-architecture.png` | Phase-1 AWS architecture (VPC, Aurora, Lambdas, API Gateway, Cognito, CloudFront). |
| `04-phase1-request-response.png` | Phase-1 request/response sequence for a single query (`.mmd` source alongside). |

## What Phase 1 covers vs what Phase 2 will add
- **Phase 1 (these diagrams):** dense-only retrieval, baseline generation, the deployed AWS
  architecture, and the single-query request/response path.
- **Phase 2 (to add):** hybrid retrieval + rerank + query-transform + Chain-of-Note + CRAG in
  the online flow; the automated online-eval loop (EventBridge sampler → LLM-judge → drift
  alarms); and the OTel content-trace path (query Lambda → `aws/spans` → trace-grounded eval)
  that Phase 1 introduced via FI-6. See [`../docs/phase-1/FUTURE-IMPROVEMENTS.md`](../docs/phase-1/FUTURE-IMPROVEMENTS.md).

## Editing
Sources are in `../_diagram-src/` (HTML + `style.css` + `aws-icons/`) and the Mermaid `.mmd`
files here. Re-export to PNG after editing and keep the filename/phase prefix stable.
