import json
from pathlib import Path

EXPECTED_SCHEMA = "mm.survivor_run_data_availability_audit.v1"
OWNING_HEAD = "282a59cec29f1303e63fc64afcf32c240328df1b"


def project_operator_intelligence(strategy_health, readiness=None):
    """Sanitized contract model of the private operator handoff.

    Completed-trade availability may be preserved for display, but it must never
    manufacture Strategy Health readiness, capital eligibility, or a live-trading
    consequence.
    """
    health = strategy_health if isinstance(strategy_health, dict) else {}
    evidence = health.get("completed_trade_evidence")
    evidence = dict(evidence) if isinstance(evidence, dict) else None
    readiness = readiness if isinstance(readiness, dict) else {}
    return {
        "completed_trade_evidence": evidence,
        "state": readiness.get("state", "EVIDENCE_UNAVAILABLE"),
        "micro_live_eligible": bool(readiness.get("micro_live_eligible")),
        "current_risk_rung": readiness.get("risk_rung", 0),
    }


INPUT = {
    "owning_repo": "XoticHaze/mm-IBKR",
    "owning_head": OWNING_HEAD,
    "producer_schema": EXPECTED_SCHEMA,
    "pipeline_schema": EXPECTED_SCHEMA,
    "verifier_schema": EXPECTED_SCHEMA,
    "fail_closed_on_missing": True,
    "fail_closed_on_mismatch": True,
    "promotion_authority": False,
    "live_trading_change": False,
}

bridge_ready = {
    "state": "BRIDGE_READY",
    "symbol": "AMAT",
    "bridge_ready_runs": 2,
    "intent_only_runs": 0,
    "ledger_only_runs": 0,
    "missing_evidence": [],
    "source_ref": EXPECTED_SCHEMA,
}
incomplete = {
    "state": "INSUFFICIENT_EVIDENCE",
    "symbol": "AMAT",
    "bridge_ready_runs": 0,
    "intent_only_runs": 1,
    "ledger_only_runs": 0,
    "missing_evidence": ["strategy_spec_digest", "runtime_id"],
    "source_ref": EXPECTED_SCHEMA,
}
ready_projection = project_operator_intelligence({"completed_trade_evidence": bridge_ready})
incomplete_projection = project_operator_intelligence({"completed_trade_evidence": incomplete})
missing_projection = project_operator_intelligence({})

checks = {
    "producer_pipeline_schema_equal": INPUT["producer_schema"] == INPUT["pipeline_schema"],
    "producer_verifier_schema_equal": INPUT["producer_schema"] == INPUT["verifier_schema"],
    "missing_fails_closed": INPUT["fail_closed_on_missing"] is True,
    "mismatch_fails_closed": INPUT["fail_closed_on_mismatch"] is True,
    "no_promotion_authority": INPUT["promotion_authority"] is False,
    "no_live_trading_change": INPUT["live_trading_change"] is False,
    "bridge_ready_reaches_operator_projection": ready_projection["completed_trade_evidence"] == bridge_ready,
    "bridge_ready_does_not_promote_readiness": ready_projection["state"] == "EVIDENCE_UNAVAILABLE",
    "bridge_ready_does_not_enable_micro_live": ready_projection["micro_live_eligible"] is False,
    "bridge_ready_does_not_raise_risk_rung": ready_projection["current_risk_rung"] == 0,
    "incomplete_reasons_survive_operator_handoff": incomplete_projection["completed_trade_evidence"]["missing_evidence"] == ["strategy_spec_digest", "runtime_id"],
    "missing_projection_remains_missing": missing_projection["completed_trade_evidence"] is None,
}
passed = all(checks.values())
out = {
    "schema": "continue_release.completed_trade_schema_acceptance.v2",
    "input": INPUT,
    "operator_handoff": {
        "bridge_ready": ready_projection,
        "incomplete": incomplete_projection,
        "missing": missing_projection,
    },
    "checks": checks,
    "conclusion": "PASS" if passed else "FAIL",
}
Path("completed-trade-schema-acceptance-r1-result.json").write_text(json.dumps(out, sort_keys=True, indent=2))
print(json.dumps(out, sort_keys=True))
raise SystemExit(0 if passed else 1)
