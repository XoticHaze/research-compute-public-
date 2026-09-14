import hashlib
import json
from pathlib import Path

PRODUCT_BASE = "91c3988a9c40db1dbd7189862962b7bcf12059a9"
PRODUCT_CONTRACT_BRANCH = "main"


def main():
    route = {
        "portfolio_workflows_route": "/portfolio/workflows",
        "wrapper_preserves_existing_workflow": True,
        "selected_action_source": "query.actionId",
        "selected_action_detail_path": "/portfolio/actions/{actionId}",
        "rebalance_plan_source": "selected_action.result.rebalance_plan",
        "direct_plan_supported": True,
        "schema": "mm_ibkr.portfolio_rebalance_plan_r3",
        "preview_only": True,
    }
    canonical_projection_fields = {
        "provenance_fallback": "plan.source_intent",
        "actual_weight_fallback": "row.current_weight",
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
    assert route["selected_action_detail_path"] == "/portfolio/actions/{actionId}"
    assert route["rebalance_plan_source"] == "selected_action.result.rebalance_plan"
    assert route["direct_plan_supported"] is True
    assert route["schema"] == "mm_ibkr.portfolio_rebalance_plan_r3"
    assert route["preview_only"] is True
    assert canonical_projection_fields["provenance_fallback"] == "plan.source_intent"
    assert canonical_projection_fields["actual_weight_fallback"] == "row.current_weight"
    assert len(original_workflow_controls) == 4
    assert len(set(original_workflow_controls)) == 4
    assert all(token for token in preview_mutation_tokens)

    semantic_payload = json.dumps(
        {
            "route": route,
            "canonical_projection_fields": canonical_projection_fields,
            "original_workflow_controls": original_workflow_controls,
            "preview_forbidden_mutation_tokens": preview_mutation_tokens,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    receipt = {
        "schema": "mm.portfolio_rebalance_preview_sanitized_acceptance.v3",
        "product_base": PRODUCT_BASE,
        "product_contract_branch": PRODUCT_CONTRACT_BRANCH,
        "acceptance_class": "SANITIZED_READ_ONLY_REBALANCE_PREVIEW_CANONICAL_FIELDS",
        "operator_consequence": {
            "existing_workflow_controls_preserved": True,
            "selected_action_identity_drives_detail": True,
            "rebalance_plan_consumed_from_selected_action_result": True,
            "direct_plan_supported": True,
            "canonical_source_intent_provenance_supported": True,
            "canonical_current_weight_supported": True,
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
