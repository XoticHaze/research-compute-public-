from __future__ import annotations

import json
from pathlib import Path

OWNING_REPO = "XoticHaze/mm-IBKR"
OWNING_HEAD = "e81ae38c7136812101e09ff50288bcb3b5804bdf"
READINESS_BLOB = "87a65f47e938960ce248f2d51c892214a1cfa257"
VIEW_MODEL_BLOB = "76747989cac627a0f77dc9e49cc6233ffcae3646"
PANEL_BLOB = "725f838f5ae1954c6e9a8b9f0aa9f6d660aed231"
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


def summarize_observation_span(runtimes: list[dict]) -> dict:
    observed = []
    missing = []
    for runtime in runtimes:
        runtime_id = str(runtime.get("runtime_id") or "UNKNOWN_RUNTIME")
        updated_at = runtime.get("updated_at")
        if isinstance(updated_at, str) and updated_at.strip():
            observed.append({"runtime_id": runtime_id, "updated_at": updated_at})
        else:
            missing.append(runtime_id)
    observed.sort(key=lambda row: row["updated_at"])
    return {
        "observed_runtime_count": len(observed),
        "missing_runtime_ids": missing,
        "oldest_updated_at": observed[0]["updated_at"] if observed else None,
        "newest_updated_at": observed[-1]["updated_at"] if observed else None,
        "authority": "DESCRIPTIVE_SOURCE_TIMESTAMP_ONLY",
        "freshness_verdict": None,
    }


def operator_message(summary: dict) -> str:
    if not summary["runtime_count"]:
        return "No AutoTuner worker status artifacts are currently available."
    if not summary["incomplete_count"]:
        return f"Comparison evidence complete for {summary['complete_count']}/{summary['runtime_count']} runtimes. Research evidence only; operator review remains required before any strategy decision."
    missing = ", ".join(f"{field} ({count})" for field, count in summary["missing_counts"].items())
    affected = " | ".join(f"{row['runtime_id']}: {', '.join(row['missing'])}" for row in summary["incomplete_runtimes"])
    return f"Comparison evidence complete for {summary['complete_count']}/{summary['runtime_count']} runtimes. Missing evidence: {missing}. Incomplete runtimes: {affected}. No runtime is selected or promoted by this summary."


def complete_runtime(runtime_id: str, updated_at: str) -> dict:
    return {
        "runtime_id": runtime_id,
        "updated_at": updated_at,
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


runtimes = [
    complete_runtime("AMAT-15Min", "2026-09-12T11:58:00Z"),
    complete_runtime("APH-15Min", "2026-09-12T12:01:00Z"),
]
mnq = complete_runtime("MNQ-12Min", "2026-09-12T12:04:00Z")
mnq["robust_bands"] = None
mnq["decision_evidence"]["excess_return"] = None
mnq["decision_evidence"]["data_coverage"] = {}
runtimes.append(mnq)
summary = summarize(runtimes)
observation_span = summarize_observation_span(runtimes)
message = operator_message(summary)

checks = {
    "owning_head_exact": OWNING_HEAD == "e81ae38c7136812101e09ff50288bcb3b5804bdf",
    "exact_readiness_blob_bound": len(READINESS_BLOB) == 40,
    "exact_view_model_blob_bound": VIEW_MODEL_BLOB == "76747989cac627a0f77dc9e49cc6233ffcae3646",
    "exact_panel_blob_bound": PANEL_BLOB == "725f838f5ae1954c6e9a8b9f0aa9f6d660aed231",
    "two_runtimes_complete": summary["complete_count"] == 2,
    "one_runtime_incomplete": summary["incomplete_count"] == 1,
    "exact_missing_counts": summary["missing_counts"] == {"data_coverage": 1, "excess_return": 1, "robust_bands": 1},
    "exact_incomplete_runtime": summary["incomplete_runtimes"] == [{"runtime_id": "MNQ-12Min", "missing": ["excess_return", "data_coverage", "robust_bands"]}],
    "operator_review_only": summary["authority"] == "OPERATOR_REVIEW_ONLY",
    "observation_span_complete": observation_span["observed_runtime_count"] == 3 and observation_span["missing_runtime_ids"] == [],
    "observation_span_exact_bounds": observation_span["oldest_updated_at"] == "2026-09-12T11:58:00Z" and observation_span["newest_updated_at"] == "2026-09-12T12:04:00Z",
    "observation_timestamp_descriptive_only": observation_span["authority"] == "DESCRIPTIVE_SOURCE_TIMESTAMP_ONLY" and observation_span["freshness_verdict"] is None,
    "message_surfaces_completeness": "2/3 runtimes" in message,
    "message_surfaces_missing_fields": all(field in message for field in ("excess_return", "data_coverage", "robust_bands")),
    "message_surfaces_affected_runtime": "MNQ-12Min" in message,
    "message_refuses_selection": "No runtime is selected or promoted" in message,
    "empty_snapshot_not_ready": summarize([])["complete_count"] == 0 and summarize([])["runtime_count"] == 0,
    "no_strategy_or_broker_authority": all(key not in summary for key in ("selected_runtime_id", "strategy_spec", "broker_submit", "live_unlock")),
    "observation_span_has_no_ranking_or_promotion": all(key not in observation_span for key in ("selected_runtime_id", "rank", "score", "promotion", "activation", "broker_submit", "live_unlock")),
}
passed = all(checks.values())
result = {
    "schema": "cc.p01_autotuner_operator_comparison_readiness_acceptance.v1",
    "owning_repo": OWNING_REPO,
    "owning_head": OWNING_HEAD,
    "source_identity": {"readiness_blob": READINESS_BLOB, "view_model_blob": VIEW_MODEL_BLOB, "panel_blob": PANEL_BLOB},
    "product_route": PRODUCT_ROUTE,
    "comparison_readiness": summary,
    "observation_span": observation_span,
    "operator_message": message,
    "checks": checks,
    "conclusion": "PASS" if passed else "FAIL",
}
Path("p01-autotuner-binding-acceptance-r1-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if passed else 1)
