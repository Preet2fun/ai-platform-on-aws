"""Tests for prompt/citation building and the pipeline orchestration (mocked I/O)."""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dataclasses import dataclass
from typing import Any

from common.prompt import build_prompt, citations_payload, SYSTEM_INSTRUCTIONS
from common.retrieval import Hit
import app


def test_prompt_numbers_context_and_builds_citations():
    hits = [
        Hit("c1", "d1", "S3 bucket policy guidance", 0.9, {"source": "s3.pdf"}),
        Hit("c2", "d2", "IMDS SSRF prevention", 0.8, {"source": "ec2.md"}),
    ]
    prompt, cites = build_prompt("How to secure S3?", hits)
    assert "[1]" in prompt and "[2]" in prompt
    assert "s3.pdf" in prompt
    assert "only" in SYSTEM_INSTRUCTIONS.lower()  # grounding instruction present
    payload = citations_payload(cites)
    assert payload[0] == {"n": 1, "chunk_id": "c1", "doc_id": "d1", "source": "s3.pdf"}


def test_empty_context_prompt():
    prompt, cites = build_prompt("q", [])
    assert "(no context retrieved)" in prompt
    assert cites == []


@dataclass
class _Settings:
    embedding_dim: int = 1024
    top_k: int = 3


def test_pipeline_baseline_happy_path(monkeypatch):
    # mock every external call
    monkeypatch.setattr(app.bedrock, "apply_guardrail",
                        lambda text, source: {"blocked": False, "text": text, "action": "NONE"})
    monkeypatch.setattr(app.bedrock, "embed_query", lambda q, dim=1024: [0.0] * dim)
    monkeypatch.setattr(app.retrieval, "dense_search",
                        lambda vec, k: [Hit("c1", "d1", "ctx", 0.9, {"source": "s3.pdf"})])
    monkeypatch.setattr(app.bedrock, "generate", lambda prompt, **kw: "Configure it securely [1].")

    out = app.run_pipeline("How to secure S3?", s=_Settings())
    assert out["blocked"] is None
    assert out["answer"] == "Configure it securely [1]."
    assert out["citations"][0]["source"] == "s3.pdf"
    assert out["retrieved"] == 1
    assert "latency_ms" in out


def test_pipeline_input_blocked(monkeypatch):
    monkeypatch.setattr(app.bedrock, "apply_guardrail",
                        lambda text, source: {"blocked": source == "INPUT",
                                              "text": "blocked", "action": "GUARDRAIL_INTERVENED"})
    out = app.run_pipeline("malicious", s=_Settings())
    assert out["blocked"] == "input"
    assert out["citations"] == []


def test_handler_missing_question_returns_400():
    resp = app.handler({"body": "{}"})
    assert resp["statusCode"] == 400
