"""Aggregation + delta reporting (pure, testable).

- aggregate(): mean each metric across per-example rows.
- delta_report(): compare a candidate config's scores vs a baseline, per metric.
Used to answer "did enabling hybrid / rerank / CoN / CRAG actually help?" (Phase 2).
"""

from __future__ import annotations

from typing import Any

METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


def aggregate(rows: list[dict[str, Any]], metrics: list[str] | None = None) -> dict[str, float]:
    metrics = metrics or METRICS
    out: dict[str, float] = {}
    for m in metrics:
        vals = [r[m] for r in rows if isinstance(r.get(m), (int, float))]
        out[m] = round(sum(vals) / len(vals), 4) if vals else 0.0
    return out


def aggregate_system(rows: list[dict[str, Any]]) -> dict[str, float]:
    lat = sorted(r["latency_ms"] for r in rows if isinstance(r.get("latency_ms"), (int, float)))
    costs = [r["cost_usd"] for r in rows if isinstance(r.get("cost_usd"), (int, float))]
    out: dict[str, float] = {}
    if lat:
        idx = max(0, int(round(0.95 * (len(lat) - 1))))
        out["p95_latency_ms"] = lat[idx]
        out["avg_latency_ms"] = round(sum(lat) / len(lat), 1)
    if costs:
        out["avg_cost_usd_per_query"] = round(sum(costs) / len(costs), 5)
    return out


def delta_report(candidate: dict[str, float], baseline: dict[str, float],
                 metrics: list[str] | None = None) -> list[dict[str, Any]]:
    metrics = metrics or METRICS
    rows = []
    for m in metrics:
        c, b = candidate.get(m, 0.0), baseline.get(m, 0.0)
        rows.append({
            "metric": m, "baseline": b, "candidate": c,
            "delta": round(c - b, 4),
            "verdict": "better" if c > b else ("worse" if c < b else "same"),
        })
    return rows


def render_markdown(candidate: dict, baseline: dict, config_name: str) -> str:
    lines = [f"### Eval delta — `{config_name}` vs baseline\n",
             "| Metric | Baseline | Candidate | Delta | Verdict |",
             "|---|---|---|---|---|"]
    for r in delta_report(candidate, baseline):
        arrow = {"better": "🟢", "worse": "🔴", "same": "⚪"}[r["verdict"]]
        lines.append(f"| {r['metric']} | {r['baseline']:.3f} | {r['candidate']:.3f} "
                     f"| {r['delta']:+.3f} | {arrow} {r['verdict']} |")
    return "\n".join(lines)
