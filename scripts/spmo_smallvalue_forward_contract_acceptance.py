import hashlib
import json
from datetime import date


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def validate(contract, as_of):
    assert contract["schema"] == "foundry.research.forward_observation_contract.v1"
    c = contract["candidate"]
    e = contract["eligibility"]
    b = contract["boundaries"]
    assert c["representation"] == "SPMO+IJS"
    assert c["weights"] == {"SPMO": 0.5, "IJS": 0.5}
    assert c["matched_control"] == {"SPY": 0.5, "IJR": 0.5}
    assert abs(sum(c["weights"].values()) - 1.0) < 1e-12
    assert abs(sum(c["matched_control"].values()) - 1.0) < 1e-12
    assert e["required_claim_status"] == "SUPPORTED"
    assert e["automatic_action_allowed"] is False
    for key in ("portfolio_ranking_authority", "portfolio_allocation_authority", "promotion_authority", "runtime_mutation", "broker_authority", "live_trading_authority"):
        assert b[key] is False
    decision = date.fromisoformat(e["first_eligible_decision_boundary"])
    maturity = date.fromisoformat(e["first_maturity_boundary"])
    assert maturity > decision
    state = "READY_TO_FREEZE_DECISION" if as_of >= decision else "WAIT_FOR_DECISION_BOUNDARY"
    return {
        "state": state,
        "decision_emission_allowed": state == "READY_TO_FREEZE_DECISION",
        "contract_sha256": hashlib.sha256(canonical(contract)).hexdigest(),
        "automatic_action_allowed": False,
        "allocation_authority": False,
    }


contract = {
    "schema": "foundry.research.forward_observation_contract.v1",
    "contract_id": "spmo-smallvalue-fixed50-forward-20260910-r1",
    "candidate": {
        "evidence_claim_path": "shared_evidence/claims/p303_p304_spmo_smallvalue_fixed_utility_supported.v1.json",
        "cost_robustness_claim_path": "shared_evidence/claims/p305_spmo_smallvalue_cost_robustness_supported.v1.json",
        "representation": "SPMO+IJS",
        "weights": {"SPMO": 0.5, "IJS": 0.5},
        "matched_control": {"SPY": 0.5, "IJR": 0.5},
        "opportunity_controls": ["SPY", "QQQ"],
        "cadence": "monthly",
        "rebalance": "drift-rebalance-to-fixed-50-50-at-month-boundary",
        "cost_bps_endpoints": [25, 50],
    },
    "eligibility": {"required_claim_status": "SUPPORTED", "required_authority_scope": "RESEARCH_ONLY", "automatic_action_allowed": False, "first_eligible_decision_boundary": "2026-09-30", "first_maturity_boundary": "2026-10-30", "pre_boundary_emission": "FAIL_CLOSED"},
    "receipt_split": {"decision": "immutable before interval", "outcome": "separate after maturity", "anti_leakage": True},
    "scorecard": {"primary": "after-cost matched-control excess", "secondary": ["SPY opportunity cost", "QQQ opportunity cost", "drawdown", "turnover"], "no_cross_candidate_ranking_without_common_sample": True, "no_refit_from_forward_outcomes": True},
    "boundaries": {"research_only": True, "portfolio_ranking_authority": False, "portfolio_allocation_authority": False, "promotion_authority": False, "runtime_mutation": False, "broker_authority": False, "live_trading_authority": False, "prohibited": ["weight tuning", "product substitution", "backfilled decision"]},
}

pre = validate(contract, date(2026, 9, 10))
ready = validate(contract, date(2026, 9, 30))
assert pre["state"] == "WAIT_FOR_DECISION_BOUNDARY"
assert pre["decision_emission_allowed"] is False
assert ready["state"] == "READY_TO_FREEZE_DECISION"
assert ready["decision_emission_allowed"] is True
assert pre["contract_sha256"] == ready["contract_sha256"]
print(json.dumps({"result":"PASS","pre_boundary":pre,"at_boundary":ready}, sort_keys=True))
