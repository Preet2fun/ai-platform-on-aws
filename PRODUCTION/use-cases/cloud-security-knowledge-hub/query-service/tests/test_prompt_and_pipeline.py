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


def test_chain_of_note_prompt_adds_notes_instructions():
    from common.prompt import CON_MARKER
    hits = [Hit("c1", "d1", "ctx", 0.9, {"source": "s3.pdf"})]
    prompt, _ = build_prompt("q", hits, chain_of_note=True)
    assert "NOTES:" in prompt
    assert CON_MARKER in prompt
    # baseline prompt must NOT carry the notes instructions
    base_prompt, _ = build_prompt("q", hits, chain_of_note=False)
    assert "NOTES:" not in base_prompt


def test_split_final_answer_extracts_after_marker():
    from common.prompt import split_final_answer, CON_MARKER
    raw = f"NOTES:\n[1] relevant - S3 BPA\n{CON_MARKER}\nEnable Block Public Access [1]."
    assert split_final_answer(raw) == "Enable Block Public Access [1]."


def test_split_final_answer_fallback_when_no_marker():
    from common.prompt import split_final_answer
    assert split_final_answer("just an answer, no marker") == "just an answer, no marker"


@dataclass
class _Settings:
    embedding_dim: int = 1024
    top_k: int = 3
    generation_model_id: str = "test-model"
    enable_hybrid: bool = False
    enable_rerank: bool = False
    rerank_model_id: str = "cohere.rerank-v3-5:0"
    rerank_candidate_k: int = 20
    enable_query_transform: bool = False
    query_transform_n: int = 3
    merged_candidate_cap: int = 60
    enable_chain_of_note: bool = False
    enable_crag: bool = False
    crag_min_relevance: float = 0.30


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


@dataclass
class _CragSettings(_Settings):
    enable_rerank: bool = True
    enable_crag: bool = True
    crag_min_relevance: float = 0.30


def test_crag_short_circuits_to_idk_on_weak_context(monkeypatch):
    monkeypatch.setattr(app.bedrock, "apply_guardrail",
                        lambda text, source: {"blocked": False, "text": text, "action": "NONE"})
    monkeypatch.setattr(app.bedrock, "embed_query", lambda q, dim=1024: [0.0] * dim)
    monkeypatch.setattr(app.retrieval, "dense_search",
                        lambda vec, k: [Hit("c1", "d1", "ctx", 0.9, {"source": "x"})])
    # reranker returns a LOW top relevance score -> CRAG should correct to IDK
    monkeypatch.setattr(app.bedrock, "rerank",
                        lambda q, hits, k, **kw: [Hit("c1", "d1", "ctx", 0.10, {"source": "x"})])
    called = {"gen": False}
    monkeypatch.setattr(app.bedrock, "generate",
                        lambda prompt, **kw: called.__setitem__("gen", True) or "should not run")

    out = app.run_pipeline("out-of-corpus question", s=_CragSettings())
    assert "don't have enough information" in out["answer"].lower()
    assert out["citations"] == []
    assert called["gen"] is False           # generation was skipped (corrective short-circuit)


def test_crag_allows_answer_on_strong_context(monkeypatch):
    monkeypatch.setattr(app.bedrock, "apply_guardrail",
                        lambda text, source: {"blocked": False, "text": text, "action": "NONE"})
    monkeypatch.setattr(app.bedrock, "embed_query", lambda q, dim=1024: [0.0] * dim)
    monkeypatch.setattr(app.retrieval, "dense_search",
                        lambda vec, k: [Hit("c1", "d1", "ctx", 0.9, {"source": "x"})])
    # strong top relevance -> CRAG passes, normal generation runs
    monkeypatch.setattr(app.bedrock, "rerank",
                        lambda q, hits, k, **kw: [Hit("c1", "d1", "ctx", 0.85, {"source": "x"})])
    monkeypatch.setattr(app.bedrock, "generate", lambda prompt, **kw: "Grounded answer [1].")

    out = app.run_pipeline("in-corpus question", s=_CragSettings())
    assert out["answer"] == "Grounded answer [1]."


def test_handler_missing_question_returns_400():
    resp = app.handler({"body": "{}"})
    assert resp["statusCode"] == 400
