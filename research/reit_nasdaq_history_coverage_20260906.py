#!/usr/bin/env python3
"""Source-only Nasdaq historical coverage discriminator for frozen Equity REIT holdout.

Runs after Yahoo chart truncation, Stooq bot challenge, and Yahoo cookie/crumb CSV
rate limiting. It measures only whether the exact frozen symbols have sufficiently
long daily history from Nasdaq's public quote-history endpoint. No model or holdout
economics are executed and no source switch is authorized here.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

SYMBOLS = ("AVB", "EQR", "ESS", "DLR")
OUTPUT = Path("reit_nasdaq_history_coverage_20260906.json")
RANGES = (("01/01/2014", "12/31/2019"), ("01/01/2020", "09/01/2026"))


def _request_json(symbol: str, start: str, end: str) -> dict:
    params = urllib.parse.urlencode(
        {
            "assetclass": "stocks",
            "fromdate": start,
            "todate": end,
            "limit": 5000,
        }
    )
    url = f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(symbol)}/historical?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.nasdaq.com",
            "Referer": f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/historical",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _extract_dates(payload: dict) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    table = data.get("tradesTable") if isinstance(data, dict) else None
    rows = table.get("rows") if isinstance(table, dict) else None
    dates: list[str] = []
    if not isinstance(rows, list):
        return dates
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw = str(row.get("date") or row.get("Date") or "").strip()
        if not raw:
            continue
        parsed = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                parsed = dt.datetime.strptime(raw, fmt).date()
                break
            except ValueError:
                pass
        if parsed is not None:
            dates.append(parsed.isoformat())
    return dates


def main() -> int:
    results: dict[str, dict] = {}
    for symbol in SYMBOLS:
        all_dates: set[str] = set()
        segments = []
        for start, end in RANGES:
            try:
                payload = _request_json(symbol, start, end)
                dates = _extract_dates(payload)
                all_dates.update(dates)
                status = "PASS" if dates else "NO_ROWS"
                error = None
            except Exception as exc:
                dates = []
                status = "FAIL"
                error = f"{type(exc).__name__}: {exc}"
            segments.append(
                {
                    "from": start,
                    "to": end,
                    "status": status,
                    "rows": len(dates),
                    "first": min(dates) if dates else None,
                    "last": max(dates) if dates else None,
                    "error": error,
                }
            )
        dates_sorted = sorted(all_dates)
        results[symbol] = {
            "rows": len(dates_sorted),
            "first": dates_sorted[0] if dates_sorted else None,
            "last": dates_sorted[-1] if dates_sorted else None,
            "long_history": bool(dates_sorted) and len(dates_sorted) >= 2500 and dates_sorted[0] <= "2014-01-10",
            "segments": segments,
        }

    long_symbols = [s for s in SYMBOLS if results[s]["long_history"]]
    supported = len(long_symbols) == len(SYMBOLS)
    receipt = {
        "schema": "public_compute.reit_nasdaq_history_coverage.v1",
        "family": "equity_reits",
        "frozen_external_holdout": list(SYMBOLS),
        "frozen_development_ceiling": "2026-09-01T13:30:00+00:00",
        "source": "Nasdaq public quote historical endpoint",
        "symbols": results,
        "long_history_symbols": long_symbols,
        "candidate_source_mechanics_supported": supported,
        "status": "LONG_HISTORY_RESTORED" if supported else "LONG_HISTORY_NOT_RESTORED",
        "next_authorized_step": (
            "freeze and execute same-symbol source-parity consumer before holdout economics"
            if supported
            else "do not execute holdout economics from this source path"
        ),
        "model_executed": False,
        "target_returns_computed": False,
        "source_switch_authorized": False,
        "ticker_substitution_authorized": False,
        "promotion_authority": False,
        "live_trading_change": False,
        "research_only": True,
    }
    OUTPUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("REIT_NASDAQ_HISTORY=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
