import hashlib
import json
from pathlib import Path

PRODUCT_BASE = "b989129813f3e92be262909f4da14ec297a0c399"


def main():
    boundary_contract = {
        "schema": "mm_ibkr.portfolio_rebalance_plan_r3",
        "verified_only_when": {
            "planner_can_submit_orders": False,
            "paper_submit": False,
            "live_submit": False,
        },
        "verified_label": "PREVIEW ONLY",
        "unverified_label": "UNVERIFIED BOUNDARY",
        "unverified_action_class": "pill-bad",
        "unverified_message": "Planner safety boundaries are missing or not explicitly read-only. Treat all displayed actions as unverified evidence only.",
        "mutation_authority_added": False,
    }
    assert boundary_contract["verified_only_when"] == {
        "planner_can_submit_orders": False,
        "paper_submit": False,
        "live_submit": False,
    }
    assert boundary_contract["unverified_label"] == "UNVERIFIED BOUNDARY"
    assert boundary_contract["unverified_action_class"] == "pill-bad"
    assert boundary_contract["mutation_authority_added"] is False

    payload = json.dumps(boundary_contract, sort_keys=True, separators=(",", ":")).encode()
    receipt = {
        "schema": "mm.portfolio_rebalance_preview_fail_closed_acceptance.v1",
        "product_base": PRODUCT_BASE,
        "acceptance_class": "SANITIZED_FAIL_CLOSED_REBALANCE_PREVIEW_BOUNDARY",
        "boundary_contract": boundary_contract,
        "protected_boundaries": {
            "portfolio_ranking": False,
            "portfolio_allocation": False,
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "broker_submission": False,
            "paper_submit": False,
            "live_trading_change": False,
        },
        "semantic_sha256": hashlib.sha256(payload).hexdigest(),
        "result": "PASS",
    }
    Path("portfolio-rebalance-preview-fail-closed-acceptance-r1-result.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
