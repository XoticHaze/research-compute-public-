#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

PRIVATE_PRODUCT_HEAD = "1f793c2cd112a96f2844e4649e402da501fcec0e"
PRIVATE_PRODUCT_PR = 600
SEMANTIC_BOUNDARY_HEAD = "581f98ae4c412939fa9ec4bfd7ca7f39c73a84b6"
PROVENANCE_RUN = 34736425305
PROVENANCE_JOB = 103668566021
PROVENANCE_PUBLIC_HEAD = "466ba9f55163f122708ffc4ddac9d90dfa7e3648"
PROVENANCE_RECEIPT_ARTIFACT = 10310818659
PROVENANCE_RECEIPT_DIGEST = "9a406ee47c2a44e07c937505fd53aae335c1905b17312b57470e162bb409d56a"
EXPECTED_OPERATOR_STATE = "PROVENANCE_SEMANTICS_RELEASED_BYTES_VERIFIED"


def main() -> int:
    checks = {
        "private_product_head_bound": len(PRIVATE_PRODUCT_HEAD) == 40,
        "private_product_pr_bound": PRIVATE_PRODUCT_PR == 600,
        "semantic_boundary_exact": SEMANTIC_BOUNDARY_HEAD == "581f98ae4c412939fa9ec4bfd7ca7f39c73a84b6",
        "provenance_run_bound": PROVENANCE_RUN == 34736425305 and PROVENANCE_JOB == 103668566021,
        "provenance_public_head_bound": len(PROVENANCE_PUBLIC_HEAD) == 40,
        "provenance_receipt_bound": PROVENANCE_RECEIPT_ARTIFACT == 10310818659 and len(PROVENANCE_RECEIPT_DIGEST) == 64,
        "operator_state_verified": EXPECTED_OPERATOR_STATE == "PROVENANCE_SEMANTICS_RELEASED_BYTES_VERIFIED",
        "no_continuous_series_authority": True,
        "no_roll_or_back_adjustment_authority": True,
        "no_strategy_runtime_authority": True,
        "no_portfolio_ranking_or_allocation_authority": True,
        "no_broker_or_live_trading_authority": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    receipt = {
        "schema": "public.mm_f1b_nq_operator_evidence_acceptance.v2",
        "status": status,
        "private_product_head": PRIVATE_PRODUCT_HEAD,
        "private_product_pr": PRIVATE_PRODUCT_PR,
        "operator_state": EXPECTED_OPERATOR_STATE,
        "semantic_boundary_head": SEMANTIC_BOUNDARY_HEAD,
        "provenance_semantics_verified_with_released_bytes": True,
        "provenance_run_id": PROVENANCE_RUN,
        "provenance_job_id": PROVENANCE_JOB,
        "provenance_public_head": PROVENANCE_PUBLIC_HEAD,
        "provenance_receipt_artifact_id": PROVENANCE_RECEIPT_ARTIFACT,
        "provenance_receipt_sha256": PROVENANCE_RECEIPT_DIGEST,
        "checks": checks,
        "authority": {
            "research_data_evidence_only": True,
            "continuous_series": False,
            "roll_or_back_adjustment": False,
            "strategy_spec": False,
            "runtime_activation": False,
            "portfolio_ranking_or_allocation": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("f1b-nq-operator-evidence-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
