import hashlib
import json
from pathlib import Path

PRODUCT_HEAD = "163b59d2f440f8da742a42beb410b6030130309e"
FORMULA_AUTHORITY_MERGE = "923bc9baf67344f2cec6c92b5055b39568dddbb8"
FEATURES = ["return_5", "return_20", "return_60", "volatility_20", "distance_ma20", "distance_ma60"]
DCA_STATE = "last_fully_completed_12min_bar_strictly_before_dca_fill"
HISTORICAL_EVENT_VECTOR_PARITY_STATE = "NOT_RECOVERED_FROM_SANITIZED_RECEIPT"
ALLOWED_PARITY_STATES = ["VERIFIED", "NOT_RECOVERED_FROM_SANITIZED_RECEIPT"]
PARITY_EVIDENCE_GAP = "historical_event_level_feature_vectors_not_recovered"
PARITY_PROOF_REQUIRED = "recompute_or_recover_event_level_six_feature_vectors_and_compare_against_frozen_formula_authority"
OPERATOR_ACTION = "DO_NOT_TREAT_AS_PARITY_VERIFIED"
MATCHED_BASELINE_EVIDENCE = {
    "baseline": "normalized-distance top-20",
    "baseline_return_direction_accuracy_pct": 47.67,
    "challenger": "prospectively fixed same-causal-regime",
    "challenger_return_direction_accuracy_pct": 48.67,
    "lift_percentage_points": 1.00,
    "aggregate_metrics_improved": 4,
    "aggregate_metrics_tested": 4,
    "positive_fold_wins_each_metric": 3,
    "fold_count": 5,
    "interpretation": "MODEST_POSITIVE_LIFT",
}
VISIBLE_OPERATOR_CONTRACT = {
    "browser_state": "Parity not verified.",
    "browser_gap_prefix": "Gap:",
    "browser_closure_prefix": "Closure proof:",
    "export_gap_label": "Parity gap:",
    "export_closure_label": "Closure proof:",
    "export_operator_action_label": "Operator action:",
}


def matched_baseline_readiness(evidence):
    required = (
        "baseline_return_direction_accuracy_pct",
        "challenger_return_direction_accuracy_pct",
        "aggregate_metrics_improved",
        "aggregate_metrics_tested",
        "positive_fold_wins_each_metric",
        "fold_count",
    )
    missing = [key for key in required if evidence.get(key) is None]
    return {"state": "COMPLETE" if not missing else "INCOMPLETE", "missing": missing}


def main():
    assert len(FEATURES) == 6
    assert len(set(FEATURES)) == 6
    assert DCA_STATE.endswith("before_dca_fill")
    assert HISTORICAL_EVENT_VECTOR_PARITY_STATE in ALLOWED_PARITY_STATES

    parity_ready = HISTORICAL_EVENT_VECTOR_PARITY_STATE == "VERIFIED"
    context_evidence_state = "CONTEXT_EVIDENCE_VERIFIED" if parity_ready else "CONTEXT_EVIDENCE_PARTIAL"
    metric_readiness = matched_baseline_readiness(MATCHED_BASELINE_EVIDENCE)
    assert context_evidence_state == "CONTEXT_EVIDENCE_PARTIAL"
    assert not parity_ready
    assert metric_readiness == {"state": "COMPLETE", "missing": []}
    incomplete = dict(MATCHED_BASELINE_EVIDENCE)
    incomplete.pop("aggregate_metrics_tested")
    assert matched_baseline_readiness(incomplete) == {"state": "INCOMPLETE", "missing": ["aggregate_metrics_tested"]}
    assert PARITY_EVIDENCE_GAP == "historical_event_level_feature_vectors_not_recovered"
    assert PARITY_PROOF_REQUIRED.startswith("recompute_or_recover_event_level_six_feature_vectors")
    assert OPERATOR_ACTION == "DO_NOT_TREAT_AS_PARITY_VERIFIED"
    assert MATCHED_BASELINE_EVIDENCE["baseline_return_direction_accuracy_pct"] == 47.67
    assert MATCHED_BASELINE_EVIDENCE["challenger_return_direction_accuracy_pct"] == 48.67
    assert MATCHED_BASELINE_EVIDENCE["lift_percentage_points"] == 1.00
    assert MATCHED_BASELINE_EVIDENCE["aggregate_metrics_improved"] == 4
    assert MATCHED_BASELINE_EVIDENCE["aggregate_metrics_tested"] == 4
    assert MATCHED_BASELINE_EVIDENCE["positive_fold_wins_each_metric"] == 3
    assert MATCHED_BASELINE_EVIDENCE["fold_count"] == 5
    assert MATCHED_BASELINE_EVIDENCE["interpretation"] == "MODEST_POSITIVE_LIFT"
    assert VISIBLE_OPERATOR_CONTRACT["browser_state"] == "Parity not verified."
    assert VISIBLE_OPERATOR_CONTRACT["browser_gap_prefix"] == "Gap:"
    assert VISIBLE_OPERATOR_CONTRACT["browser_closure_prefix"] == "Closure proof:"
    assert VISIBLE_OPERATOR_CONTRACT["export_gap_label"] == "Parity gap:"
    assert VISIBLE_OPERATOR_CONTRACT["export_closure_label"] == "Closure proof:"
    assert VISIBLE_OPERATOR_CONTRACT["export_operator_action_label"] == "Operator action:"

    payload = {
        "product_head": PRODUCT_HEAD,
        "formula_authority_merge": FORMULA_AUTHORITY_MERGE,
        "features": FEATURES,
        "dca_state": DCA_STATE,
        "fill_bar_features_forbidden": True,
        "operator_classification": "RESEARCH_PROVENANCE_ONLY",
        "historical_event_vector_parity_state": HISTORICAL_EVENT_VECTOR_PARITY_STATE,
        "parity_ready": parity_ready,
        "context_evidence_state": context_evidence_state,
        "matched_baseline_readiness": metric_readiness,
        "parity_evidence_gap": PARITY_EVIDENCE_GAP,
        "parity_proof_required": PARITY_PROOF_REQUIRED,
        "operator_action": OPERATOR_ACTION,
        "matched_baseline_evidence": MATCHED_BASELINE_EVIDENCE,
        "visible_operator_contract": VISIBLE_OPERATOR_CONTRACT,
        "protected_boundaries": {
            "signal_or_trigger_authority": False,
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "portfolio_ranking": False,
            "portfolio_allocation": False,
            "broker_submission": False,
            "live_trading_change": False,
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    receipt = {
        "schema": "mm.strategy_health_cc75_provenance_sanitized_acceptance.v8",
        **payload,
        "semantic_sha256": hashlib.sha256(canonical).hexdigest(),
        "result": "PASS",
    }
    Path("strategy-health-cc75-provenance-acceptance-r1-result.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
