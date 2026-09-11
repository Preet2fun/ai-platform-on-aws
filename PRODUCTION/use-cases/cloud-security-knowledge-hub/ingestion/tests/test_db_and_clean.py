"""Tests for the pgvector literal, clean/normalize, and manifest checks (no AWS needed)."""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.db import _vec_literal
from handlers.clean import normalize
from handlers.manifest import run_checks


def test_vec_literal_format():
    assert _vec_literal([0.1, 0.2, 0.3]) == "[0.100000,0.200000,0.300000]"


def test_normalize_collapses_whitespace_and_dehyphenates():
    raw = "Secur-\nity   config\r\n\r\n\r\n\r\nnext"
    out = normalize(raw)
    assert "Security" in out          # de-hyphenated across line break
    assert "  " not in out            # collapsed spaces
    assert "\n\n\n" not in out        # capped blank lines


def test_manifest_checks_pass():
    ok, problems = run_checks({"chunk_count": 5, "upserted": 5}, db_count=5)
    assert ok and problems == []


def test_manifest_checks_fail_on_mismatch():
    ok, problems = run_checks({"chunk_count": 5, "upserted": 4}, db_count=5)
    assert not ok
    assert any("upserted" in p for p in problems)


def test_manifest_checks_fail_on_zero_chunks():
    ok, problems = run_checks({"chunk_count": 0, "upserted": 0}, db_count=0)
    assert not ok
    assert any("no chunks" in p for p in problems)
