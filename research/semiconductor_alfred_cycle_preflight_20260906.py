from __future__ import annotations

"""Source-only causal semiconductor-cycle preflight using key-free ALFRED graph CSV.

No equity price/path target and no model is computed. The three NAICS-3344 series are
frozen before any model outcome. Historical vintage snapshots must be accessible and
must not expose observations later than the month preceding the chosen vintage date.
"""

import csv
import io
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUT = Path("semiconductor_alfred_cycle_preflight_20260906.json")
BASE = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
SERIES = {
    "industrial_production": "IPG3344S",
    "capacity_utilization": "CAPUTLG3344S",
    "industrial_capacity": "CAPG3344S",
}
VINTAGES = ("2016-03-25", "2020-04-25", "2024-04-25", "2026-08-25")
START = "2014-01-01"
UA = "research-compute-public/1.0"
MIN_ROWS = {"2016-03-25": 20, "2020-04-25": 70, "2024-04-25": 115, "2026-08-25": 145}


def previous_month_start(s: str) -> date:
    d = date.fromisoformat(s)
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


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
    query = urlencode({
        "id": series_id,
        "cosd": START,
        "coed": vintage,
        "vintage_date": vintage,
    })
    url = BASE + "?" + query
    text = get_text(url)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{series_id} {vintage}: invalid CSV header={rows[:2]}")
    header = rows[0]
    if header[0] not in {"DATE", "observation_date"}:
        raise RuntimeError(f"{series_id} {vintage}: unexpected first column={header[0]}")
    parsed = []
    for row in rows[1:]:
        if len(row) < 2 or not row[0] or row[1] in {"", "."}:
            continue
        parsed.append((date.fromisoformat(row[0]), float(row[1])))
    if not parsed:
        raise RuntimeError(f"{series_id} {vintage}: no observations")
    parsed.sort()
    return {
        "url_shape": "alfredgraph.csv?id=<series>&cosd=<start>&coed=<vintage>&vintage_date=<vintage>",
        "value_column": header[1],
        "rows": len(parsed),
        "first_observation": parsed[0][0].isoformat(),
        "last_observation": parsed[-1][0].isoformat(),
        "last_value": parsed[-1][1],
    }


def main():
    evidence = {}
    passed = True
    for semantic, series_id in SERIES.items():
        snapshots = {}
        for vintage in VINTAGES:
            snap = fetch(series_id, vintage)
            max_allowed = previous_month_start(vintage)
            snap["conservative_max_allowed_observation"] = max_allowed.isoformat()
            snap["truncation_ok"] = date.fromisoformat(snap["last_observation"]) <= max_allowed
            snap["history_ok"] = snap["rows"] >= MIN_ROWS[vintage]
            passed = passed and snap["truncation_ok"] and snap["history_ok"]
            snapshots[vintage] = snap
        evidence[semantic] = {"series_id": series_id, "vintages": snapshots}

    out = {
        "schema": "public_compute.semiconductor_alfred_cycle_preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "ALFRED key-free graph CSV",
        "information_family": "semiconductor_cycle_naics3344",
        "series_frozen_before_model_outcomes": SERIES,
        "vintages": list(VINTAGES),
        "causal_rule": "a downstream daily signal may use a monthly observation only from an ALFRED vintage already available by that signal date; first consumer will use a conservative 25th-of-following-month publication wall unless separately disproved",
        "evidence": evidence,
        "status": "PASS" if passed else "FAIL",
        "targets_computed": False,
        "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "next_boundary": "PASS authorizes one frozen development-only cycle-information consumer against exact PR31/PR34 path-head control; FAIL requires source/publication diagnosis, not revised-current-history substitution",
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("SEMICONDUCTOR_ALFRED_CYCLE_PREFLIGHT=" + json.dumps(out, sort_keys=True))
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
