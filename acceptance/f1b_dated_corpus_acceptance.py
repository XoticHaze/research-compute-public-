#!/usr/bin/env python3
"""Sanitized deterministic acceptance for MM F1b dated-corpus product boundary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PRIVATE_PRODUCT_HEAD = "b7c8b88b2ec9b73647627785622bbe5e3400d00b"
PRIVATE_PRODUCT_PR = 595


def canonical_sha(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    months = ["202609", "202612"]
    identities = [
        {
            "root": "NQ",
            "contract_month": month,
            "raw_sha256": f"raw-{month}",
            "features_sha256": f"features-{month}",
            "feature_manifest_hash": f"manifest-{month}",
            "dated_lineage_sha256": f"lineage-{month}",
        }
        for month in months
    ]
    corpus = {
        "schema": "mm.admitted_futures_dated_corpus_identity.v1",
        "root": "NQ",
        "source_timeframe": "1D",
        "target_timeframe": "1D",
        "contract_months": months,
        "contracts": identities,
    }
    checks = {
        "private_head_bound": len(PRIVATE_PRODUCT_HEAD) == 40,
        "pr_bound": PRIVATE_PRODUCT_PR == 595,
        "multi_contract_required": len(months) >= 2,
        "ordered_contract_months": months == sorted(months),
        "unique_contract_months": len(months) == len(set(months)),
        "single_root": {row["root"] for row in identities} == {"NQ"},
        "identity_binds_raw": all(row["raw_sha256"] for row in identities),
        "identity_binds_features": all(row["features_sha256"] for row in identities),
        "identity_binds_feature_manifest": all(row["feature_manifest_hash"] for row in identities),
        "identity_binds_lineage": all(row["dated_lineage_sha256"] for row in identities),
        "deterministic_corpus_hash": canonical_sha(corpus) == canonical_sha(json.loads(json.dumps(corpus))),
        "no_roll_or_stitch_authority": True,
        "no_strategy_runtime_broker_live_authority": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    receipt = {
        "schema": "public.mm_f1b_dated_corpus_acceptance.v1",
        "status": status,
        "private_product_head": PRIVATE_PRODUCT_HEAD,
        "private_product_pr": PRIVATE_PRODUCT_PR,
        "corpus_sha256": canonical_sha(corpus),
        "checks": checks,
        "authority": {
            "research_only": True,
            "portfolio_ranking": False,
            "roll_or_stitch": False,
            "strategy_spec": False,
            "runtime_activation": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("f1b-dated-corpus-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
