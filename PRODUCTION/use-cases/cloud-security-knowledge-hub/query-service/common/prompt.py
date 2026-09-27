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

# Chain-of-Note (Phase-2 Stage 4): make the model reason over each passage BEFORE answering,
# in one call. It writes a one-line relevance note per passage, then a final grounded answer
# after the marker. We show the user only the text after the marker; the notes stay in the
# trace for observability. Same grounding/IDK discipline as the baseline.
CON_MARKER = "=== FINAL ANSWER ==="
CHAIN_OF_NOTE_INSTRUCTIONS = (
    " Before answering, work through the passages step by step:\n"
    "1) Under a 'NOTES:' heading, write ONE short line per numbered passage stating whether it "
    "is relevant to the question and what specific fact it contributes (or 'not relevant').\n"
    "2) Then write the line " + repr(CON_MARKER) + " on its own.\n"
    "3) After that marker, give the final answer, grounded ONLY in the passages you marked "
    "relevant, citing them as [n]. If NONE of the passages support an answer, the text after "
    "the marker must be exactly: \"I don't have enough information to answer that from the "
    "knowledge base.\""
)


def split_final_answer(text: str) -> str:
    """Return the user-facing answer: the text after the last Chain-of-Note marker.

    Non-fatal: if the marker is absent (model didn't follow format), return the full text
    stripped — never lose the answer.
    """
    if not text:
        return ""
    idx = text.rfind(CON_MARKER)
    if idx == -1:
        return text.strip()
    return text[idx + len(CON_MARKER):].strip()


@dataclass
class Citation:
    n: int
    chunk_id: str
    doc_id: str
    source: str | None


def build_prompt(question: str, hits: list[Any], *, chain_of_note: bool = False) -> tuple[str, list[Citation]]:
    """Build the generation prompt from retrieved hits; return (prompt, citations).

    `hits` are objects with .chunk_id, .doc_id, .text, .metadata (retrieval.Hit).
    If `chain_of_note`, the model first writes per-passage notes, then the answer after
    CON_MARKER (Phase-2 Stage 4). The caller splits the final answer with split_final_answer().
    """
    citations: list[Citation] = []
    blocks: list[str] = []
    for i, h in enumerate(hits, start=1):
        src = (h.metadata or {}).get("source")
        citations.append(Citation(i, h.chunk_id, h.doc_id, src))
        blocks.append(f"[{i}] (source: {src or h.doc_id})\n{h.text}")
    context = "\n\n".join(blocks) if blocks else "(no context retrieved)"
    instructions = SYSTEM_INSTRUCTIONS + (CHAIN_OF_NOTE_INSTRUCTIONS if chain_of_note else "")
    tail = "=== NOTES then ANSWER ===" if chain_of_note else "=== ANSWER (cite passages as [n]) ==="
    prompt = (
        f"{instructions}\n\n"
        f"=== CONTEXT PASSAGES ===\n{context}\n\n"
        f"=== QUESTION ===\n{question}\n\n"
        f"{tail}"
    )
    return prompt, citations


def citations_payload(citations: list[Citation]) -> list[dict[str, Any]]:
    return [
        {"n": c.n, "chunk_id": c.chunk_id, "doc_id": c.doc_id, "source": c.source}
        for c in citations
    ]
