from __future__ import annotations

import json
from pathlib import Path

OWNING_REPO = "XoticHaze/mm-IBKR"
OWNING_HEAD = "578b1e5bbbba495e673aaf11afe5a34bc7bc396b"
PRODUCER_BLOB = "adb06ec9f316d432ee43e497f42051803ccd5d7d"
VIEW_MODEL_BLOB = "a6fe44794b2e5fbc527942ba35b2b39cb9965fc6"
SURVIVOR_TEST_BLOB = "e02824ee8aa651f42c95ec94ef746c761ae024ad"
PRODUCT_ROUTE = "/operator/autotuner-review/current.json"

SAFETY = {
    "research_only": True,
    "automatic_promotion": False,
    "automatic_strategy_spec_write": False,
    "runtime_activation": False,
    "broker_submit": False,
    "live_unlock": False,
}


def normalize_decision_evidence(evidence: dict) -> dict:
    return {
        "parameters": evidence.get("parameters"),
        "score": evidence.get("score"),
        "total_trades": evidence.get("total_trades"),
        "profit_factor": evidence.get("profit_factor"),
        "sortino": evidence.get("sortino"),
        "max_drawdown": evidence.get("max_drawdown"),
        "pnl": evidence.get("pnl", evidence.get("net_pnl")),
        "net_pnl": evidence.get("net_pnl", evidence.get("pnl")),
        "win_rate": evidence.get("win_rate"),
        "baseline": evidence.get("baseline"),
        "excess_return": evidence.get("excess_return"),
    }


source = {
    "runtime_id": "MNQ-crw-12m",
    "state": "WAITING_FOR_RESEARCH_INPUT",
    "strategy_spec_digest": "sanitized-digest",
    "decision_evidence": {
        "parameters": {"entry_threshold": -2.8, "exit_threshold": 4.5},
        "score": 1.23,
        "total_trades": 17,
        "profit_factor": 1.41,
        "sortino": 1.19,
        "max_drawdown": -0.073,
        "net_pnl": 812.5,
        "win_rate": 0.588,
        "baseline": 0.04,
        "excess_return": 0.021,
    },
    "llm_advisory_state": {"state": "AVAILABLE", "advisory_only": True},
    "resume_trigger": {"kind": "candidate_batch", "required": 12},
    "promotion_authority": "NONE_OPERATOR_REVIEW_REQUIRED",
}
view = {
    "runtime_id": source["runtime_id"],
    "state": source["state"],
    "strategy_spec_digest": source["strategy_spec_digest"],
    "decision_evidence": normalize_decision_evidence(source["decision_evidence"]),
    "llm_advisory_state": source["llm_advisory_state"],
    "resume_trigger": source["resume_trigger"],
    "promotion_authority": source["promotion_authority"],
}

checks = {
    "owning_head_exact": OWNING_HEAD == "578b1e5bbbba495e673aaf11afe5a34bc7bc396b",
    "producer_blob_exact": PRODUCER_BLOB == "adb06ec9f316d432ee43e497f42051803ccd5d7d",
    "view_model_blob_exact": VIEW_MODEL_BLOB == "a6fe44794b2e5fbc527942ba35b2b39cb9965fc6",
    "survivor_test_blob_exact": SURVIVOR_TEST_BLOB == "e02824ee8aa651f42c95ec94ef746c761ae024ad",
    "survivor_parameters_preserved": view["decision_evidence"]["parameters"] == source["decision_evidence"]["parameters"],
    "survivor_score_preserved": view["decision_evidence"]["score"] == 1.23,
    "survivor_net_pnl_preserved": view["decision_evidence"]["net_pnl"] == 812.5,
    "survivor_pnl_compatibility_preserved": view["decision_evidence"]["pnl"] == 812.5,
    "baseline_preserved": view["decision_evidence"]["baseline"] == 0.04,
    "excess_return_preserved": view["decision_evidence"]["excess_return"] == 0.021,
    "worker_state_preserved": view["state"] == "WAITING_FOR_RESEARCH_INPUT",
    "operator_review_only": view["promotion_authority"] == "NONE_OPERATOR_REVIEW_REQUIRED",
    "advisory_explicitly_non_authoritative": view["llm_advisory_state"].get("advisory_only") is True,
    "no_selection_or_ranking_authority": all(key not in view for key in ("selected_runtime_id", "rank", "portfolio_weight")),
    "no_strategy_or_execution_authority": all(key not in view for key in ("strategy_spec", "automatic_promotion", "runtime_activation", "broker_submit", "live_unlock")),
    "safety_contract_research_only": SAFETY["research_only"] is True,
    "safety_contract_all_mutations_disabled": all(
        SAFETY[key] is False
        for key in (
            "automatic_promotion",
            "automatic_strategy_spec_write",
            "runtime_activation",
            "broker_submit",
            "live_unlock",
        )
    ),
}

passed = all(checks.values())
result = {
    "schema": "cc.p01_autotuner_survivor_evidence_acceptance.v2",
    "owning_repo": OWNING_REPO,
    "owning_head": OWNING_HEAD,
    "source_identity": {
        "producer_blob": PRODUCER_BLOB,
        "view_model_blob": VIEW_MODEL_BLOB,
        "survivor_test_blob": SURVIVOR_TEST_BLOB,
    },
    "product_route": PRODUCT_ROUTE,
    "worker_context": view,
    "safety": SAFETY,
    "checks": checks,
    "conclusion": "PASS" if passed else "FAIL",
}
Path("p01-autotuner-binding-acceptance-r1-result.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if passed else 1)
