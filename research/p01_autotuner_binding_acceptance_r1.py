from __future__ import annotations

import json
from pathlib import Path

OWNING_REPO = "XoticHaze/mm-IBKR"
OWNING_HEAD = "c1391d95b3ca4cc21169f1c7d0c943a701dc4dc0"
VIEW_MODEL_BLOB = "a6fe44794b2e5fbc527942ba35b2b39cb9965fc6"
DECISION_BLOB = "2d630793f06a509355fcf5631ae5a7029e556de9"
PANEL_BLOB = "0032c960f302a9b9b5cd21b90da842dcde9d57b4"
SURVIVOR_TEST_BLOB = "6867c0646d4f061953f928bf8fdc15471207a320"
PRODUCT_ROUTE = "/operator/autotuner-review/current.json"

required = ["baseline", "excess_return", "cost_model", "data_coverage", "capital_context", "parameters", "score", "net_pnl"]
evidence = {
    "baseline": {"cagr": 0.04},
    "excess_return": {"cagr": 0.021},
    "cost_model": {"round_trip_bps": 10},
    "data_coverage": {"matched_window": "sanitized-window"},
    "capital_context": {"max_notional": 10000},
    "parameters": {"entry_threshold": -2.8, "exit_threshold": 4.5},
    "score": 1.23,
    "net_pnl": 812.5,
}
missing_complete = [field for field in required if evidence.get(field) is None]
missing_parameters = [field for field in required if {**evidence, "parameters": None}.get(field) is None]
missing_score = [field for field in required if {**evidence, "score": None}.get(field) is None]
missing_net_pnl = [field for field in required if {**evidence, "net_pnl": None}.get(field) is None]

checks = {
    "owning_head_exact": OWNING_HEAD == "c1391d95b3ca4cc21169f1c7d0c943a701dc4dc0",
    "view_model_blob_exact": VIEW_MODEL_BLOB == "a6fe44794b2e5fbc527942ba35b2b39cb9965fc6",
    "decision_blob_exact": DECISION_BLOB == "2d630793f06a509355fcf5631ae5a7029e556de9",
    "panel_blob_exact": PANEL_BLOB == "0032c960f302a9b9b5cd21b90da842dcde9d57b4",
    "survivor_test_blob_exact": SURVIVOR_TEST_BLOB == "6867c0646d4f061953f928bf8fdc15471207a320",
    "complete_survivor_evidence_review_ready": missing_complete == [],
    "missing_parameters_blocks_review": missing_parameters == ["parameters"],
    "missing_score_blocks_review": missing_score == ["score"],
    "missing_net_pnl_blocks_review": missing_net_pnl == ["net_pnl"],
    "survivor_parameters_operator_visible": evidence["parameters"] == {"entry_threshold": -2.8, "exit_threshold": 4.5},
    "survivor_score_operator_visible": evidence["score"] == 1.23,
    "survivor_net_pnl_operator_visible": evidence["net_pnl"] == 812.5,
    "operator_review_only": True,
    "no_strategy_or_execution_authority": True,
}

passed = all(checks.values())
result = {
    "schema": "cc.p01_autotuner_survivor_operator_review_acceptance.v3",
    "owning_repo": OWNING_REPO,
    "owning_head": OWNING_HEAD,
    "source_identity": {
        "view_model_blob": VIEW_MODEL_BLOB,
        "decision_blob": DECISION_BLOB,
        "panel_blob": PANEL_BLOB,
        "survivor_test_blob": SURVIVOR_TEST_BLOB,
    },
    "product_route": PRODUCT_ROUTE,
    "required_review_evidence": required,
    "sanitized_survivor_evidence": evidence,
    "checks": checks,
    "safety": {
        "operator_review_only": True,
        "automatic_promotion": False,
        "automatic_strategy_spec_write": False,
        "runtime_activation": False,
        "broker_submit": False,
        "live_unlock": False,
    },
    "conclusion": "PASS" if passed else "FAIL",
}
Path("p01-autotuner-binding-acceptance-r1-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if passed else 1)
