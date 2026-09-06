from __future__ import annotations

"""Source-only preflight for continuously vintaged semiconductor-cycle information.

The original exact-3344 capacity identifiers were rejected because ALFRED only begins
their real-time history in 2022. This child freezes two series selected solely by source
availability, before any equity model outcome: exact 3344 industrial production and the
broader high-tech capacity-utilization series that explicitly includes semiconductors.
"""

import csv
import io
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUT = Path("semiconductor_alfred_vintage_eligible_preflight_20260906.json")
BASE = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
SERIES = {
    "semiconductor_industrial_production": {
        "id": "IPG3344S",
        "scope": "NAICS 3344 semiconductor and other electronic component manufacturing",
    },
    "high_tech_capacity_utilization": {
        "id": "CAPUTLHITEK2S",
        "scope": "NAICS 3341,3342,3344 computers, communications equipment, and semiconductors",
    },
}
VINTAGES = ("2016-03-25", "2020-04-25", "2024-04-25", "2026-08-25")
START = "2014-01-01"
MIN_ROWS = {"2016-03-25": 20, "2020-04-25": 70, "2024-04-25": 115, "2026-08-25": 145}
UA = "research-compute-public/1.0"


def previous_month_start(s: str) -> date:
    d = date.fromisoformat(s)
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)


def get_text(url: str):
    last = None
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
            with urlopen(req, timeout=45) as response:
                return response.read().decode("utf-8-sig")
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET failed after 3 attempts: {url}: {last}")


def fetch(series_id: str, vintage: str):
    query = urlencode({"id": series_id, "cosd": START, "coed": vintage, "vintage_date": vintage})
    rows = list(csv.reader(io.StringIO(get_text(BASE + "?" + query))))
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{series_id} {vintage}: invalid CSV header={rows[:2]}")
    if rows[0][0] not in {"DATE", "observation_date"}:
        raise RuntimeError(f"{series_id} {vintage}: unexpected first column={rows[0][0]}")
    parsed = []
    for row in rows[1:]:
        if len(row) < 2 or not row[0] or row[1] in {"", "."}:
            continue
        parsed.append((date.fromisoformat(row[0]), float(row[1])))
    if not parsed:
        raise RuntimeError(f"{series_id} {vintage}: no observations")
    parsed.sort()
    return {
        "value_column": rows[0][1],
        "rows": len(parsed),
        "first_observation": parsed[0][0].isoformat(),
        "last_observation": parsed[-1][0].isoformat(),
        "last_value": parsed[-1][1],
    }


def main():
    evidence = {}
    passed = True
    for semantic, meta in SERIES.items():
        vintages = {}
        for vintage in VINTAGES:
            snap = fetch(meta["id"], vintage)
            allowed = previous_month_start(vintage)
            snap["conservative_max_allowed_observation"] = allowed.isoformat()
            snap["truncation_ok"] = date.fromisoformat(snap["last_observation"]) <= allowed
            snap["history_ok"] = snap["rows"] >= MIN_ROWS[vintage]
            passed = passed and snap["truncation_ok"] and snap["history_ok"]
            vintages[vintage] = snap
        evidence[semantic] = {**meta, "vintages": vintages}

    out = {
        "schema": "public_compute.semiconductor_alfred_vintage_eligible_preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parent_failed_preflight": 43,
        "source": "ALFRED key-free graph CSV",
        "selection_reason": "continuous real-time vintage availability from the development era; no equity-model outcome used",
        "series_frozen_before_model_outcomes": SERIES,
        "excluded_late_vintage_series": {
            "CAPUTLG3344S": "ALFRED release history begins 2022-08-16",
            "CAPG3344S": "ALFRED release history begins 2022-08-16",
        },
        "vintages_tested": list(VINTAGES),
        "evidence": evidence,
        "status": "PASS" if passed else "FAIL",
        "targets_computed": False,
        "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "next_boundary": "PASS authorizes building one reusable first-print monthly cache using conservative 25th-of-following-month vintages; that cache must be frozen before any equity model outcome",
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("SEMICONDUCTOR_ALFRED_VINTAGE_ELIGIBLE_PREFLIGHT=" + json.dumps(out, sort_keys=True))
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        failure = {
            "schema": "public_compute.semiconductor_alfred_vintage_eligible_preflight.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "ALFRED key-free graph CSV",
            "series_frozen_before_model_outcomes": SERIES,
            "status": "TRANSPORT_OR_VINTAGE_FAILURE",
            "error": str(exc),
            "targets_computed": False,
            "model_executed": False,
            "external_semiconductor_holdouts_loaded": False,
            "research_only": True,
            "promotion_authority": False,
            "runtime_mutation": False,
            "broker_action": False,
            "live_trading_change": False,
        }
        OUT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        print("SEMICONDUCTOR_ALFRED_VINTAGE_ELIGIBLE_PREFLIGHT=" + json.dumps(failure, sort_keys=True))
        raise
