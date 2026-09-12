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
}
EXPECTED_BY_REVISION = {
    "20260912-r2": {
        "MR_PKW_BUYBACK_ALPHA_20260912_R1",
        "MR_PRWCX_ACTIVE_BALANCED_ALPHA_20260912_R1",
        "MR_IPO_EVENT_ALPHA_20260912_R1",
    },
    "20260912-r3": {
        "MR_PKW_BUYBACK_ALPHA_20260912_R1",
        "MR_PRWCX_ACTIVE_BALANCED_ALPHA_20260912_R1",
        "MR_IPO_EVENT_ALPHA_20260912_R1",
        "PIT_FUNDAMENTAL_EVENT_ROA_R1",
        "PIT_FUNDAMENTAL_EVENT_CASH_CONVERSION_R1",
    },
    "20260912-r4": set(EXPECTED_STATE_BY_ID) - {"YAHOO_EPS_SURPRISE_SIGN_R1", "PIT_INSIDER_OPEN_MARKET_PURCHASE_R1"},
    "20260912-r5": set(EXPECTED_STATE_BY_ID) - {"PIT_INSIDER_OPEN_MARKET_PURCHASE_R1"},
    "20260912-r6": set(EXPECTED_STATE_BY_ID),
}


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
        assert isinstance(claim["source_run_id"], int) and claim["source_run_id"] > 0
        assert isinstance(claim["source_job_id"], int) and claim["source_job_id"] > 0
        assert isinstance(claim["artifact_id"], int) and claim["artifact_id"] > 0
        assert HEX40.fullmatch(claim["source_head_sha"])
        assert HEX40.fullmatch(claim["foundry_commit"])
        assert HEX64.fullmatch(claim["artifact_sha256"])
        assert claim["semantic_state"] == EXPECTED_STATE_BY_ID[workload_id]

    authority = payload["required_authority"]
    assert authority["authority"] == "RESEARCH_ONLY"
    for key in (
        "automatic_action",
        "portfolio_ranking_authority",
        "allocation_authority",
        "promotion_authority",
        "runtime_authority",
        "broker_authority",
        "live_trading",
    ):
        assert authority[key] is False, key

    print(json.dumps({
        "accepted": True,
        "acceptance_revision": revision,
        "claim_count": len(claims),
        "workload_ids": sorted(ids),
        "authority": "RESEARCH_ONLY",
        "live_trading": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
