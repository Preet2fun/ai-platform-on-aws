"""Quality-gate logic (pure, testable).

Given aggregated metric scores, an optional recorded baseline, and thresholds, decide whether
a change passes the gate. Used both locally and in CI (see .github/workflows/eval-gate.yml).

Gate fails if ANY of:
  - a quality metric is below its floor
  - a quality metric regresses more than the allowed max_regression vs baseline
  - a system metric exceeds its ceiling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "failures": self.failures}


def evaluate_gate(
    scores: dict[str, float],
    thresholds: dict[str, Any],
    baseline: dict[str, float] | None = None,
    system: dict[str, float] | None = None,
) -> GateResult:
    failures: list[str] = []

    floors = thresholds.get("floors", {})
    for metric, floor in floors.items():
        val = scores.get(metric)
        if val is None:
            failures.append(f"missing metric: {metric}")
        elif val < floor:
            failures.append(f"{metric}={val:.3f} below floor {floor:.3f}")

    if baseline:
        max_reg = thresholds.get("max_regression", {})
        for metric, allowed in max_reg.items():
            cur, base = scores.get(metric), baseline.get(metric)
            if cur is not None and base is not None and (base - cur) > allowed:
                failures.append(
                    f"{metric} regressed {base - cur:.3f} (>{allowed:.3f}) "
                    f"[{base:.3f} -> {cur:.3f}]"
                )

    if system:
        ceilings = thresholds.get("system_ceilings", {})
        for metric, ceiling in ceilings.items():
            val = system.get(metric)
            if val is not None and val > ceiling:
                failures.append(f"{metric}={val} exceeds ceiling {ceiling}")

    return GateResult(passed=(len(failures) == 0), failures=failures)
