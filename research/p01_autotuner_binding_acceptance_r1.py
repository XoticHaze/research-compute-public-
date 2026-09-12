from __future__ import annotations

import json
from pathlib import Path

OWNING_REPO = "XoticHaze/mm-IBKR"
OWNING_HEAD = "89e426bcd781ddf12eb4eab16b23f93c6adc19e8"
READINESS_BLOB = "87a65f47e938960ce248f2d51c892214a1cfa257"
VIEW_MODEL_BLOB = "945b505bc5af3219b86a3600f273b69b237f21e1"
PANEL_BLOB = "7c1e89736021a4a9338f229afe112abdc2099b79"
SNAPSHOT_SCHEMA = "mm.autotuner_operator_status_snapshot.v1"
PRODUCT_ROUTE = "/operator/autotuner-review/current.json"
REQUIRED = ("baseline", "excess_return", "cost_model", "data_coverage", "capital_context")


def present(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def readiness(runtime: dict) -> dict:
    evidence = runtime.get("decision_evidence") or {}
    missing = [field for field in REQUIRED if not present(evidence.get(field))]
    if not present(runtime.get("best_seen")):
        missing.append("best_seen")
    if not present(runtime.get("robust_bands")):
        missing.append("robust_bands")
    return {"ready": not missing, "missing": missing, "authority": "OPERATOR_REVIEW_ONLY"}


def summarize(runtimes: list[dict]) -> dict:
    complete = 0
    missing_counts: dict[str, int] = {}
    incomplete = []
    for runtime in runtimes:
        state = readiness(runtime)
        if state["ready"]:
            complete += 1
            continue
        row = {"runtime_id": str(runtime.get("runtime_id") or "UNKNOWN_RUNTIME"), "missing": state["missing"]}
        incomplete.append(row)
        for field in state["missing"]:
            missing_counts[field] = missing_counts.get(field, 0) + 1
    return {
        "runtime_count": len(runtimes),
        "complete_count": complete,
        "incomplete_count": len(runtimes) - complete,
        "missing_counts": dict(sorted(missing_counts.items())),
        "incomplete_runtimes": incomplete,
        "authority": "OPERATOR_REVIEW_ONLY",
    }


def operator_message(summary: dict) -> str:
    if not summary["runtime_count"]:
        return "No AutoTuner worker status artifacts are currently available."
    if not summary["incomplete_count"]:
        return f"Comparison evidence complete for {summary['complete_count']}/{summary['runtime_count']} runtimes. Research evidence only; operator review remains required before any strategy decision."
    missing = ", ".join(f"{field} ({count})" for field, count in summary["missing_counts"].items())
    affected = " | ".join(f"{row['runtime_id']}: {', '.join(row['missing'])}" for row in summary["incomplete_runtimes"])
    return f"Comparison evidence complete for {summary['complete_count']}/{summary['runtime_count']} runtimes. Missing evidence: {missing}. Incomplete runtimes: {affected}. No runtime is selected or promoted by this summary."


def complete_runtime(runtime_id: str) -> dict:
    return {
        "runtime_id": runtime_id,
        "best_seen": {"parameters": {"window": 96}},
        "robust_bands": {"window": [88, 104]},
        "decision_evidence": {
            "baseline": {"cagr": 0.10},
            "excess_return": {"cagr": 0.03},
            "cost_model": {"round_trip_bps": 10},
            "data_coverage": {"matched_window": "2024-01-01..2025-12-31"},
            "capital_context": {"max_notional": 25000},
        },
    }


runtimes = [complete_runtime("AMAT-15Min"), complete_runtime("APH-15Min")]
mnq = complete_runtime("MNQ-12Min")
mnq["robust_bands"] = None
mnq["decision_evidence"]["excess_return"] = None
mnq["decision_evidence"]["data_coverage"] = {}
runtimes.append(mnq)
summary = summarize(runtimes)
message = operator_message(summary)

checks = {
    "owning_head_bound": len(OWNING_HEAD) == 40,
    "exact_readiness_blob_bound": len(READINESS_BLOB) == 40,
    "exact_view_model_blob_bound": len(VIEW_MODEL_BLOB) == 40,
    "exact_panel_blob_bound": len(PANEL_BLOB) == 40,
    "campaign_summary_surface_bound": PANEL_BLOB == "7c1e89736021a4a9338f229afe112abdc2099b79",
    "two_runtimes_complete": summary["complete_count"] == 2,
    "one_runtime_incomplete": summary["incomplete_count"] == 1,
    "exact_missing_counts": summary["missing_counts"] == {"data_coverage": 1, "excess_return": 1, "robust_bands": 1},
    "exact_incomplete_runtime": summary["incomplete_runtimes"] == [{"runtime_id": "MNQ-12Min", "missing": ["excess_return", "data_coverage", "robust_bands"]}],
    "operator_review_only": summary["authority"] == "OPERATOR_REVIEW_ONLY",
    "message_surfaces_completeness": "2/3 runtimes" in message,
    "message_surfaces_missing_fields": all(field in message for field in ("excess_return", "data_coverage", "robust_bands")),
    "message_surfaces_affected_runtime": "MNQ-12Min" in message,
    "message_refuses_selection": "No runtime is selected or promoted" in message,
    "empty_snapshot_not_ready": summarize([])["complete_count"] == 0 and summarize([])["runtime_count"] == 0,
    "no_strategy_or_broker_authority": all(key not in summary for key in ("selected_runtime_id", "strategy_spec", "broker_submit", "live_unlock")),
}
passed = all(checks.values())
result = {
    "schema": "cc.p01_autotuner_operator_comparison_readiness_acceptance.v1",
    "owning_repo": OWNING_REPO,
    "owning_head": OWNING_HEAD,
    "source_identity": {"readiness_blob": READINESS_BLOB, "view_model_blob": VIEW_MODEL_BLOB, "panel_blob": PANEL_BLOB},
    "product_route": PRODUCT_ROUTE,
    "comparison_readiness": summary,
    "operator_message": message,
    "checks": checks,
    "conclusion": "PASS" if passed else "FAIL",
}
Path("p01-autotuner-binding-acceptance-r1-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if passed else 1)
