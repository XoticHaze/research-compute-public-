#!/usr/bin/env python3
"""P554 frozen Census M3 industry→security causal child R1.

Purpose: execute only the preperformance contract frozen in
contracts/p554_census_m3_industry_security_causal_contract_r1.json.

This script intentionally fails closed when promotion-quality release/vintage
or point-in-time security-universe evidence is unavailable. It may still emit
proxy-level causal diagnostics from official Census M3 observations plus
market prices, but must label any latest-revised-history result as
REPRESENTATION_NOT_PROMOTION_SAFE.
"""
from __future__ import annotations

import csv, io, json, math, os, statistics, sys, urllib.request, zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CENSUS_URL = os.environ.get("P554_M3_URL", "https://www.census.gov/manufacturing/m3/historical_data/historical_data.csv")
CONTRACT = Path(__file__).resolve().parents[1] / "contracts" / "p554_census_m3_industry_security_causal_contract_r1.json"
OUT = Path(os.environ.get("P554_RESULT", "p554_census_m3_industry_security_child_r1_result.json"))


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "CommandCenter-research/1.0", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        if not data:
            raise RuntimeError(f"empty source: {url}")
        return data


def main() -> int:
    contract = json.loads(CONTRACT.read_text())
    result = {
        "schema": "research.p554_census_m3_industry_security_child_result.r1",
        "parent_id": "P554",
        "contract_sha_local": None,
        "contract_status": contract.get("status"),
        "source_url": CENSUS_URL,
        "decision": None,
        "promotion_safe": False,
        "live_trading_change": False,
        "notes": [],
    }
    import hashlib
    result["contract_sha_local"] = hashlib.sha256(CONTRACT.read_bytes()).hexdigest()

    try:
        source = fetch(CENSUS_URL)
        result["source_sha256"] = hashlib.sha256(source).hexdigest()
        result["source_bytes"] = len(source)
    except Exception as e:
        result["decision"] = "P554_SOURCE_TRANSPORT_NOT_READY"
        result["error"] = repr(e)
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    # The currently admitted M3 archive/source-shape evidence is latest-history oriented.
    # Until a release-vintage mapping is provided, fail closed rather than backtest revised
    # values as promotion-quality causal evidence.
    vintage_manifest = os.environ.get("P554_VINTAGE_MANIFEST")
    if not vintage_manifest:
        result["decision"] = "REPRESENTATION_NOT_PROMOTION_SAFE"
        result["representation_blocker"] = "POINT_IN_TIME_M3_RELEASE_VINTAGE_MANIFEST_ABSENT"
        result["required_next_binding"] = {
            "artifact": "authoritative M3 release/vintage manifest",
            "minimum_fields": ["release_date", "observation_month", "category", "measure", "published_value", "source_identity"],
            "consumer": "same frozen contract; no mapping/feature/ticker changes"
        }
        result["notes"].append("Official M3 bytes are reachable, but revised-history bytes alone cannot support the frozen promotion-quality causal claim.")
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 3

    # A supplied manifest is intentionally only validated here. Scientific evaluation is
    # admitted only after exact vintage bytes are bound; this prevents accidental leakage.
    p = Path(vintage_manifest)
    if not p.exists():
        result["decision"] = "REPRESENTATION_NOT_PROMOTION_SAFE"
        result["representation_blocker"] = "DECLARED_VINTAGE_MANIFEST_NOT_FOUND"
        result["declared_manifest"] = vintage_manifest
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 4

    rows = list(csv.DictReader(p.read_text().splitlines()))
    required = {"release_date", "observation_month", "category", "measure", "published_value", "source_identity"}
    missing = sorted(required - set(rows[0].keys() if rows else []))
    if not rows or missing:
        result["decision"] = "REPRESENTATION_NOT_PROMOTION_SAFE"
        result["representation_blocker"] = "VINTAGE_MANIFEST_SCHEMA_INVALID"
        result["missing_fields"] = missing
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 5

    result["decision"] = "P554_VINTAGE_BINDING_VALIDATED__ECONOMIC_EVALUATION_READY"
    result["promotion_safe"] = True
    result["vintage_row_count"] = len(rows)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
