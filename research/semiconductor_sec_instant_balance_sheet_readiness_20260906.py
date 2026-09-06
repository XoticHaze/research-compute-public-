from __future__ import annotations

"""Consumer-specific readiness gate for the frozen SEC balance-sheet experiment.

This does not change or reinterpret the six-category source gate. The full source receipt
remains PASS/FAIL exactly as emitted. This gate asks the narrower question already frozen
by the first-consumer contract: are assets, inventory and cash eligible for all seven
companies? Duration-category failures are recorded but cannot silently become PASS.
"""

import hashlib
import json
from pathlib import Path

PREFLIGHT = Path("sec_hf_root_parquet_semiconductor_preflight_20260906.json")
CACHE = Path("sec_hf_root_parquet_semiconductor_cache_20260906.json")
OUT = Path("semiconductor_sec_instant_balance_sheet_readiness_20260906.json")
INSTANT = ("assets", "inventory", "cash")
EXPECTED = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")


def main():
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    cache_bytes = CACHE.read_bytes()
    cache = json.loads(cache_bytes.decode("utf-8"))
    if tuple(preflight.get("development_universe") or ()) != EXPECTED:
        raise RuntimeError(f"unexpected preflight universe={preflight.get('development_universe')}")
    if tuple(cache.get("development_universe") or ()) != EXPECTED:
        raise RuntimeError(f"unexpected cache universe={cache.get('development_universe')}")

    instant_failures = []
    duration_failures = []
    for symbol in EXPECTED:
        categories = preflight["coverage"][symbol]["categories"]
        for category, payload in categories.items():
            selected = payload["selected"]
            if not selected.get("eligible"):
                item = {
                    "symbol": symbol,
                    "category": category,
                    "label": selected.get("label"),
                    "distinct_filings": selected.get("distinct_filings"),
                    "filed_years": selected.get("filed_years"),
                    "first_filed": selected.get("first_filed"),
                    "last_filed": selected.get("last_filed"),
                }
                if category in INSTANT:
                    instant_failures.append(item)
                else:
                    duration_failures.append(item)

    ready = not instant_failures
    receipt = {
        "schema": "public_compute.semiconductor_sec_instant_balance_sheet_readiness.v1",
        "source_dataset": cache.get("source_dataset"),
        "source_dataset_revision": cache.get("source_dataset_revision"),
        "source_cache_sha256": hashlib.sha256(cache_bytes).hexdigest(),
        "six_category_source_status": preflight.get("status"),
        "instant_categories": list(INSTANT),
        "instant_failures": instant_failures,
        "duration_failures_preserved": duration_failures,
        "status": "PASS" if ready else "FAIL",
        "interpretation": "PASS authorizes only the frozen instant balance-sheet first consumer; it does not convert the full six-category source gate to PASS",
        "duration_facts_authorized_for_model": False,
        "external_semiconductor_holdouts_loaded": False,
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SEMICONDUCTOR_SEC_INSTANT_BALANCE_SHEET_READINESS=" + json.dumps(receipt, sort_keys=True))
    if not ready:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
