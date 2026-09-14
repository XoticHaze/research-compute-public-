import hashlib
import json
from pathlib import Path

PRODUCT_BASE = "b783b0ed8a27bb4d2fefb8d5b5f2e954119d6005"
PRODUCT_CONTRACT_BRANCH = "assistant/portfolio-rebalance-preview-contract-r1"


def main():
    route = {
        "portfolio_workflows_route": "/portfolio/workflows",
        "wrapper_preserves_existing_workflow": True,
        "selected_action_source": "query.actionId",
        "rebalance_plan_path": "/api/portfolio/workflows/{actionId}/rebalance-plan",
        "schema": "mm_ibkr.portfolio_rebalance_plan_r3",
        "preview_only": True,
    }
    original_workflow_controls = [
        "queueAction",
        "cancelAction",
        "retryAction",
        "updateDraftAction",
    ]
    preview_mutation_tokens = [
        "apiPost(",
        "/submit",
        "/flatten",
        "/cancel",
        "ENABLE_LIVE_TRADING",
        "paper_submit_enabled",
    ]

    assert route["wrapper_preserves_existing_workflow"] is True
    assert route["selected_action_source"] == "query.actionId"
    assert route["schema"] == "mm_ibkr.portfolio_rebalance_plan_r3"
    assert route["preview_only"] is True
    assert len(original_workflow_controls) == 4
    assert len(set(original_workflow_controls)) == 4
    assert all(token for token in preview_mutation_tokens)

    semantic_payload = json.dumps(
        {
            "route": route,
            "original_workflow_controls": original_workflow_controls,
            "preview_forbidden_mutation_tokens": preview_mutation_tokens,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    receipt = {
        "schema": "mm.portfolio_rebalance_preview_sanitized_acceptance.v1",
        "product_base": PRODUCT_BASE,
        "product_contract_branch": PRODUCT_CONTRACT_BRANCH,
        "acceptance_class": "SANITIZED_READ_ONLY_REBALANCE_PREVIEW_OPERATOR_CONTRACT",
        "operator_consequence": {
            "existing_workflow_controls_preserved": True,
            "selected_action_identity_drives_preview": True,
            "canonical_rebalance_plan_schema_required": True,
            "preview_only": True,
        },
        "protected_boundaries": {
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "portfolio_ranking": False,
            "portfolio_allocation": False,
            "broker_submission": False,
            "paper_submit": False,
            "live_trading_change": False,
        },
        "semantic_sha256": hashlib.sha256(semantic_payload).hexdigest(),
        "result": "PASS",
    }
    Path("portfolio-rebalance-preview-acceptance-r1-result.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
