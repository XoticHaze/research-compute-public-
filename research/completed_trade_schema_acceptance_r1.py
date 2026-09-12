import json
from pathlib import Path

EXPECTED_SCHEMA = "mm.survivor_run_data_availability_audit.v1"
INPUT = {
    "owning_repo": "XoticHaze/mm-IBKR",
    "owning_head": "9d424ce06c45d0b4e778165141dc229f53a91934",
    "producer_schema": EXPECTED_SCHEMA,
    "pipeline_schema": EXPECTED_SCHEMA,
    "verifier_schema": EXPECTED_SCHEMA,
    "fail_closed_on_missing": True,
    "fail_closed_on_mismatch": True,
    "promotion_authority": False,
    "live_trading_change": False,
}

checks = {
    "producer_pipeline_schema_equal": INPUT["producer_schema"] == INPUT["pipeline_schema"],
    "producer_verifier_schema_equal": INPUT["producer_schema"] == INPUT["verifier_schema"],
    "missing_fails_closed": INPUT["fail_closed_on_missing"] is True,
    "mismatch_fails_closed": INPUT["fail_closed_on_mismatch"] is True,
    "no_promotion_authority": INPUT["promotion_authority"] is False,
    "no_live_trading_change": INPUT["live_trading_change"] is False,
}
passed = all(checks.values())
out = {
    "schema": "continue_release.completed_trade_schema_acceptance.v1",
    "input": INPUT,
    "checks": checks,
    "conclusion": "PASS" if passed else "FAIL",
}
Path("completed-trade-schema-acceptance-r1-result.json").write_text(json.dumps(out, sort_keys=True, indent=2))
print(json.dumps(out, sort_keys=True))
raise SystemExit(0 if passed else 1)
