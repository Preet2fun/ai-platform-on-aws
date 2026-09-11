"""Step 2: Clean & normalize extracted text.

Input:  { "doc_id", "source", "text_key" }
Output: adds { "clean_key" } (normalized text in the processed bucket)

Normalization: collapse excessive whitespace, strip control chars, de-hyphenate line breaks,
normalize bullets — without destroying paragraph structure (chunking relies on it).
"""

from __future__ import annotations

import os
import re

PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "")


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # de-hyphenate across line breaks
    text = re.sub(r"[ \t]+", " ", text)                    # collapse runs of spaces/tabs
    text = re.sub(r"\n{3,}", "\n\n", text)                 # cap blank lines at one
    return text.strip()


def handler(event, _context=None):
    import boto3

    s3 = boto3.client("s3")
    raw = s3.get_object(Bucket=PROCESSED_BUCKET, Key=event["text_key"])["Body"].read().decode("utf-8", "ignore")
    cleaned = normalize(raw)
    clean_key = f"clean/{event['doc_id']}.txt"
    s3.put_object(Bucket=PROCESSED_BUCKET, Key=clean_key, Body=cleaned.encode("utf-8"))
    return {**event, "clean_key": clean_key, "clean_chars": len(cleaned)}
