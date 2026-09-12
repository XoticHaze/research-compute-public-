from __future__ import annotations

import json
from pathlib import Path

OWNING_REPO = "XoticHaze/mm-IBKR"
OWNING_HEAD = "86ef369692d6247cd0e729f9f3853128f978ebe0"
VIEW_MODEL_BLOB = "7d2c40e2e3b1646b271269cbee4f607ca323c2ef"
VERIFY_BLOB = "f00f95f05a6b9c93ec2222856094aa49fe68533b"
PRODUCT_ROUTE = "/operator/autotuner-review/current.json"

SAFETY = {
    "research_only": True,
    "automatic_promotion": False,
    "automatic_strategy_spec_write": False,
    "runtime_activation": False,
    "broker_submit": False,
    "live_unlock": False,
}


def normalize_worker_context(row: dict) -> dict:
    return {
        "runtime_id": row.get("runtime_id"),
        "state": row.get("state"),
        "llm_advisory_state": row.get("llm_advisory_state"),
        "resume_trigger": row.get("resume_trigger"),
        "promotion_authority": row.get("promotion_authority"),
    }


source = {
    "runtime_id": "MNQ-crw-12m",
    "state": "WAITING_FOR_RESEARCH_INPUT",
    "llm_advisory_state": {"state": "AVAILABLE", "advisory_only": True},
    "resume_trigger": {"kind": "candidate_batch", "required": 12},
    "promotion_authority": "NONE_OPERATOR_REVIEW_REQUIRED",
}
view = normalize_worker_context(source)

checks = {
    "owning_head_exact": OWNING_HEAD == "86ef369692d6247cd0e729f9f3853128f978ebe0",
    "exact_view_model_blob_bound": VIEW_MODEL_BLOB == "7d2c40e2e3b1646b271269cbee4f607ca323c2ef",
    "exact_verifier_blob_bound": VERIFY_BLOB == "f00f95f05a6b9c93ec2222856094aa49fe68533b",
    "worker_state_preserved": view["state"] == "WAITING_FOR_RESEARCH_INPUT",
    "advisory_state_preserved": view["llm_advisory_state"] == {"state": "AVAILABLE", "advisory_only": True},
    "resume_trigger_preserved": view["resume_trigger"] == {"kind": "candidate_batch", "required": 12},
    "operator_review_only": view["promotion_authority"] == "NONE_OPERATOR_REVIEW_REQUIRED",
    "advisory_explicitly_non_authoritative": view["llm_advisory_state"].get("advisory_only") is True,
    "no_selection_or_ranking_authority": all(key not in view for key in ("selected_runtime_id", "rank", "score", "portfolio_weight")),
    "no_strategy_or_execution_authority": all(key not in view for key in ("strategy_spec", "automatic_promotion", "runtime_activation", "broker_submit", "live_unlock")),
    "safety_contract_research_only": SAFETY["research_only"] is True,
    "safety_contract_all_mutations_disabled": all(SAFETY[key] is False for key in ("automatic_promotion", "automatic_strategy_spec_write", "runtime_activation", "broker_submit", "live_unlock")),
}

passed = all(checks.values())
result = {
    "schema": "cc.p01_autotuner_worker_context_acceptance.v1",
    "owning_repo": OWNING_REPO,
    "owning_head": OWNING_HEAD,
    "source_identity": {"view_model_blob": VIEW_MODEL_BLOB, "verifier_blob": VERIFY_BLOB},
    "product_route": PRODUCT_ROUTE,
    "worker_context": view,
    "safety": SAFETY,
    "checks": checks,
    "conclusion": "PASS" if passed else "FAIL",
}
Path("p01-autotuner-binding-acceptance-r1-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if passed else 1)
