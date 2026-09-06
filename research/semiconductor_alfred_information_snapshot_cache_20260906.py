from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUT = Path("semiconductor_alfred_information_snapshot_cache_receipt_20260906.json")
CACHE = Path("semiconductor_alfred_information_snapshot_cache_20260906.json")
BASE = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
SERIES = {"ip": "IPG3344S", "util": "CAPUTLHITEK2S"}
FIRST = date(2015, 2, 25)
LAST = date(2026, 8, 25)
UA = "research-compute-public/1.0"
FEATURES = [
    "semi_ip_change_1m", "semi_ip_change_3m", "semi_ip_change_12m",
    "hitek_capacity_utilization", "hitek_capacity_utilization_change_3m",
    "hitek_capacity_utilization_change_12m",
]


def add_months(d: date, n: int, day: int | None = None) -> date:
    total = d.year * 12 + d.month - 1 + n
    y, m = divmod(total, 12)
    return date(y, m + 1, d.day if day is None else day)


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def snapshots():
    d = FIRST
    while d <= LAST:
        yield d
        d = add_months(d, 1, 25)


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


def fetch_snapshot(series_id: str, snapshot: date):
    query = urlencode({
        "id": series_id,
        "cosd": "2014-01-01",
        "coed": snapshot.isoformat(),
        "vintage_date": snapshot.isoformat(),
    })
    rows = list(csv.reader(io.StringIO(get_text(BASE + "?" + query))))
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{series_id} {snapshot}: invalid CSV")
    values = {}
    for row in rows[1:]:
        if len(row) < 2 or not row[0] or row[1] in {"", "."}:
            continue
        values[date.fromisoformat(row[0])] = float(row[1])
    if not values:
        raise RuntimeError(f"{series_id} {snapshot}: no observations")
    return values, rows[0][1]


def value(values, d: date, series_id: str, snapshot: date):
    if d not in values:
        raise RuntimeError(f"{series_id} snapshot={snapshot} missing required observation={d}")
    return values[d]


def lag_month(d: date, n: int) -> date:
    return add_months(month_start(d), -n, 1)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main():
    rows = []
    requests = 0
    for snapshot in snapshots():
        ip, ip_col = fetch_snapshot(SERIES["ip"], snapshot); requests += 1
        util, util_col = fetch_snapshot(SERIES["util"], snapshot); requests += 1
        ip0d = max(ip); u0d = max(util)
        ip0 = value(ip, ip0d, SERIES["ip"], snapshot)
        ip1 = value(ip, lag_month(ip0d, 1), SERIES["ip"], snapshot)
        ip3 = value(ip, lag_month(ip0d, 3), SERIES["ip"], snapshot)
        ip12 = value(ip, lag_month(ip0d, 12), SERIES["ip"], snapshot)
        u0 = value(util, u0d, SERIES["util"], snapshot)
        u3 = value(util, lag_month(u0d, 3), SERIES["util"], snapshot)
        u12 = value(util, lag_month(u0d, 12), SERIES["util"], snapshot)
        if min(ip0, ip1, ip3, ip12) <= 0:
            raise RuntimeError(f"{snapshot}: nonpositive IP input")
        rows.append({
            "available_from": snapshot.isoformat(),
            "semi_ip_latest_observation_month": ip0d.isoformat(),
            "hitek_util_latest_observation_month": u0d.isoformat(),
            "source_columns": {"ip": ip_col, "util": util_col},
            "semi_ip_change_1m": ip0 / ip1 - 1.0,
            "semi_ip_change_3m": ip0 / ip3 - 1.0,
            "semi_ip_change_12m": ip0 / ip12 - 1.0,
            "hitek_capacity_utilization": u0,
            "hitek_capacity_utilization_change_3m": u0 - u3,
            "hitek_capacity_utilization_change_12m": u0 - u12,
        })
        time.sleep(0.02)

    if len(rows) != 139:
        raise RuntimeError(f"snapshot row count={len(rows)} expected=139")
    cache = {
        "schema": "public_compute.semiconductor_alfred_information_snapshot_cache.v1",
        "source_parent_pr": 44,
        "failed_fixed_lag_parent_pr": 45,
        "source": "ALFRED key-free graph CSV",
        "series": SERIES,
        "snapshot_schedule": "monthly calendar day 25",
        "rebase_policy": "IP changes computed entirely inside each same-vintage snapshot",
        "features": FEATURES,
        "rows": rows,
    }
    raw = canonical(cache)
    sha = hashlib.sha256(raw).hexdigest()
    CACHE.write_bytes(raw + b"\n")
    receipt = {
        "schema": "public_compute.semiconductor_alfred_information_snapshot_cache_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_path": str(CACHE), "cache_sha256": sha, "cache_bytes": len(raw) + 1,
        "cache_rows": len(rows), "first_available_from": rows[0]["available_from"],
        "last_available_from": rows[-1]["available_from"], "http_requests": requests,
        "max_ip_observation_lag_days": max((date.fromisoformat(r["available_from"]) - date.fromisoformat(r["semi_ip_latest_observation_month"])).days for r in rows),
        "max_util_observation_lag_days": max((date.fromisoformat(r["available_from"]) - date.fromisoformat(r["hitek_util_latest_observation_month"])).days for r in rows),
        "status": "PASS", "targets_computed": False, "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "next_boundary": "validate and persist these exact cache bytes by SHA, then run the predeclared target-specific path-head consumer on matched rows",
        "research_only": True, "promotion_authority": False, "runtime_mutation": False,
        "broker_action": False, "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("SEMICONDUCTOR_ALFRED_INFORMATION_SNAPSHOT_CACHE=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        failure = {
            "schema": "public_compute.semiconductor_alfred_information_snapshot_cache_receipt.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(), "status": "FAIL",
            "error": str(exc), "targets_computed": False, "model_executed": False,
            "external_semiconductor_holdouts_loaded": False, "research_only": True,
            "promotion_authority": False, "runtime_mutation": False, "broker_action": False,
            "live_trading_change": False,
        }
        OUT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        print("SEMICONDUCTOR_ALFRED_INFORMATION_SNAPSHOT_CACHE=" + json.dumps(failure, sort_keys=True))
        raise
