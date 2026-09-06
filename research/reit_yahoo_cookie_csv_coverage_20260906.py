#!/usr/bin/env python3
"""Public source-only diagnostic for frozen Equity REIT holdout history.

Tests Yahoo's cookie+crumb CSV history endpoint as an alternate access form after
chart endpoints returned truncated AVB/EQR history. This does not execute a
model, compute holdout economics, substitute symbols, or authorize a source
switch.
"""
from __future__ import annotations

import csv
import datetime as dt
import http.cookiejar
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SYMBOLS = ("AVB", "EQR", "ESS", "DLR")
START = dt.datetime(2014, 1, 1, tzinfo=dt.timezone.utc)
END_EXCLUSIVE = dt.datetime(2026, 9, 2, tzinfo=dt.timezone.utc)
OUTPUT = Path("reit_yahoo_cookie_csv_coverage_20260906.json")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def _epoch(value: dt.datetime) -> int:
    return int(value.timestamp())


def _build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Accept", "text/csv,application/json,text/plain,*/*"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    return opener


def _get_crumb(opener: urllib.request.OpenerDirector) -> str:
    # Yahoo often sets an access cookie even when fc.yahoo.com returns an HTTP
    # error. Preserve the opener/cookie jar and then request the crumb.
    try:
        with opener.open("https://fc.yahoo.com", timeout=20) as response:
            response.read(64)
    except urllib.error.HTTPError:
        pass
    with opener.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=20) as response:
        crumb = response.read().decode("utf-8", "replace").strip()
    if not crumb or len(crumb) > 256 or "<" in crumb:
        raise RuntimeError("Yahoo crumb unavailable or malformed")
    return crumb


def _download_csv(opener: urllib.request.OpenerDirector, crumb: str, symbol: str) -> tuple[str, str]:
    params = urllib.parse.urlencode(
        {
            "period1": _epoch(START),
            "period2": _epoch(END_EXCLUSIVE),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
            "crumb": crumb,
        }
    )
    errors: list[str] = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v7/finance/download/{urllib.parse.quote(symbol)}?{params}"
        try:
            with opener.open(url, timeout=30) as response:
                body = response.read().decode("utf-8", "replace")
            if body.startswith("Date,"):
                return host, body
            errors.append(f"{host}: non_csv_prefix={body[:80]!r}")
        except Exception as exc:  # source diagnostic: retain narrow public error only
            errors.append(f"{host}: {type(exc).__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def _summarize_csv(body: str) -> dict[str, object]:
    rows = []
    for row in csv.DictReader(io.StringIO(body)):
        date = (row.get("Date") or "").strip()
        close = (row.get("Adj Close") or row.get("Close") or "").strip()
        if date and close and close.lower() != "null":
            rows.append((date, close))
    first = rows[0][0] if rows else None
    last = rows[-1][0] if rows else None
    long_history = bool(rows) and len(rows) >= 2500 and first <= "2014-01-10"
    return {
        "rows": len(rows),
        "first": first,
        "last": last,
        "long_history": long_history,
    }


def main() -> int:
    receipt: dict[str, object] = {
        "schema": "public_compute.reit_yahoo_cookie_csv_coverage.v1",
        "family": "equity_reits",
        "frozen_external_holdout": list(SYMBOLS),
        "frozen_development_ceiling": "2026-09-01T13:30:00+00:00",
        "source": "Yahoo cookie+crumb CSV download",
        "model_executed": False,
        "target_returns_computed": False,
        "source_switch_authorized": False,
        "ticker_substitution_authorized": False,
        "promotion_authority": False,
        "live_trading_change": False,
        "research_only": True,
        "symbols": {},
    }

    opener = _build_opener()
    try:
        crumb = _get_crumb(opener)
        receipt["crumb_acquired"] = True
    except Exception as exc:
        receipt.update(
            {
                "status": "COOKIE_CSV_ACCESS_UNAVAILABLE",
                "crumb_acquired": False,
                "error": f"{type(exc).__name__}: {exc}",
                "candidate_source_mechanics_supported": False,
            }
        )
        OUTPUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print("REIT_YAHOO_COOKIE_CSV=" + json.dumps(receipt, sort_keys=True))
        return 0

    symbol_results: dict[str, object] = {}
    for symbol in SYMBOLS:
        try:
            host, body = _download_csv(opener, crumb, symbol)
            summary = _summarize_csv(body)
            summary["host"] = host
            summary["status"] = "PASS"
        except Exception as exc:
            summary = {
                "status": "FAIL",
                "error": f"{type(exc).__name__}: {exc}",
                "rows": 0,
                "first": None,
                "last": None,
                "long_history": False,
            }
        symbol_results[symbol] = summary

    receipt["symbols"] = symbol_results
    long_symbols = [s for s in SYMBOLS if bool(symbol_results[s].get("long_history"))]
    supported = len(long_symbols) == len(SYMBOLS)
    receipt.update(
        {
            "long_history_symbols": long_symbols,
            "candidate_source_mechanics_supported": supported,
            "status": "LONG_HISTORY_RESTORED" if supported else "LONG_HISTORY_NOT_RESTORED",
            "next_authorized_step": (
                "freeze and execute same-symbol source-parity consumer before holdout economics"
                if supported
                else "do not execute holdout economics from this access form"
            ),
        }
    )
    OUTPUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("REIT_YAHOO_COOKIE_CSV=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
