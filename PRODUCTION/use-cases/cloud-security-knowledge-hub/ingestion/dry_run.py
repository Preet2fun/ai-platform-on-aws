"""Local dry-run of the ingestion pipeline (no AWS).

Runs clean → chunk → metadata on a local text file and prints what WOULD be embedded/upserted,
so you can eyeball chunking + metadata quality before deploying. Embedding + DB steps are
stubbed (they need Bedrock + Aurora).

Usage:
  python dry_run.py path/to/sample.txt
"""

from __future__ import annotations

import json
import sys

from common.chunking import chunk_text
from common.metadata import build_metadata
from handlers.clean import normalize


def main(path: str) -> None:
    with open(path, encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    cleaned = normalize(raw)
    doc_md = build_metadata(source=path, text_sample=cleaned[:4000])
    chunks = chunk_text("dryrun-doc", cleaned, metadata=doc_md)

    print(f"# source: {path}")
    print(f"# clean chars: {len(cleaned)}  chunks: {len(chunks)}")
    print(f"# doc metadata: {json.dumps(doc_md)}\n")
    for c in chunks[:5]:
        cm = build_metadata(source=path, text_sample=c.text[:2000], overrides=doc_md)
        print(f"--- {c.chunk_id} (ordinal {c.ordinal}, {len(c.text)} chars) ---")
        print(f"    service={cm.get('service')} topic={cm.get('topic')}")
        print(f"    {c.text[:160]!r}...\n")
    if len(chunks) > 5:
        print(f"... and {len(chunks) - 5} more chunks")
    print("\n[dry-run] embedding + Aurora upsert are stubbed (need Bedrock + Aurora).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python dry_run.py path/to/sample.txt", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
