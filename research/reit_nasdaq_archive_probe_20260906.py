#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SYMBOLS = ("AVB", "EQR", "ESS", "DLR", "AAPL")
START = "01/01/2014"
END = "09/01/2026"
OUT = Path("reit_nasdaq_archive_probe_20260906.json")


def fetch(symbol: str) -> dict:
    params = urllib.parse.urlencode({
        "assetclass": "stocks",
        "fromdate": START,
        "todate": END,
        "limit": 5000,
    })
    url = f"https://api.nasdaq.com/api/quote/{symbol}/historical?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/historical",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
        parsed = json.loads(body)
        rows = (((parsed.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
        dates = [str(r.get("date")) for r in rows if isinstance(r, dict) and r.get("date")]
        return {
            "http_status": status,
            "rows": len(rows),
            "first_date": dates[-1] if dates else None,
            "last_date": dates[0] if dates else None,
            "usable_long_history": len(rows) >= 1000,
            "error": None,
        }
    except Exception as exc:
        return {
            "http_status": None,
            "rows": 0,
            "first_date": None,
            "last_date": None,
            "usable_long_history": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    symbols = {s: fetch(s) for s in SYMBOLS}
    controls_ok = symbols["AAPL"]["usable_long_history"]
    holdout_long = [s for s in ("AVB", "EQR", "ESS", "DLR") if symbols[s]["usable_long_history"]]
    out = {
        "schema": "public_compute.reit_nasdaq_archive_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frozen_holdout": ["AVB", "EQR", "ESS", "DLR"],
        "source": "Nasdaq historical API",
        "request_window": {"start": START, "end": END},
        "symbols": symbols,
        "transport_control_pass": controls_ok,
        "long_history_holdout_symbols": holdout_long,
        "candidate_source_mechanics_supported": controls_ok and len(holdout_long) == 4,
        "model_executed": False,
        "target_returns_computed": False,
        "source_switch_authorized": False,
        "research_only": True,
        "decision": "CANDIDATE_SOURCE_MECHANICS" if controls_ok and len(holdout_long) == 4 else "SOURCE_MECHANICS_NOT_SUFFICIENT",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("REIT_NASDAQ_ARCHIVE_PROBE=" + json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
