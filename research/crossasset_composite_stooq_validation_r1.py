from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path

import pandas as pd

import fixed_multifactor_cross_sectional_r1 as base
import fixed_multifactor_cross_sectional_r1_complete_month as guard

SYMBOLS = ("SPY", "QQQ", "TLT", "GLD", "DBC")
HOSTS = ("stooq.pl", "stooq.com")


def _fetch(symbol: str) -> pd.Series:
    failures = []
    for host in HOSTS:
        url = f"https://{host}/q/d/l/?s={symbol.lower()}.us&i=d&d1=20050101&d2=20260908"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.1",
                "Referer": f"https://{host}/q/d/?s={symbol.lower()}.us",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = response.read()
            frame = pd.read_csv(io.BytesIO(raw))
            if frame.empty or "Date" not in frame or "Close" not in frame:
                failures.append(f"{host}:invalid:{raw[:80]!r}")
                continue
            frame["Date"] = pd.to_datetime(frame["Date"], errors="raise")
            series = pd.to_numeric(frame["Close"], errors="coerce")
            series.index = frame["Date"]
            series = series.dropna().sort_index()
            if len(series) < 1000:
                failures.append(f"{host}:rows={len(series)}")
                continue
            return series.rename(symbol)
        except Exception as exc:
            failures.append(f"{host}:{type(exc).__name__}:{str(exc)[:180]}")
    raise RuntimeError(f"stooq_source_access_exhausted:{symbol}:{failures}")


def stooq_load(symbols):
    requested = tuple(dict.fromkeys((*symbols, "SPY", "QQQ")))
    close = pd.concat([_fetch(symbol) for symbol in requested], axis=1).sort_index()
    close = close.dropna(how="all")
    missing = [symbol for symbol in requested if close[symbol].notna().sum() < 1000]
    if missing:
        raise RuntimeError(f"stooq_missing_history:{missing}")
    return close


base.load = stooq_load
base.features = guard._complete_month_features

if __name__ == "__main__":
    result = base.evaluate("crossasset")
    result["schema"] = "research.crossasset_composite_stooq_validation_r1"
    result["source"] = {
        "provider": "Stooq direct daily CSV",
        "hosts_attempted": list(HOSTS),
        "symbols": [f"{s.lower()}.us" for s in SYMBOLS],
        "source_identity": "https://<stooq.pl|stooq.com>/q/d/l/?s=<symbol>.us&i=d&d1=20050101&d2=20260908",
        "canonical_mm_claim": false
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/crossasset_composite_stooq_validation.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"decision": result["decision"], "window": result["oos_window"], "excess25": result["costs"]["25"]["excess_cagr_vs_equal_weight"], "folds": result["costs"]["25"]["positive_excess_folds"], "excess50": result["costs"]["50"]["excess_cagr_vs_equal_weight"]}, sort_keys=True))
