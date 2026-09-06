from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path

EXPECTED_FEATURES = [
    "semi_ip_change_1m",
    "semi_ip_change_3m",
    "semi_ip_change_12m",
    "hitek_capacity_utilization",
    "hitek_capacity_utilization_change_3m",
    "hitek_capacity_utilization_change_12m",
]
FIRST = date(2015, 1, 1)
LAST = date(2026, 7, 1)
EXPECTED_ROWS = 139


def add_months(d: date, n: int) -> date:
    total = d.year * 12 + d.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)


def expected_available(m: date) -> date:
    nxt = add_months(m, 1)
    return date(nxt.year, nxt.month, 25)


def validate(path: str | Path):
    p = Path(path)
    doc = json.loads(p.read_text())
    if doc.get("schema") != "public_compute.semiconductor_alfred_first_print_cache.v1":
        raise ValueError("unexpected cache schema")
    if doc.get("series") != {"ip": "IPG3344S", "util": "CAPUTLHITEK2S"}:
        raise ValueError("unexpected source series")
    if doc.get("features") != EXPECTED_FEATURES:
        raise ValueError("unexpected feature contract")
    rows = doc.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_ROWS:
        raise ValueError(f"cache row count={0 if not isinstance(rows,list) else len(rows)} expected={EXPECTED_ROWS}")

    for i, row in enumerate(rows):
        m = add_months(FIRST, i)
        if row.get("observation_month") != m.isoformat():
            raise ValueError(f"row {i}: observation_month={row.get('observation_month')} expected={m}")
        available = expected_available(m)
        if row.get("available_from") != available.isoformat():
            raise ValueError(f"row {i}: available_from={row.get('available_from')} expected={available}")
        suffix = available.strftime("%Y%m%d")
        cols = row.get("source_columns") or {}
        if not re.fullmatch(rf"IPG3344S_{suffix}", str(cols.get("ip") or "")):
            raise ValueError(f"row {i}: IP source column does not match vintage {suffix}")
        if not re.fullmatch(rf"CAPUTLHITEK2S_{suffix}", str(cols.get("util") or "")):
            raise ValueError(f"row {i}: utilization source column does not match vintage {suffix}")
        for feature in EXPECTED_FEATURES:
            v = row.get(feature)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(float(v)):
                raise ValueError(f"row {i}: nonfinite {feature}={v}")
        if not (0.0 <= float(row["hitek_capacity_utilization"]) <= 100.0):
            raise ValueError(f"row {i}: capacity utilization outside [0,100]")

    if rows[-1]["observation_month"] != LAST.isoformat():
        raise ValueError("unexpected last observation month")
    return doc


if __name__ == "__main__":
    try:
        validate(sys.argv[1])
        print("SEMICONDUCTOR_ALFRED_FIRST_PRINT_CACHE=VALID")
    except Exception as exc:
        print(f"SEMICONDUCTOR_ALFRED_FIRST_PRINT_CACHE=INVALID {exc}", file=sys.stderr)
        raise SystemExit(2)
