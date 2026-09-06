from __future__ import annotations

"""Materialize the frozen first-print semiconductor-cycle feature cache.

Each monthly row is computed entirely inside the ALFRED snapshot dated the 25th of the
following month. This preserves historical revisions/rebasings and prevents later data
from leaking backward. No equity price, target, or model is loaded here.
"""

import csv
import hashlib
import io
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUT = Path("semiconductor_alfred_first_print_cache_receipt_20260906.json")
CACHE = Path("semiconductor_alfred_first_print_cache_20260906.json")
BASE = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
SERIES = {
    "ip": "IPG3344S",
    "util": "CAPUTLHITEK2S",
}
FIRST = date(2015, 1, 1)
LAST = date(2026, 7, 1)
UA = "research-compute-public/1.0"


def add_months(d: date, n: int) -> date:
    total = d.year * 12 + (d.month - 1) + n
    return date(total // 12, total % 12 + 1, 1)


def months(start: date, stop: date):
    d = start
    while d <= stop:
        yield d
        d = add_months(d, 1)


def vintage_for(observation_month: date) -> date:
    nxt = add_months(observation_month, 1)
    return date(nxt.year, nxt.month, 25)


def get_text(url: str):
    last = None
    for attempt in range(4):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
            with urlopen(req, timeout=45) as response:
                return response.read().decode("utf-8-sig")
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"GET failed after 4 attempts: {url}: {last}")


def fetch_window(series_id: str, observation_month: date, vintage: date):
    start = add_months(observation_month, -12)
    # Use the URL shape already proven by PR #44: coed is the vintage date.  The
    # required observation month is then selected locally from that same vintage.
    query = urlencode({
        "id": series_id,
        "cosd": start.isoformat(),
        "coed": vintage.isoformat(),
        "vintage_date": vintage.isoformat(),
    })
    rows = list(csv.reader(io.StringIO(get_text(BASE + "?" + query))))
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{series_id} {vintage}: invalid CSV")
    values = {}
    for row in rows[1:]:
        if len(row) < 2 or not row[0] or row[1] in {"", "."}:
            continue
        values[date.fromisoformat(row[0])] = float(row[1])
    return values, rows[0][1]


def required(values, d: date, series_id: str, vintage: date):
    if d not in values:
        raise RuntimeError(f"{series_id} vintage={vintage} missing required observation={d}")
    return values[d]


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main():
    cache_rows = []
    request_count = 0
    for m in months(FIRST, LAST):
        vintage = vintage_for(m)
        ip, ip_col = fetch_window(SERIES["ip"], m, vintage); request_count += 1
        util, util_col = fetch_window(SERIES["util"], m, vintage); request_count += 1

        ip0 = required(ip, m, SERIES["ip"], vintage)
        ip1 = required(ip, add_months(m, -1), SERIES["ip"], vintage)
        ip3 = required(ip, add_months(m, -3), SERIES["ip"], vintage)
        ip12 = required(ip, add_months(m, -12), SERIES["ip"], vintage)
        u0 = required(util, m, SERIES["util"], vintage)
        u3 = required(util, add_months(m, -3), SERIES["util"], vintage)
        u12 = required(util, add_months(m, -12), SERIES["util"], vintage)
        if min(ip0, ip1, ip3, ip12) <= 0:
            raise RuntimeError(f"{m}: nonpositive IP level in same-vintage change inputs")

        cache_rows.append({
            "observation_month": m.isoformat(),
            "available_from": vintage.isoformat(),
            "source_columns": {"ip": ip_col, "util": util_col},
            "semi_ip_change_1m": ip0 / ip1 - 1.0,
            "semi_ip_change_3m": ip0 / ip3 - 1.0,
            "semi_ip_change_12m": ip0 / ip12 - 1.0,
            "hitek_capacity_utilization": u0,
            "hitek_capacity_utilization_change_3m": u0 - u3,
            "hitek_capacity_utilization_change_12m": u0 - u12,
        })
        time.sleep(0.03)

    expected = (LAST.year - FIRST.year) * 12 + LAST.month - FIRST.month + 1
    if len(cache_rows) != expected:
        raise RuntimeError(f"cache row count {len(cache_rows)} != expected {expected}")

    cache = {
        "schema": "public_compute.semiconductor_alfred_first_print_cache.v1",
        "source": "ALFRED key-free graph CSV",
        "source_parent_pr": 44,
        "series": SERIES,
        "availability_wall": "25th of following month",
        "rebase_policy": "IP changes computed inside each vintage snapshot; raw IP levels are not stitched across vintages",
        "features": [
            "semi_ip_change_1m",
            "semi_ip_change_3m",
            "semi_ip_change_12m",
            "hitek_capacity_utilization",
            "hitek_capacity_utilization_change_3m",
            "hitek_capacity_utilization_change_12m",
        ],
        "rows": cache_rows,
    }
    raw = canonical(cache)
    sha = hashlib.sha256(raw).hexdigest()
    CACHE.write_bytes(raw + b"\n")
    receipt = {
        "schema": "public_compute.semiconductor_alfred_first_print_cache_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_parent_pr": 44,
        "cache_path": str(CACHE),
        "cache_sha256": sha,
        "cache_bytes": len(raw) + 1,
        "cache_rows": len(cache_rows),
        "first_observation_month": cache_rows[0]["observation_month"],
        "last_observation_month": cache_rows[-1]["observation_month"],
        "first_available_from": cache_rows[0]["available_from"],
        "last_available_from": cache_rows[-1]["available_from"],
        "http_requests": request_count,
        "targets_computed": False,
        "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "status": "PASS",
        "next_boundary": "commit this exact cache by SHA, then run the separately frozen target-specific path-head consumer on matched rows",
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("SEMICONDUCTOR_ALFRED_FIRST_PRINT_CACHE=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        failure = {
            "schema": "public_compute.semiconductor_alfred_first_print_cache_receipt.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_parent_pr": 44,
            "status": "FAIL",
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
        print("SEMICONDUCTOR_ALFRED_FIRST_PRINT_CACHE=" + json.dumps(failure, sort_keys=True))
        raise
