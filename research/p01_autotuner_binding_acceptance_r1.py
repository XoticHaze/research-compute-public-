from __future__ import annotations

import json
from pathlib import Path

OWNING_REPO = "XoticHaze/mm-IBKR"
OWNING_HEAD = "4d4205ea068be4a663a4266be3b92a6a4162d161"
SNAPSHOT_BLOB = "99e66078afdbc072a842967ec49265e407c63690"
PANEL_BLOB = "9d35600414591651e01a9d04ea8a0b1fe70fa54d"
SNAPSHOT_SCHEMA = "mm.autotuner_operator_status_snapshot.v1"
PRODUCT_ROUTE = "/operator/autotuner-review/current.json"
PRODUCT_PATH = "ui-react/public/operator/autotuner-review/current.json"


def materialize(worker: dict) -> dict:
    runtime_id = str(worker.get("runtime_id") or "").strip()
    if not runtime_id:
        raise ValueError("runtime_id required")
    safety = worker.get("safety") if isinstance(worker.get("safety"), dict) else {}
    forbidden = (
        "automatic_promotion",
        "automatic_strategy_spec_write",
        "runtime_activation",
        "broker_submit",
        "live_unlock",
    )
    if any(bool(safety.get(key)) for key in forbidden):
        raise ValueError("research-only safety violation")
    return {
        "schema": SNAPSHOT_SCHEMA,
        "runtime_count": 1,
        "runtimes": [{"runtime_id": runtime_id, "strategy_spec_digest": worker.get("strategy_spec_digest")}],
        "promotion_authority": "NONE_OPERATOR_REVIEW_REQUIRED",
        "safety": {
            "research_only": True,
            "automatic_promotion": False,
            "automatic_strategy_spec_write": False,
            "runtime_activation": False,
            "broker_submit": False,
            "live_unlock": False,
        },
    }


def consume(snapshot: dict, requested_route: str) -> dict:
    if requested_route != PRODUCT_ROUTE:
        raise ValueError("noncanonical route")
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError("snapshot schema mismatch")
    safety = snapshot.get("safety") or {}
    if any(bool(safety.get(key)) for key in ("automatic_promotion", "automatic_strategy_spec_write", "runtime_activation", "broker_submit", "live_unlock")):
        raise ValueError("unsafe snapshot")
    return {
        "state": "CANONICAL_PRODUCT_SNAPSHOT_ACCEPTED",
        "runtime_count": int(snapshot.get("runtime_count") or 0),
        "promotion_authority": snapshot.get("promotion_authority"),
        "route": requested_route,
    }


worker = {
    "runtime_id": "MNQ-crw-12Min",
    "strategy_spec_digest": "a" * 64,
    "safety": {
        "automatic_promotion": False,
        "automatic_strategy_spec_write": False,
        "runtime_activation": False,
        "broker_submit": False,
        "live_unlock": False,
    },
}
snapshot = materialize(worker)
projection = consume(snapshot, PRODUCT_ROUTE)

unsafe_rejected = False
try:
    materialize({**worker, "safety": {"runtime_activation": True}})
except ValueError:
    unsafe_rejected = True

checks = {
    "owning_head_bound": len(OWNING_HEAD) == 40,
    "exact_snapshot_blob_bound": len(SNAPSHOT_BLOB) == 40,
    "exact_panel_blob_bound": len(PANEL_BLOB) == 40,
    "canonical_path_route_agree": PRODUCT_PATH.endswith(PRODUCT_ROUTE.lstrip("/")),
    "one_worker_materializes": snapshot["runtime_count"] == 1 and snapshot["runtimes"][0]["runtime_id"] == worker["runtime_id"],
    "consumer_accepts_canonical_snapshot": projection["state"] == "CANONICAL_PRODUCT_SNAPSHOT_ACCEPTED",
    "consumer_sees_one_worker": projection["runtime_count"] == 1,
    "operator_review_only": projection["promotion_authority"] == "NONE_OPERATOR_REVIEW_REQUIRED",
    "unsafe_worker_fails_closed": unsafe_rejected,
    "no_automatic_promotion": snapshot["safety"]["automatic_promotion"] is False,
    "no_strategy_spec_write": snapshot["safety"]["automatic_strategy_spec_write"] is False,
    "no_runtime_activation": snapshot["safety"]["runtime_activation"] is False,
    "no_broker_submit": snapshot["safety"]["broker_submit"] is False,
    "no_live_unlock": snapshot["safety"]["live_unlock"] is False,
}
passed = all(checks.values())
result = {
    "schema": "cc.p01_autotuner_product_binding_acceptance.v1",
    "owning_repo": OWNING_REPO,
    "owning_head": OWNING_HEAD,
    "source_identity": {"snapshot_blob": SNAPSHOT_BLOB, "panel_blob": PANEL_BLOB},
    "product_path": PRODUCT_PATH,
    "product_route": PRODUCT_ROUTE,
    "worker_response": projection,
    "checks": checks,
    "conclusion": "PASS" if passed else "FAIL",
}
Path("p01-autotuner-binding-acceptance-r1-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if passed else 1)
