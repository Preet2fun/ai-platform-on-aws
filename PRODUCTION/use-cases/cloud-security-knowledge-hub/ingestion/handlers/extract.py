"""Step 1: Extract text from a source object (text or PDF).

Input (from EventBridge S3 detail): { "bucket": {"name": ...}, "object": {"key": ...} }
Output: { "doc_id", "source", "text_key" }  (raw text written to the processed bucket)

- .txt / .md → read directly
- native PDF  → PyPDF text extraction
- scanned PDF → Amazon Textract fallback (when PyPDF yields little/no text)
"""

from __future__ import annotations

import os
import re

RAW_BUCKET = os.getenv("RAW_BUCKET", "")
PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "")


def _doc_id(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._/-]", "_", key)


def handler(event, _context=None):
    import boto3

    s3 = boto3.client("s3")
    bucket = event.get("bucket", {}).get("name") or RAW_BUCKET
    key = event["object"]["key"]
    doc_id = _doc_id(key)
    lower = key.lower()

    if lower.endswith((".txt", ".md")):
        text = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8", "ignore")
    elif lower.endswith(".pdf"):
        text = _extract_pdf(s3, bucket, key)
    else:
        raise ValueError(f"unsupported file type (v1 = text/pdf only): {key}")

    text_key = f"text/{doc_id}.txt"
    s3.put_object(Bucket=PROCESSED_BUCKET, Key=text_key, Body=text.encode("utf-8"))
    return {"doc_id": doc_id, "source": key, "text_key": text_key, "chars": len(text)}


def _extract_pdf(s3, bucket: str, key: str) -> str:
    raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    text = ""
    try:
        import io
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        text = ""
    # Fallback to Textract for scanned/image PDFs where native extraction is empty.
    if len(text.strip()) < 100:
        text = _textract(bucket, key)
    return text


def _textract(bucket: str, key: str) -> str:
    import boto3

    tx = boto3.client("textract")
    resp = tx.detect_document_text(Document={"S3Object": {"Bucket": bucket, "Name": key}})
    lines = [b["Text"] for b in resp.get("Blocks", []) if b["BlockType"] == "LINE"]
    return "\n".join(lines)
