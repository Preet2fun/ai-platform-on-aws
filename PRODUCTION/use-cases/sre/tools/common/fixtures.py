"""Shared fixture loader for the synthetic observability backends (Option A).

Every backend (metrics/logs/traces/changes/k8s-events/runbooks) reads tenant- and
scenario-scoped fixtures from `synthetic-data/tenants/<tenant_id>/scenarios/<scenario_id>/`.
The agent never sees `manifest.yaml` (that is eval-only ground truth) — these loaders expose
only the observable signals, and always enforce tenant + optional time-window scoping so the
agent's experience matches a real per-tenant observability tool.

In P9 a `cloudwatch_tools` backend implements the same response shapes against real CloudWatch,
so agents swap data source by config, not by code.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# repo-relative root: .../PRODUCTION/use-cases/sre
_SRE_ROOT = Path(__file__).resolve().parents[2]
_DATA_ROOT = Path(os.getenv("SRE_SYNTH_DATA_ROOT", _SRE_ROOT / "synthetic-data" / "tenants"))


class TenantNotFound(Exception):
    pass


class ScenarioNotFound(Exception):
    pass


@lru_cache(maxsize=1)
def _registry() -> dict[str, Any]:
    reg = _DATA_ROOT / "registry.yaml"
    with open(reg, encoding="utf-8") as f:
        return yaml.safe_load(f)


def known_tenants() -> list[str]:
    return [t["tenant_id"] for t in _registry().get("tenants", [])]


def tenant_config(tenant_id: str) -> dict[str, Any]:
    for t in _registry().get("tenants", []):
        if t["tenant_id"] == tenant_id:
            return t
    raise TenantNotFound(f"unknown tenant '{tenant_id}' (known: {known_tenants()})")


def tenant_scenarios(tenant_id: str) -> list[str]:
    return list(tenant_config(tenant_id).get("scenarios", []))


def _scenario_dir(tenant_id: str, scenario_id: str) -> Path:
    tenant_config(tenant_id)  # validates tenant
    d = _DATA_ROOT / tenant_id / "scenarios" / scenario_id
    if not d.is_dir():
        raise ScenarioNotFound(
            f"unknown scenario '{scenario_id}' for tenant '{tenant_id}' "
            f"(available: {tenant_scenarios(tenant_id)})"
        )
    return d


def _load_json(tenant_id: str, scenario_id: str, name: str) -> Any:
    path = _scenario_dir(tenant_id, scenario_id) / name
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def _in_window(ts: str, start: str | None, end: str | None) -> bool:
    if not start and not end:
        return True
    t = _parse_ts(ts)
    if start and t < _parse_ts(start):
        return False
    if end and t > _parse_ts(end):
        return False
    return True


# ---- signal loaders (tenant + optional service + optional time-window scoped) ----

def get_metrics(tenant_id: str, scenario_id: str, service: str | None = None,
                metric: str | None = None, start: str | None = None,
                end: str | None = None) -> list[dict[str, Any]]:
    series = _load_json(tenant_id, scenario_id, "metrics.json")
    out = []
    for s in series:
        if service and s.get("service") != service:
            continue
        if metric and s.get("metric") != metric:
            continue
        pts = [p for p in s.get("points", []) if _in_window(p["ts"], start, end)]
        out.append({**s, "points": pts})
    return out


def get_logs(tenant_id: str, scenario_id: str, service: str | None = None,
             level: str | None = None, contains: str | None = None,
             start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    rows = _load_json(tenant_id, scenario_id, "logs.json")
    out = []
    for r in rows:
        if service and r.get("service") != service:
            continue
        if level and r.get("level", "").upper() != level.upper():
            continue
        if contains and contains.lower() not in r.get("message", "").lower():
            continue
        if not _in_window(r.get("ts", ""), start, end):
            continue
        out.append(r)
    return out


def get_traces(tenant_id: str, scenario_id: str, service: str | None = None,
               errors_only: bool = False, start: str | None = None,
               end: str | None = None) -> list[dict[str, Any]]:
    rows = _load_json(tenant_id, scenario_id, "traces.json")
    out = []
    for r in rows:
        if not _in_window(r.get("ts", ""), start, end):
            continue
        if service and r.get("root_service") != service \
                and not any(sp.get("service") == service for sp in r.get("spans", [])):
            continue
        if errors_only and not any(sp.get("error") for sp in r.get("spans", [])):
            continue
        out.append(r)
    return out


def get_changes(tenant_id: str, scenario_id: str, service: str | None = None,
                change_type: str | None = None, start: str | None = None,
                end: str | None = None) -> list[dict[str, Any]]:
    rows = _load_json(tenant_id, scenario_id, "changes.json")
    out = []
    for r in rows:
        if service and r.get("service") != service:
            continue
        if change_type and r.get("type") != change_type:
            continue
        if not _in_window(r.get("ts", ""), start, end):
            continue
        out.append(r)
    return out


def get_events(tenant_id: str, scenario_id: str, service: str | None = None,
               source: str | None = None, start: str | None = None,
               end: str | None = None) -> list[dict[str, Any]]:
    rows = _load_json(tenant_id, scenario_id, "events.json")
    out = []
    for r in rows:
        if service and r.get("service") != service:
            continue
        if source and r.get("source") != source:
            continue
        if not _in_window(r.get("ts", ""), start, end):
            continue
        out.append(r)
    return out


def get_runbooks(tenant_id: str, query: str | None = None,
                 service: str | None = None) -> list[dict[str, Any]]:
    """Tenant-level operational runbooks (not per-scenario). Simple keyword/service search."""
    tenant_config(tenant_id)  # validates tenant
    path = _DATA_ROOT / tenant_id / "runbooks.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        books = json.load(f)
    q = (query or "").lower().strip()
    out = []
    for b in books:
        if service and service not in b.get("services", []):
            continue
        if q:
            hay = " ".join([
                b.get("title", ""),
                " ".join(b.get("symptoms", [])),
                " ".join(b.get("services", [])),
                " ".join(b.get("steps", [])),
            ]).lower()
            if q not in hay and not any(q in s.lower() for s in b.get("symptoms", [])):
                continue
        out.append(b)
    return out
