# RAG — Advanced Retrieval-Augmented Generation Patterns

Comprehensive notes on advanced RAG techniques for grounding agents in external knowledge,
part of the AI-PLATFORM reference.

## Contents

- **`advanced-rag-patterns.html`** — the full notes (open in a browser). Covers 10 topics,
  each with the source diagram and worked **Observability** and **Security** use-case examples.
- **`advanced-rag-patterns.pdf`** — the notes exported to PDF (with images embedded).
- **`images/`** — the original blog diagrams (`.webp`), embedded in the HTML.
- **`reference/SOURCES.md`** — the source blog + citations for every technique.

## Topics covered

1. Why Basic RAG Fails at Scale
2. Query Transformation (Multi-Query, RAG-Fusion/RRF, Decomposition, Step-Back, HyDE)
3. Query Routing (logical, semantic, tool/no-retrieve)
4. Advanced Indexing (Multi-Representation + RAPTOR)
5. Advanced Retrieval (DPR + ColBERT, hybrid search)
6. Re-ranking & Chain-of-Note
7. Agentic RAG (CRAG & Self-RAG)
8. Evaluation Framework
9. Production Architecture Blueprint
10. Implementation Patterns

## How to read / export

- **View:** open `advanced-rag-patterns.html` in any browser.
- **PDF:** already provided as `advanced-rag-patterns.pdf`; regenerate anytime via Print → "Save as PDF".

## Notes on scope

- Content follows the source blog ("Advanced RAG patterns", AWS Builder Center), provided
  by the user; code snippets, metrics, the RAG Triad, RAGAS, the tech-stack table, and the
  decision tree are reproduced from it.
- The 8 diagrams in `images/` are the **original blog images** supplied by the user.
- The per-technique **Observability** and **Security** examples were added at explicit
  request and are not part of the source blog.
