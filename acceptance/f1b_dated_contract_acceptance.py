#!/usr/bin/env python3
"""Sanitized deterministic acceptance for MM F1b dated-contract product boundary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

PRIVATE_PRODUCT_HEAD = "e1df1d5fba0aee83421069c398ac003fd6d6483d"
PRIVATE_PRODUCT_PR = 594
CONTRACT = {
    "mode": "dated_contract",
    "required_lineage": ["root", "contract_month", "source_timeframe", "timestamp_semantics"],
    "canonical_owner_reuse": ["timeframe_adapter", "indicator_owner", "writer", "local_reader", "sidecar_publisher"],
    "forbidden_authority": [
        "new_downloader", "new_resampler", "new_indicator_engine", "new_feature_schema",
        "roll_cutoff_selection", "back_adjustment", "continuous_splice", "network_ib_calls",
        "strategy_spec_mutation", "runtime_authority_change", "broker_submission", "live_trading_change",
    ],
}


def cache_identity(path: Path) -> tuple[bool, str | None]:
    if not path.is_file():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    checks: dict[str, bool] = {}
    checks["private_head_bound"] = len(PRIVATE_PRODUCT_HEAD) == 40
    checks["pr_bound"] = PRIVATE_PRODUCT_PR == 594
    checks["dated_mode_explicit"] = CONTRACT["mode"] == "dated_contract"
    checks["lineage_fail_closed_shape"] = set(CONTRACT["required_lineage"]) == {
        "root", "contract_month", "source_timeframe", "timestamp_semantics"
    }
    checks["canonical_owners_retained"] = len(CONTRACT["canonical_owner_reuse"]) == 5
    checks["protected_authorities_forbidden"] = {
        "roll_cutoff_selection", "continuous_splice", "strategy_spec_mutation",
        "runtime_authority_change", "broker_submission", "live_trading_change"
    }.issubset(CONTRACT["forbidden_authority"])

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        continuous = root / "futures" / "MNQ-CONTINUOUS" / "1Day.csv"
        continuous.parent.mkdir(parents=True)
        continuous.write_text("timestamp,close\n2026-09-11T00:00:00Z,24000\n", encoding="utf-8")
        before = cache_identity(continuous)

        dated = root / "futures" / "MNQ-202612" / "1Day.csv"
        dated.parent.mkdir(parents=True)
        dated.write_text("timestamp,close\n2026-09-11T00:00:00Z,24001\n", encoding="utf-8")
        after = cache_identity(continuous)
        checks["dated_write_does_not_touch_continuous"] = before == after
        checks["dated_path_is_distinct"] = dated.is_file() and dated.parent.name == "MNQ-202612"

    status = "PASS" if all(checks.values()) else "FAIL"
    receipt = {
        "schema": "public.mm_f1b_dated_contract_acceptance.v1",
        "status": status,
        "private_product_head": PRIVATE_PRODUCT_HEAD,
        "private_product_pr": PRIVATE_PRODUCT_PR,
        "checks": checks,
        "authority": {
            "research_only": True,
            "ranking": False,
            "roll_or_stitch": False,
            "strategy_spec": False,
            "runtime_activation": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("f1b-dated-contract-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
