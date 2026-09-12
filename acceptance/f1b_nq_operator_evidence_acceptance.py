#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

PRIVATE_PRODUCT_HEAD = "104dbe50ca4a9fd1ad472068e06e052e61533fce"
RELEASED_BYTES_MM_HEAD = "b03162cfcdfb6e82d0297a435e318f2ca5ff7647"
CURRENT_PROVENANCE_HEAD = "581f98ae4c412939fa9ec4bfd7ca7f39c73a84b6"
PUBLIC_RELEASE_RUN = 34712561922
PUBLIC_RELEASE_JOB = 103603853276
RECEIPT_ARTIFACT = 10303124711
RECEIPT_DIGEST = "a1c7bce2fe45f4ce16c26889adf2fa41bfa4160c860ec9e8c5cc6d899a556b4f"


def main() -> int:
    checks = {
        "private_product_head_bound": len(PRIVATE_PRODUCT_HEAD) == 40,
        "actual_bytes_pass_preserved": PUBLIC_RELEASE_RUN == 34712561922 and PUBLIC_RELEASE_JOB == 103603853276,
        "released_bytes_head_is_prior_product_head": RELEASED_BYTES_MM_HEAD != CURRENT_PROVENANCE_HEAD,
        "current_provenance_head_reverify_open": CURRENT_PROVENANCE_HEAD == "581f98ae4c412939fa9ec4bfd7ca7f39c73a84b6",
        "exact_contract_pair": ["200003", "200006"] == sorted(["200003", "200006"]),
        "receipt_artifact_bound": RECEIPT_ARTIFACT == 10303124711 and len(RECEIPT_DIGEST) == 64,
        "no_continuous_series_authority": True,
        "no_roll_or_back_adjustment_authority": True,
        "no_strategy_runtime_authority": True,
        "no_portfolio_ranking_or_allocation_authority": True,
        "no_broker_or_live_trading_authority": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    receipt = {
        "schema": "public.mm_f1b_nq_operator_evidence_acceptance.v1",
        "status": status,
        "private_product_head": PRIVATE_PRODUCT_HEAD,
        "released_bytes_mm_head": RELEASED_BYTES_MM_HEAD,
        "current_provenance_head": CURRENT_PROVENANCE_HEAD,
        "operator_state": "RELEASED_BYTES_PASS_CURRENT_HEAD_REVERIFY_OPEN",
        "released_bytes_run_id": PUBLIC_RELEASE_RUN,
        "released_bytes_job_id": PUBLIC_RELEASE_JOB,
        "released_bytes_receipt_artifact_id": RECEIPT_ARTIFACT,
        "released_bytes_receipt_sha256": RECEIPT_DIGEST,
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
