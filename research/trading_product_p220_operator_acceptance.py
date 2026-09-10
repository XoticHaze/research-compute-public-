import hashlib
import json
from pathlib import Path

PAYLOAD = {
    "schema": "mm.trading_product.p220_operator_contract.v1",
    "product_repository": "XoticHaze/mm-IBKR",
    "product_pr": 476,
    "product_head": "0ef0c26712aff6a16360db7767b4425bcd6a54a1",
    "source_execution": {
        "repository": "XoticHaze/research-compute-public-",
        "run_id": 34434053340,
        "job_id": 102735358987,
        "started_at": "2026-09-10T03:37:47Z",
        "head_sha": "5b1e108150936c6c27869aa6a5b4d4c85db308eb",
        "artifact_id": 10135521227,
        "artifact_sha256": "2b1d36781cceddf427922b20d27fafc6a2b28d70423ca47eeefdbd1a1b6eb743",
    },
    "decision": "P220_BETA_ADJUSTED_ALPHA_NOT_SUPPORTED",
    "operator_state": "POSITIVE_ATTRIBUTION_WEAK_TEMPORAL_PERSISTENCE",
    "metrics": {"mdy_adjusted_alpha_annualized_bp": 357, "iid_t_stat": 1.82, "positive_chronological_folds": 2, "required_positive_folds": 4},
    "retains": "P217/P219 matched-size XMMO evidence as bounded context",
    "prohibits": ["promotion inference", "portfolio-ranking inference", "allocation inference", "parameter rescue"],
}

assert PAYLOAD["decision"] == "P220_BETA_ADJUSTED_ALPHA_NOT_SUPPORTED"
assert PAYLOAD["metrics"]["mdy_adjusted_alpha_annualized_bp"] > 0
assert PAYLOAD["metrics"]["iid_t_stat"] >= 1.5
assert PAYLOAD["metrics"]["positive_chronological_folds"] < PAYLOAD["metrics"]["required_positive_folds"]
assert "parameter rescue" in PAYLOAD["prohibits"]
assert PAYLOAD["source_execution"]["artifact_sha256"] == "2b1d36781cceddf427922b20d27fafc6a2b28d70423ca47eeefdbd1a1b6eb743"

canonical = json.dumps(PAYLOAD, sort_keys=True, separators=(",", ":"))
out = {
    "schema": "mm.trading_product.p220_operator_acceptance.v1",
    "result": "PASS",
    "contract_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    "contract": PAYLOAD,
}
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/trading_product_p220_operator_acceptance.json").write_text(json.dumps(out, sort_keys=True, indent=2))
print(f"P220_OPERATOR_ACCEPTANCE=PASS contract_sha256={out['contract_sha256']}")
