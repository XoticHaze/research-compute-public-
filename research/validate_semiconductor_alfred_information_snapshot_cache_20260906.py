from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path

FEATURES = [
    "semi_ip_change_1m", "semi_ip_change_3m", "semi_ip_change_12m",
    "hitek_capacity_utilization", "hitek_capacity_utilization_change_3m",
    "hitek_capacity_utilization_change_12m",
]
FIRST = date(2015, 2, 25)
LAST = date(2026, 8, 25)


def add_months(d: date, n: int) -> date:
    total = d.year * 12 + d.month - 1 + n
    y, m = divmod(total, 12)
    return date(y, m + 1, 25)


def validate(path):
    doc = json.loads(Path(path).read_text())
    if doc.get("schema") != "public_compute.semiconductor_alfred_information_snapshot_cache.v1":
        raise ValueError("unexpected schema")
    if doc.get("series") != {"ip": "IPG3344S", "util": "CAPUTLHITEK2S"}:
        raise ValueError("unexpected series")
    if doc.get("features") != FEATURES:
        raise ValueError("unexpected feature contract")
    rows = doc.get("rows")
    if not isinstance(rows, list) or len(rows) != 139:
        raise ValueError(f"row count={0 if not isinstance(rows,list) else len(rows)} expected=139")
    for i, row in enumerate(rows):
        snapshot = add_months(FIRST, i)
        if row.get("available_from") != snapshot.isoformat():
            raise ValueError(f"row {i}: snapshot discontinuity")
        suffix = snapshot.strftime("%Y%m%d")
        cols = row.get("source_columns") or {}
        if not re.fullmatch(rf"IPG3344S_{suffix}", str(cols.get("ip") or "")):
            raise ValueError(f"row {i}: IP source-vintage mismatch")
        if not re.fullmatch(rf"CAPUTLHITEK2S_{suffix}", str(cols.get("util") or "")):
            raise ValueError(f"row {i}: utilization source-vintage mismatch")
        for audit in ("semi_ip_latest_observation_month", "hitek_util_latest_observation_month"):
            obs = date.fromisoformat(str(row.get(audit)))
            if obs > snapshot:
                raise ValueError(f"row {i}: future audit observation {audit}={obs}")
        for f in FEATURES:
            v = row.get(f)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                raise ValueError(f"row {i}: nonfinite {f}={v}")
        if not 0.0 <= float(row["hitek_capacity_utilization"]) <= 100.0:
            raise ValueError(f"row {i}: utilization outside [0,100]")
    if rows[-1]["available_from"] != LAST.isoformat():
        raise ValueError("unexpected last snapshot")
    return doc


if __name__ == "__main__":
    try:
        validate(sys.argv[1])
        print("SEMICONDUCTOR_ALFRED_INFORMATION_SNAPSHOT_CACHE=VALID")
    except Exception as exc:
        print(f"SEMICONDUCTOR_ALFRED_INFORMATION_SNAPSHOT_CACHE=INVALID {exc}", file=sys.stderr)
        raise SystemExit(2)
