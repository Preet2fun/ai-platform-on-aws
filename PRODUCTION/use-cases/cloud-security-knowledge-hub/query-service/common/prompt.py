"""Prompt construction + citation handling for grounded, cited answers.

Security-first behavior: the model must answer ONLY from the provided context and must say
"I don't have enough information" when the context doesn't support an answer (no guessing).
Each context chunk is numbered so the answer can cite [n], and we map [n] -> source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SYSTEM_INSTRUCTIONS = (
    "You are a cloud-security knowledge assistant. Answer the user's question about AWS "
    "security (how to configure a service securely, how an attack happens, how to prevent "
    "it) using ONLY the numbered context passages provided. Cite the passages you use with "
    "bracketed numbers like [1], [2]. If the context does not contain enough information to "
    "answer, say exactly: \"I don't have enough information to answer that from the "
    "knowledge base.\" Do not use outside knowledge. Be precise and do not invent "
    "configuration steps, commands, or CVE identifiers."
)


@dataclass
class Citation:
    n: int
    chunk_id: str
    doc_id: str
    source: str | None


def build_prompt(question: str, hits: list[Any]) -> tuple[str, list[Citation]]:
    """Build the generation prompt from retrieved hits; return (prompt, citations).

    `hits` are objects with .chunk_id, .doc_id, .text, .metadata (retrieval.Hit).
    """
    citations: list[Citation] = []
    blocks: list[str] = []
    for i, h in enumerate(hits, start=1):
        src = (h.metadata or {}).get("source")
        citations.append(Citation(i, h.chunk_id, h.doc_id, src))
        blocks.append(f"[{i}] (source: {src or h.doc_id})\n{h.text}")
    context = "\n\n".join(blocks) if blocks else "(no context retrieved)"
    prompt = (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"=== CONTEXT PASSAGES ===\n{context}\n\n"
        f"=== QUESTION ===\n{question}\n\n"
        f"=== ANSWER (cite passages as [n]) ==="
    )
    return prompt, citations


def citations_payload(citations: list[Citation]) -> list[dict[str, Any]]:
    return [
        {"n": c.n, "chunk_id": c.chunk_id, "doc_id": c.doc_id, "source": c.source}
        for c in citations
    ]
