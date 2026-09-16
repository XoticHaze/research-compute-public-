#!/usr/bin/env python3
"""Fail fast when a cold IBKR login would start inside the daily reset window.

The guard is intentionally conservative: it adds five minutes of margin around
the published North America 00:15-01:45 America/New_York reset window.  A warm
session that is already API-ready is not governed by this script; this guard is
for starting a new authenticated Gateway login.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
BLOCK_START = time(0, 10)
BLOCK_END = time(1, 50)


def parse_now(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("--now must include a timezone offset or Z")
    return dt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", help="Offset-aware ISO timestamp, for deterministic tests")
    args = ap.parse_args()

    now_utc = parse_now(args.now).astimezone(timezone.utc)
    now_et = now_utc.astimezone(ET)
    blocked = BLOCK_START <= now_et.timetz().replace(tzinfo=None) < BLOCK_END

    result = {
        "schema": "mmibkr-login-window-v1",
        "now_utc": now_utc.isoformat(),
        "now_et": now_et.isoformat(),
        "published_reset_window_et": "00:15-01:45",
        "guard_window_et": "00:10-01:50",
        "cold_login_allowed": not blocked,
        "reason": "north_america_daily_reset_guard" if blocked else "outside_reset_guard",
    }
    print("IBKR_LOGIN_WINDOW=" + json.dumps(result, sort_keys=True))
    return 46 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
