# Phase 1 · Chunking & Retrieval Strategy

> A focused reference for the two decisions that most shape RAG quality: **how documents are
> split into chunks** (ingestion) and **how chunks are retrieved** at query time. Both are the
> **Phase-1 baseline** — deliberately simple, measured, and with clear Phase-2 upgrade hooks.
> Grounded in the actual code: `ingestion/common/chunking.py`, `query-service/common/retrieval.py`,
> `query-service/common/prompt.py`.

---

## Part 1 — Chunking strategy

**Code:** `ingestion/common/chunking.py` → `chunk_text()`. Runs in the ingestion pipeline's
chunk step, after text extraction/cleaning and before embedding.

### Approach: structure-aware, overlapping chunks
Rather than blindly cutting every N characters, the chunker splits on **paragraph boundaries**
and packs whole paragraphs into a chunk until the size limit, so chunks stay semantically
coherent (avoids the "chunk myopia" failure where a hard cut splits a sentence/idea mid-thought).

| Parameter | Value | Rationale |
|---|---|---|
| `DEFAULT_MAX_CHARS` | **1200** (~300 tokens) | Well under Titan v2's 8k-token limit; small enough that a top-6 retrieval fits comfortably in the generation prompt, large enough to hold a coherent idea. |
| `DEFAULT_OVERLAP_CHARS` | **200** (~50 tokens) | A tail of the previous chunk is carried into the next so context isn't lost at boundaries (continuity for answers that straddle a split). |
| `MIN_CHARS` | **80** | Trivially small fragments are dropped (headings-only, stray lines) — they add noise to retrieval. |

### The algorithm (as implemented)
1. Split cleaned text into paragraphs on blank-line boundaries (`\n\s*\n`).
2. **Accumulate** paragraphs into a buffer until adding the next would exceed `max_chars`.
3. **Emit** the buffer as a chunk, then seed the next buffer with the last `overlap` characters
   of the one just emitted (the continuity tail).
4. **Oversized single paragraph** (bigger than `max_chars` on its own) → hard-split as a
   fallback, still preserving the overlap.
5. Chunks below `MIN_CHARS` are skipped.

### Chunk identity & metadata
Each chunk is a `Chunk(chunk_id, doc_id, text, ordinal, metadata)`:
- **`chunk_id`** = `"{doc_id}::{ordinal:04d}"` — e.g. `docs/eks-security.md::0003`. Stable,
  ordinal-based, so a chunk is addressable and its position in the document is known.
- **`doc_id`** ties the chunk back to its source document.
- **`metadata`** carries per-document fields (e.g. `source`, `service`) used for citations and
  (in Phase 2) metadata-filtered retrieval.

### What the corpus looks like in practice (Phase-1 run)
- Markdown/text sample docs → a handful of chunks each.
- The **SRA PDF** → **307 chunks**, avg ~980 chars, 0% empty/oversized — the paragraph packing
  held up on a large native-text PDF.
- Corpus quality gauges (`empty_chunk_rate`, `oversized_chunk_rate`, `null_embedding_rate`) are
  all **0.0** — see `04-observability.md`.

### Known limits / Phase-2 upgrades (chunking)
- **FI-3 — one `service` tag per document.** A large multi-service doc (the SRA PDF) gets a
  single body-frequency service tag (all 307 chunks tagged `iam`). Fix: classify `service`
  **per chunk** from the chunk's own text. See `FUTURE-IMPROVEMENTS.md`.
- **Fixed-size packing only.** No semantic/late chunking, no table/section-model awareness, no
  multi-representation (summary + raw) indexing. These are candidate Phase-2/3 improvements
  (per `AI-PLATFORM/rag`), each to be measured against the baseline.

---

## Part 2 — Retrieval strategy

**Code:** `query-service/common/retrieval.py` → `dense_search()`; prompt assembly in
`query-service/common/prompt.py`. Runs inside the query Lambda's `run_pipeline`.

### Approach: dense-only vector search (Phase-1 baseline)
1. The user question is embedded with **Amazon Titan Text Embeddings v2** — **1024 dimensions,
   `normalize: true`** (same model + dim used at ingestion, so query and chunk vectors live in
   the same normalized space).
2. A **pgvector approximate-nearest-neighbour** search over the `chunks` table in Aurora
   PostgreSQL returns the **top-K = 6** most similar chunks by **cosine** similarity.

The SQL (built by a pure, unit-tested function `dense_sql`):
```sql
SELECT chunk_id, doc_id, chunk_text, metadata,
       1 - (embedding <=> %s::vector) AS score      -- cosine distance -> similarity
FROM chunks
ORDER BY embedding <=> %s::vector                    -- pgvector cosine operator
LIMIT %s;                                            -- top_k = 6
```
Each result is a `Hit(chunk_id, doc_id, text, score, metadata)` — note the hit carries the full
chunk **text**, which is what feeds the prompt (and, since FI-6, the trace span).

### From hits to a grounded, cited answer
`build_prompt()` numbers each retrieved chunk `[1]…[6]` and instructs the model (Claude Sonnet
4.5) to **answer only from those passages** and cite them, or say *"I don't have enough
information…"* if they don't support an answer. This grounding discipline is why the system
refuses rather than hallucinates on out-of-scope questions (see `03-online-testing.md`).

| Parameter | Value |
|---|---|
| Embedding model | `amazon.titan-embed-text-v2:0` |
| Embedding dim | 1024, normalized |
| Vector store | Aurora PostgreSQL + **pgvector** |
| Similarity | cosine (`<=>` operator) |
| top-K | **6** |
| Retrieval mode | **dense only** (no keyword/hybrid, no rerank) |

### Phase-2 hooks (already wired, all OFF in Phase 1)
The pipeline has explicit hook points and feature flags (`query-service/common/config.py`) so
each advanced-RAG stage can be turned on and **A/B-measured against this baseline** without
restructuring:

| Flag | Stage | What it will add |
|---|---|---|
| `enable_hybrid` | Hybrid + RRF | merge dense with full-text (`tsvector`) search via Reciprocal Rank Fusion — `fulltext_sql` + `reciprocal_rank_fusion` already exist in `retrieval.py`. Targets exact-term recall. |
| `enable_rerank` | Cohere Rerank | re-order candidates so the most relevant chunk lands first (precision / MRR). |
| `enable_query_transform` | Query transformation | expand/rewrite the question for ambiguous/multi-hop queries (recall). |
| `enable_chain_of_note` | Chain-of-Note | per-chunk notes before generation (faithfulness, better "I don't know"). |
| `enable_crag` | CRAG | grade retrieved hits and refine/fallback when weak (correctness on out-of-corpus queries). |

### Known limits / why Phase 2 is needed (retrieval)
- **FI-5 — dense-only retrieval regressed as the corpus grew.** After the SRA added 307
  IAM-heavy chunks, an IAM golden question that scored ~1.0 at baseline now deflects, because
  the specific answering chunk got crowded out of the top-6. This is the concrete, measured
  motivation for **hybrid + rerank + larger/adaptive top-K**. See `FUTURE-IMPROVEMENTS.md` and
  `02-offline-eval.md`.
- **No metadata filtering yet** (blocked partly by FI-3's mono-service tags).

---

## How the two connect
Chunking sets the **granularity of what can be retrieved**; retrieval decides **which chunks
reach the model**. The Phase-1 choices (coherent ~1200-char chunks + dense top-6) give a clean,
measurable baseline — and the findings (FI-3, FI-5) show exactly where chunking and retrieval
need to evolve together in Phase 2. Every change is measured with the eval harness
(`02-offline-eval.md`, `03-online-testing.md`) against the numbers recorded here.
