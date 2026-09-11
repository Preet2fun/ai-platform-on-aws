"""Aurora PostgreSQL access for ingestion (upsert chunks with dense + sparse fields).

Uses psycopg (v3). Connection uses the master credentials from Secrets Manager. The `tsv`
full-text column is maintained by a DB trigger (see the P0 pgvector bootstrap DDL), so we
only write `embedding` + `chunk_text` + `metadata` here.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

DB_ENDPOINT = os.getenv("DB_ENDPOINT", "")
DB_NAME = os.getenv("DB_NAME", "cshub")
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN", "")


def _credentials() -> dict[str, str]:
    import boto3

    sm = boto3.client("secretsmanager")
    sec = json.loads(sm.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"])
    return {"user": sec["username"], "password": sec["password"]}


def connect(creds: dict[str, str] | None = None):
    import psycopg  # lazy import; unit tests can avoid needing the driver

    creds = creds or _credentials()
    return psycopg.connect(
        host=DB_ENDPOINT,
        dbname=DB_NAME,
        user=creds["user"],
        password=creds["password"],
        sslmode="require",
        connect_timeout=10,
    )


def upsert_document(conn, doc_id: str, metadata: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (doc_id, source, title, service, topic, version, sensitivity)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doc_id) DO UPDATE SET
              source=EXCLUDED.source, title=EXCLUDED.title, service=EXCLUDED.service,
              topic=EXCLUDED.topic, version=EXCLUDED.version, sensitivity=EXCLUDED.sensitivity
            """,
            (
                doc_id,
                metadata.get("source"),
                metadata.get("title"),
                metadata.get("service"),
                metadata.get("topic"),
                metadata.get("version"),
                metadata.get("sensitivity", "public"),
            ),
        )


def upsert_chunks(conn, rows: Iterable[dict[str, Any]]) -> int:
    """Upsert chunk rows. Each row: chunk_id, doc_id, chunk_text, embedding(list[float]), metadata(dict)."""
    n = 0
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO chunks (chunk_id, doc_id, chunk_text, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                  chunk_text=EXCLUDED.chunk_text, embedding=EXCLUDED.embedding, metadata=EXCLUDED.metadata
                """,
                (
                    r["chunk_id"],
                    r["doc_id"],
                    r["chunk_text"],
                    _vec_literal(r["embedding"]),
                    json.dumps(r.get("metadata", {})),
                ),
            )
            n += 1
    return n


def _vec_literal(vec: list[float]) -> str:
    """pgvector accepts a string literal like '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def count_chunks(conn, doc_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunks WHERE doc_id=%s", (doc_id,))
        return int(cur.fetchone()[0])
