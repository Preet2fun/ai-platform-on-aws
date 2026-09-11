"""Structure-aware chunking.

Splits cleaned text into overlapping chunks sized for embedding + retrieval. Prefers
paragraph/heading boundaries over hard character cuts so chunks stay semantically coherent
(reduces the "chunk myopia" failure mode from the RAG notes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Titan v2 handles up to 8k tokens; we keep chunks well under that for retrieval quality.
DEFAULT_MAX_CHARS = 1200          # ~300 tokens
DEFAULT_OVERLAP_CHARS = 200       # ~50 tokens of overlap for context continuity
MIN_CHARS = 80                    # drop trivially small fragments

_HEADING = re.compile(r"^\s{0,3}(#{1,6}\s+|\d+\.\s+|[A-Z][A-Za-z0-9 ]{0,60}\n[-=]{3,})", re.M)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    ordinal: int
    metadata: dict[str, Any] = field(default_factory=dict)


def _split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def chunk_text(
    doc_id: str,
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP_CHARS,
    metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Chunk `text` into overlapping, boundary-aware chunks.

    Strategy: accumulate paragraphs until adding the next would exceed max_chars, then emit a
    chunk; carry an `overlap`-sized tail into the next chunk for continuity. Oversized single
    paragraphs are hard-split as a fallback.
    """
    metadata = metadata or {}
    paragraphs = _split_paragraphs(text)
    chunks: list[Chunk] = []
    buf = ""
    ordinal = 0

    def emit(s: str) -> None:
        nonlocal ordinal
        s = s.strip()
        if len(s) < MIN_CHARS:
            return
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}::{ordinal:04d}",
                doc_id=doc_id,
                text=s,
                ordinal=ordinal,
                metadata=dict(metadata),
            )
        )
        ordinal += 1

    for para in paragraphs:
        # hard-split a single huge paragraph
        while len(para) > max_chars:
            head, para = para[:max_chars], para[max_chars - overlap:]
            if buf:
                emit(buf)
                buf = ""
            emit(head)
        if len(buf) + len(para) + 1 <= max_chars:
            buf = f"{buf}\n{para}".strip()
        else:
            emit(buf)
            tail = buf[-overlap:] if overlap and len(buf) > overlap else ""
            buf = f"{tail}\n{para}".strip()
    if buf:
        emit(buf)
    return chunks
