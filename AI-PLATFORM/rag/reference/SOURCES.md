# Sources — Advanced RAG Patterns

## Primary source
- **"Advanced RAG patterns" — AWS Builder Center**
  https://builder.aws.com/content/2ss6jEvdXJVgDt8vzFhR6PP9Qo8/advanced-rag-patterns
  > The page is a client-rendered SPA and could not be fetched programmatically. The full
  > article text and all 8 diagrams were provided directly by the user, so the notes now
  > follow the blog's actual content and structure, and the diagrams are reproduced to
  > match the originals.

## Blog's own reference table
| Resource | Link |
|---|---|
| RAPTOR Paper | https://arxiv.org/pdf/2401.18059.pdf |
| CRAG Paper | https://arxiv.org/abs/2401.15884 |
| ColBERT Paper | https://arxiv.org/pdf/2004.12832.pdf |
| RAGAS | https://github.com/explodinggradients/ragas |
| RAGatouille (ColBERT) | https://github.com/bclavie/RAGatouille |
| LangGraph CRAG | https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_crag.ipynb |

## Additional technique references (foundational papers)
| Technique | Source |
|---|---|
| DPR (dense passage retrieval) | https://arxiv.org/abs/2004.04906 |
| HyDE | https://arxiv.org/abs/2212.10496 |
| Step-Back Prompting | https://arxiv.org/abs/2310.06117 |
| Reciprocal Rank Fusion | https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf |
| Self-RAG | https://arxiv.org/abs/2310.11511 |
| Chain-of-Note | https://arxiv.org/abs/2311.09210 |

## Notes on this deliverable
- Content follows the source blog (provided verbatim by the user); code snippets, metrics
  (10–15% / 15–20% recall, 20%+ multi-hop, 2× BM25), the RAG Triad, RAGAS, the tech-stack
  table, and the decision tree are reproduced from it. Paraphrased/reformatted for the notes.
- The 8 diagrams in `images/` are reproductions matching the blog's originals
  (basic-vs-advanced, query-transformation, query-routing, advanced-indexing,
  colbert-vs-dense, reranking-chain-of-note, agentic-crag-selfrag, evaluation-framework).
- **Observability** and **Security** use-case callouts were added at the user's explicit
  request and are not part of the source blog.
