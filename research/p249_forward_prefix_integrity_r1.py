#!/usr/bin/env python3
"""Read-only prospective P249/P266 immutable-prefix validator.

This helper does not retrieve data, launch jobs, change economics, or authorize
publication. It compares two *independently supplied, immutable* observer
artifacts; the owning Release route must authenticate the prior artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

FIELDS = ("date", "holding_month", "p249_core_gross", "p249_core_net",
          "p249_plus_p266_gross", "p249_plus_p266_net",
          "satellite_increment_net", "cost_detail")
IDENTITY = ("decision_at", "contract", "source_pins")
VALID_SCHEMAS = {
    "research.forward_p249_p266_shadow_r1",
    "research.p279_p249_p266_forward_shadow_observer_r1",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema") not in VALID_SCHEMAS:
        raise ValueError("P249_PREFIX_INVALID_SOURCE_SCHEMA")
    forward = payload.get("forward")
    rows = forward.get("observations") if isinstance(forward, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("P249_PREFIX_MISSING_OBSERVATIONS")
    previous_date = ""
    for row in rows:
        if not isinstance(row, dict) or any(key not in row for key in FIELDS):
            raise ValueError("P249_PREFIX_MISSING_SCIENTIFIC_ROW_FIELD")
        day = row["date"]
        if not isinstance(day, str) or len(day) != 10 or day <= previous_date:
            raise ValueError("P249_PREFIX_NONCHRONOLOGICAL_OR_DUPLICATE_DATE")
        if not isinstance(row["holding_month"], str) or row["holding_month"] != day[:7]:
            raise ValueError("P249_PREFIX_HOLDING_MONTH_DRIFT")
        for key in FIELDS[2:7]:
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("P249_PREFIX_NONFINITE_OR_INVALID_ECONOMIC_ROW")
        previous_date = day
    if forward.get("latest_close") != rows[-1]["date"]:
        raise ValueError("P249_PREFIX_LATEST_CLOSE_MISMATCH")
    return rows


def compare(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on historical edits, drops, duplicate dates, or contract drift."""
    before = _rows(previous)
    after = _rows(current)
    if previous.get("schema") != current.get("schema"):
        raise ValueError("P249_PREFIX_SCHEMA_CHANGED")
    for key in IDENTITY:
        if _canonical(previous.get(key)) != _canonical(current.get(key)):
            raise ValueError("P249_PREFIX_FROZEN_IDENTITY_CHANGED:" + key)
    if len(after) < len(before):
        raise ValueError("P249_PREFIX_HISTORICAL_ROWS_DROPPED")
    for i, old in enumerate(before):
        new = after[i]
        if old["date"] != new["date"]:
            raise ValueError(f"P249_PREFIX_PRIOR_DATE_CHANGED_AT_INDEX:{i}")
        if _canonical({k: old[k] for k in FIELDS}) != _canonical({k: new[k] for k in FIELDS}):
            raise ValueError(f"P249_PREFIX_HISTORICAL_FORWARD_PREFIX_REVISED:{old['date']}")
    # Provider observations may contain extra non-economic metadata; only the
    # frozen economic row identity is protected here. A stronger owning issuer
    # may choose to bind more fields but may not relax the economic prefix.
    return {
        "status": "P249_APPEND_ONLY_PREFIX_ACCEPTED",
        "prior_sessions": len(before),
        "current_sessions": len(after),
        "new_sessions": len(after) - len(before),
        "last_prior_date": before[-1]["date"],
        "latest_date": after[-1]["date"],
        "prior_science_prefix_sha256": _sha([{k: row[k] for k in FIELDS} for row in before]),
        "current_prefix_matches_prior": True,
        "stage": "READ_ONLY_SOURCE_INTEGRITY_NOT_INDEPENDENT_ISSUER_OR_FUNDED_ECONOMICS",
    }


def selftest() -> None:
    base = {
        "schema": "research.forward_p249_p266_shadow_r1",
        "decision_at": "2026-09-10T07:25:00+00:00",
        "contract": {"weights": "frozen"},
        "source_pins": {"producer": "frozen"},
        "forward": {"latest_close": "2026-09-10", "observations": [{
            "date": "2026-09-10", "holding_month": "2026-09",
            "p249_core_gross": 0.01, "p249_core_net": 0.009,
            "p249_plus_p266_gross": 0.012, "p249_plus_p266_net": 0.011,
            "satellite_increment_net": 0.002, "cost_detail": {"cost": 10},
        }]},
    }
    newer = json.loads(json.dumps(base))
    newer["forward"]["observations"].append({
        **newer["forward"]["observations"][0], "date": "2026-09-11",
        "p249_core_gross": -0.01, "p249_core_net": -0.01,
        "p249_plus_p266_gross": -0.009, "p249_plus_p266_net": -0.009,
        "satellite_increment_net": 0.001, "cost_detail": None,
    })
    newer["forward"]["latest_close"] = "2026-09-11"
    assert compare(base, newer)["new_sessions"] == 1
    revised = json.loads(json.dumps(newer))
    revised["forward"]["observations"][0]["p249_core_net"] = 0.008
    try:
        compare(base, revised)
    except ValueError as exc:
        assert "HISTORICAL_FORWARD_PREFIX_REVISED" in str(exc)
    else:
        raise AssertionError("Revised prefix accepted")
    dropped = json.loads(json.dumps(base))
    dropped["forward"]["observations"] = []
    try:
        compare(newer, dropped)
    except ValueError:
        pass
    else:
        raise AssertionError("Dropped prefix accepted")
    changed_contract = json.loads(json.dumps(newer))
    changed_contract["contract"]["weights"] = "retuned"
    try:
        compare(base, changed_contract)
    except ValueError as exc:
        assert "FROZEN_IDENTITY_CHANGED" in str(exc)
    else:
        raise AssertionError("Changed contract accepted")
    print("P249_PREFIX_INTEGRITY_SELFTEST_PASS: append, revised historical row, dropped prefix, changed contract")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    if args.prior is None or args.current is None:
        parser.error("--prior and --current authenticated immutable JSON paths are required")
    prior = json.loads(args.prior.read_text(encoding="utf-8"))
    current = json.loads(args.current.read_text(encoding="utf-8"))
    print(json.dumps(compare(prior, current), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()