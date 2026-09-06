from __future__ import annotations

"""Source-only archive coverage diagnostic for the frozen Equity REIT holdout.

The prior Stooq attempt failed at source transport because the hosted runner received a
JavaScript verification page. This continuation tests Nasdaq's public historical endpoint
without changing the frozen AVB/EQR/ESS/DLR holdout, thresholds, model, or target semantics.
It does not authorize a source switch or compute holdout economics.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SYMBOLS = ("AVB", "EQR", "ESS", "DLR")
CONTROL = "AAPL"
OUT = Path("reit_stooq_archive_parity_20260905.json")


def nasdaq(symbol: str) -> dict:
    query = urlencode({"assetclass": "stocks", "fromdate": "01/01/2014", "todate": "09/01/2026", "limit": 5000})
    url = f"https://api.nasdaq.com/api/quote/{symbol}/historical?{query}"
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/historical",
    })
    try:
        with urlopen(req, timeout=30) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
        payload = json.loads(body)
        rows = (((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or [])
        dates = [str(row.get("date")) for row in rows if isinstance(row, dict) and row.get("date")]
        return {
            "http_status": status,
            "rows": len(rows),
            "first_date": dates[-1] if dates else None,
            "last_date": dates[0] if dates else None,
            "long_history": len(rows) >= 1000,
            "error": None,
        }
    except Exception as exc:
        return {
            "http_status": None,
            "rows": 0,
            "first_date": None,
            "last_date": None,
            "long_history": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    control = nasdaq(CONTROL)
    results = {symbol: nasdaq(symbol) for symbol in SYMBOLS}
    long_history = [symbol for symbol, row in results.items() if row["long_history"]]
    transport_ok = bool(control["long_history"])
    candidate = transport_ok and len(long_history) == len(SYMBOLS)
    out = {
        "schema": "public_compute.reit_archive_source_probe.v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Nasdaq historical API",
        "frozen_holdout": list(SYMBOLS),
        "transport_control_symbol": CONTROL,
        "transport_control": control,
        "transport_control_pass": transport_ok,
        "symbols": results,
        "long_history_symbols": long_history,
        "candidate_source_mechanics_supported": candidate,
        "status": "CANDIDATE_SOURCE_MECHANICS" if candidate else ("SOURCE_TRANSPORT_UNAVAILABLE" if not transport_ok else "REIT_HISTORY_INCOMPLETE"),
        "source_switch_authorized": False,
        "authorization_boundary": "candidate source mechanics require separate return-parity proof before any frozen holdout economics",
        "target_returns_computed": False,
        "model_executed": False,
        "research_only": True,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("REIT_ARCHIVE_SOURCE_PROBE=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
