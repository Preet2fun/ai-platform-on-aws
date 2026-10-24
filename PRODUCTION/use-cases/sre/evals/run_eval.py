"""P7 eval runner — score the deployed agent against hidden scenario manifests.

Usage (from PRODUCTION/use-cases/sre, with AWS creds):
  # one scenario, fresh run:
  python3 -m evals.run_eval --tenant acme-retail --scenario rds-connection-exhaustion
  # full matrix (all tenants x scenarios in the registry):
  python3 -m evals.run_eval --all
  # score a saved agent result instead of re-running:
  python3 -m evals.run_eval --tenant acme-retail --scenario rds-connection-exhaustion --result-file out.json

Writes a per-run JSON score card to evals/reports/ and prints a summary. Ground truth is read from
each scenario's manifest.yaml (eval-only; never sent to the agent).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

from evals import client, scorer, trace as trace_mod

SRE_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = SRE_ROOT / "synthetic-data" / "tenants"
REPORTS = Path(__file__).resolve().parent / "reports"


def load_manifest(tenant: str, scenario: str) -> dict:
    with open(DATA_ROOT / tenant / "scenarios" / scenario / "manifest.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def registry_matrix() -> list[tuple[str, str]]:
    with open(DATA_ROOT / "registry.yaml", encoding="utf-8") as f:
        reg = yaml.safe_load(f)
    out = []
    for t in reg.get("tenants", []):
        for s in t.get("scenarios", []):
            out.append((t["tenant_id"], s))
    return out


def eval_one(tenant: str, scenario: str, result_file: str | None = None) -> dict:
    manifest = load_manifest(tenant, scenario)
    alarm = manifest.get("alarm", {}).get("name", "") + " — " + manifest.get("title", "")

    if result_file:
        with open(result_file, encoding="utf-8") as f:
            agent = json.load(f)
    else:
        print(f"  invoking agent: tenant={tenant} scenario={scenario} ...", flush=True)
        t0 = time.time()
        agent = client.run_investigation(tenant, scenario, alarm)
        print(f"  investigation returned in {time.time()-t0:.0f}s", flush=True)

    card = scorer.score_run(agent, manifest)
    card["_agent_result"] = {"conclusion": agent.get("conclusion", {}),
                             "hypotheses": [{"id": h.get("id"), "status": h.get("status"),
                                             "statement": h.get("statement", "")[:160]}
                                            for h in agent.get("hypotheses", [])]}
    # CP2: attach trace attribution (step timings, tokens, delegations, errors) for a fresh run.
    sid = agent.get("_eval_session_id")
    if sid and not result_file:
        try:
            # brief wait so spans flush to CloudWatch before we query
            time.sleep(20)
            card["trace"] = trace_mod.attribution_for_session(sid)
        except Exception as e:  # noqa: BLE001
            card["trace"] = {"error": f"attribution failed: {e}"}
    return card


def print_card(card: dict) -> None:
    rc = card["root_cause"]; hyp = card["hypotheses"]; rem = card["remediation"]
    print(f"\n=== {card['tenant_id']} / {card['scenario_id']} ===")
    print(f"  root-cause score     : {rc['score']}  (identified true cause: {rc['identified_true_cause']})")
    print(f"    -> {str(rc['rationale'])[:200]}")
    print(f"  confirm accuracy     : {hyp['confirm_accuracy']}")
    print(f"  red-herring rejection: {hyp['red_herring_rejection']}")
    print(f"  hypothesis overall   : {hyp['overall']}")
    print(f"  remediation score    : {rem['score']}")
    print(f"  confidence           : {card['confidence']}  (calibrated: {card['confidence_calibrated']})")
    for r in hyp["per_hypothesis"]:
        mark = "OK " if r["correct"] else "XX "
        print(f"    {mark}[{r['gt_id']}] want={r['expected']:8} got={r['agent_status']:13} {r['statement'][:70]}")
    tr = card.get("trace")
    if tr and "error" not in tr:
        tok = tr.get("tokens", {})
        print(f"  trace: id={tr.get('trace_id')} spans={tr.get('found_spans')} "
              f"delegations={tr.get('delegation_count')} tokens={tok.get('total')} "
              f"total_ms={tr.get('root_total_ms')}")
        for s in tr.get("steps", []):
            errflag = "  <ERROR>" if s.get("error") else ""
            toks = f" in/out={s.get('input_tokens','-')}/{s.get('output_tokens','-')}" if s.get("input_tokens") else ""
            print(f"      - {s['span']:28} {str(s.get('duration_ms','?')):>8}ms{toks}{errflag}")
        for err in tr.get("errors", []):
            print(f"      ! span error: {err['span']} :: {err['msg'][:120]}")
    elif tr:
        print(f"  trace: {tr.get('error')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant")
    ap.add_argument("--scenario")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--result-file")
    args = ap.parse_args()

    REPORTS.mkdir(parents=True, exist_ok=True)
    pairs = registry_matrix() if args.all else [(args.tenant, args.scenario)]
    if not args.all and (not args.tenant or not args.scenario):
        print("provide --tenant and --scenario, or --all"); sys.exit(2)

    cards = []
    for tenant, scenario in pairs:
        try:
            card = eval_one(tenant, scenario, args.result_file)
            print_card(card)
            cards.append(card)
        except Exception as e:  # noqa: BLE001 - keep going across the matrix
            print(f"  ERROR evaluating {tenant}/{scenario}: {e}", flush=True)
            cards.append({"tenant_id": tenant, "scenario_id": scenario, "error": str(e)})

    ts = time.strftime("%Y%m%d-%H%M%S")
    out = REPORTS / f"eval-{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"runs": cards}, f, indent=2)

    # aggregate
    ok = [c for c in cards if "error" not in c]
    def avg(key_path):
        vals = []
        for c in ok:
            node = c
            for k in key_path:
                node = (node or {}).get(k) if isinstance(node, dict) else None
            if isinstance(node, (int, float)):
                vals.append(node)
        return round(sum(vals) / len(vals), 3) if vals else None
    print("\n==================== AGGREGATE ====================")
    print(f"  scenarios scored       : {len(ok)}/{len(cards)}")
    print(f"  avg root-cause score   : {avg(['root_cause','score'])}")
    print(f"  avg confirm accuracy   : {avg(['hypotheses','confirm_accuracy'])}")
    print(f"  avg red-herring reject : {avg(['hypotheses','red_herring_rejection'])}")
    print(f"  avg remediation score  : {avg(['remediation','score'])}")
    print(f"  report: {out}")


if __name__ == "__main__":
    main()
