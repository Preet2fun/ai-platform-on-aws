"""Offline tests for eval aggregation, delta reporting, and the quality gate."""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gate import evaluate_gate
from report import aggregate, aggregate_system, delta_report

THRESHOLDS = {
    "floors": {"faithfulness": 0.80, "answer_relevancy": 0.75,
               "context_precision": 0.70, "context_recall": 0.70},
    "max_regression": {"faithfulness": 0.03, "answer_relevancy": 0.05,
                       "context_precision": 0.05, "context_recall": 0.05},
    "system_ceilings": {"p95_latency_ms": 6000, "avg_cost_usd_per_query": 0.05},
}


def test_aggregate_means():
    rows = [{"faithfulness": 0.9, "answer_relevancy": 0.8},
            {"faithfulness": 0.7, "answer_relevancy": 0.9}]
    agg = aggregate(rows, ["faithfulness", "answer_relevancy"])
    assert agg["faithfulness"] == 0.8
    assert agg["answer_relevancy"] == 0.85


def test_aggregate_system_p95():
    rows = [{"latency_ms": v} for v in [100, 200, 300, 400, 5000]]
    s = aggregate_system(rows)
    assert s["p95_latency_ms"] == 5000
    assert "avg_latency_ms" in s


def test_gate_passes_when_above_floors():
    scores = {"faithfulness": 0.9, "answer_relevancy": 0.85,
              "context_precision": 0.8, "context_recall": 0.78}
    res = evaluate_gate(scores, THRESHOLDS)
    assert res.passed
    assert res.failures == []


def test_gate_fails_below_floor():
    scores = {"faithfulness": 0.5, "answer_relevancy": 0.85,
              "context_precision": 0.8, "context_recall": 0.78}
    res = evaluate_gate(scores, THRESHOLDS)
    assert not res.passed
    assert any("faithfulness" in f and "floor" in f for f in res.failures)


def test_gate_fails_on_regression():
    baseline = {"faithfulness": 0.90, "answer_relevancy": 0.85,
                "context_precision": 0.80, "context_recall": 0.78}
    scores = {"faithfulness": 0.85, "answer_relevancy": 0.85,   # -0.05 > allowed 0.03
              "context_precision": 0.80, "context_recall": 0.78}
    res = evaluate_gate(scores, THRESHOLDS, baseline=baseline)
    assert not res.passed
    assert any("regressed" in f for f in res.failures)


def test_gate_fails_on_system_ceiling():
    scores = {"faithfulness": 0.9, "answer_relevancy": 0.85,
              "context_precision": 0.8, "context_recall": 0.78}
    res = evaluate_gate(scores, THRESHOLDS, system={"p95_latency_ms": 9000})
    assert not res.passed
    assert any("p95_latency_ms" in f for f in res.failures)


def test_delta_report_verdicts():
    rep = delta_report({"faithfulness": 0.9}, {"faithfulness": 0.8}, ["faithfulness"])
    assert rep[0]["verdict"] == "better"
    assert rep[0]["delta"] == 0.1
