#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "release_acceptance" / "foundry_terminal_claims_20260912.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")

EXPECTED_STATE_BY_ID = {
    "MR_PKW_BUYBACK_ALPHA_20260912_R1": "REJECTED_RESIDUAL_ALPHA_ALL_FROZEN_GATES_FAILED_NO_RESCUE",
    "MR_PRWCX_ACTIVE_BALANCED_ALPHA_20260912_R1": "REJECTED_RESIDUAL_ALPHA_MAGNITUDE_AND_PERSISTENCE_FAILED_NO_RESCUE",
    "MR_IPO_EVENT_ALPHA_20260912_R1": "REJECTED_RESIDUAL_ALPHA_ALL_FROZEN_GATES_FAILED_NO_RESCUE",
    "PIT_FUNDAMENTAL_EVENT_ROA_R1": "REJECT_NO_FORWARD_ROA_SIGN_SIGNAL_NO_PARAMETER_RESCUE",
    "PIT_FUNDAMENTAL_EVENT_CASH_CONVERSION_R1": "REJECT_NO_FORWARD_CASH_CONVERSION_BROAD_SIGNAL_NO_PARAMETER_RESCUE",
    "PIT_QUARTERLY_EARNINGS_ACCELERATION_R1": "REJECT_NO_PARAMETER_RESCUE",
    "YAHOO_EPS_SURPRISE_SIGN_R1": "REJECT_NO_PARAMETER_RESCUE",
    "PIT_INSIDER_OPEN_MARKET_PURCHASE_R1": "REJECT_NO_PARAMETER_RESCUE",
    "VIX_CURVE_FUND_STRESS_GATE_R1": "REJECT_NO_PARAMETER_RESCUE",
    "P546_SLOOS_CREDIT_STANDARDS_R1": "PARKED_REJECT_NO_PARAMETER_RESCUE",
    "IMTM_INTERNATIONAL_MOMENTUM_TRANSPORT_R1": "RESEARCH_ONLY_REJECTED_NO_RESCUE",
}
EXPECTED_BY_REVISION = {
    "20260912-r2": {"MR_PKW_BUYBACK_ALPHA_20260912_R1", "MR_PRWCX_ACTIVE_BALANCED_ALPHA_20260912_R1", "MR_IPO_EVENT_ALPHA_20260912_R1"},
    "20260912-r3": {"MR_PKW_BUYBACK_ALPHA_20260912_R1", "MR_PRWCX_ACTIVE_BALANCED_ALPHA_20260912_R1", "MR_IPO_EVENT_ALPHA_20260912_R1", "PIT_FUNDAMENTAL_EVENT_ROA_R1", "PIT_FUNDAMENTAL_EVENT_CASH_CONVERSION_R1"},
    "20260912-r4": set(EXPECTED_STATE_BY_ID) - {"YAHOO_EPS_SURPRISE_SIGN_R1", "PIT_INSIDER_OPEN_MARKET_PURCHASE_R1", "VIX_CURVE_FUND_STRESS_GATE_R1", "P546_SLOOS_CREDIT_STANDARDS_R1", "IMTM_INTERNATIONAL_MOMENTUM_TRANSPORT_R1"},
    "20260912-r5": set(EXPECTED_STATE_BY_ID) - {"PIT_INSIDER_OPEN_MARKET_PURCHASE_R1", "VIX_CURVE_FUND_STRESS_GATE_R1", "P546_SLOOS_CREDIT_STANDARDS_R1", "IMTM_INTERNATIONAL_MOMENTUM_TRANSPORT_R1"},
    "20260912-r6": set(EXPECTED_STATE_BY_ID) - {"VIX_CURVE_FUND_STRESS_GATE_R1", "P546_SLOOS_CREDIT_STANDARDS_R1", "IMTM_INTERNATIONAL_MOMENTUM_TRANSPORT_R1"},
    "20260913-r7": set(EXPECTED_STATE_BY_ID) - {"P546_SLOOS_CREDIT_STANDARDS_R1", "IMTM_INTERNATIONAL_MOMENTUM_TRANSPORT_R1"},
    "20260913-r8": set(EXPECTED_STATE_BY_ID) - {"IMTM_INTERNATIONAL_MOMENTUM_TRANSPORT_R1"},
    "20260913-r9": set(EXPECTED_STATE_BY_ID),
}


def validate_execution(execution: dict) -> None:
    assert isinstance(execution["source_run_id"], int) and execution["source_run_id"] > 0
    assert isinstance(execution["source_job_id"], int) and execution["source_job_id"] > 0
    assert isinstance(execution["artifact_id"], int) and execution["artifact_id"] > 0
    assert HEX40.fullmatch(execution["source_head_sha"])
    assert HEX64.fullmatch(execution["artifact_sha256"])


def main() -> None:
    payload = json.loads(BINDING.read_text(encoding="utf-8"))
    assert payload["schema"] == "research_compute_public.foundry_terminal_claim_acceptance.v1"
    revision = payload["acceptance_revision"]
    assert revision in EXPECTED_BY_REVISION
    claims = payload["claims"]
    ids = {claim["workload_id"] for claim in claims}
    assert len(claims) == len(ids)
    assert ids == EXPECTED_BY_REVISION[revision]
    for claim in claims:
        workload_id = claim["workload_id"]
        assert HEX40.fullmatch(claim["foundry_commit"])
        assert claim["semantic_state"] == EXPECTED_STATE_BY_ID[workload_id]
        if "source_executions" in claim:
            executions = claim["source_executions"]
            assert workload_id == "P546_SLOOS_CREDIT_STANDARDS_R1"
            assert isinstance(executions, list) and len(executions) == 2
            for execution in executions:
                validate_execution(execution)
            assert [e["source_run_id"] for e in executions] == [34728470157, 34728561691]
        else:
            validate_execution(claim)

    authority = payload["required_authority"]
    assert authority["authority"] == "RESEARCH_ONLY"
    for key in ("automatic_action", "portfolio_ranking_authority", "allocation_authority", "promotion_authority", "runtime_authority", "broker_authority", "live_trading"):
        assert authority[key] is False, key

    print(json.dumps({
        "accepted": True,
        "acceptance_revision": revision,
        "claim_count": len(claims),
        "workload_ids": sorted(ids),
        "multi_source_claims": sorted(c["workload_id"] for c in claims if "source_executions" in c),
        "authority": "RESEARCH_ONLY",
        "live_trading": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
