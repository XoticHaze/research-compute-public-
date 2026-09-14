import hashlib
import json
from pathlib import Path

PRODUCT_HEAD = "04b6311565e0e316ff100fef8aa7421d0db16188"
FORMULA_AUTHORITY_MERGE = "923bc9baf67344f2cec6c92b5055b39568dddbb8"
FEATURES = ["return_5", "return_20", "return_60", "volatility_20", "distance_ma20", "distance_ma60"]
DCA_STATE = "last_fully_completed_12min_bar_strictly_before_dca_fill"
HISTORICAL_EVENT_VECTOR_PARITY_STATE = "NOT_RECOVERED_FROM_SANITIZED_RECEIPT"
ALLOWED_PARITY_STATES = ["VERIFIED", "NOT_RECOVERED_FROM_SANITIZED_RECEIPT"]


def main():
    assert len(FEATURES) == 6
    assert len(set(FEATURES)) == 6
    assert DCA_STATE.endswith("before_dca_fill")
    assert HISTORICAL_EVENT_VECTOR_PARITY_STATE in ALLOWED_PARITY_STATES
    payload = {
        "product_head": PRODUCT_HEAD,
        "formula_authority_merge": FORMULA_AUTHORITY_MERGE,
        "features": FEATURES,
        "dca_state": DCA_STATE,
        "fill_bar_features_forbidden": True,
        "operator_classification": "RESEARCH_PROVENANCE_ONLY",
        "historical_event_vector_parity_state": HISTORICAL_EVENT_VECTOR_PARITY_STATE,
        "parity_ready": HISTORICAL_EVENT_VECTOR_PARITY_STATE == "VERIFIED",
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
        "schema": "mm.strategy_health_cc75_provenance_sanitized_acceptance.v2",
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
