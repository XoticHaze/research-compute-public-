from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

TICKERS = ["DOV","SWK","GWW","FAST","IEX","XYL","PNR","GNRC","XLI","SPY"]
START = "2012-01-01"
END = "2026-09-12"
MIN_FIRST_DATE = pd.Timestamp("2012-03-01")
MAX_MISSING_FRACTION = 0.01


def main() -> None:
    raw = yf.download(TICKERS, start=START, end=END, auto_adjust=True, progress=False, group_by="column", threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    rows = {}
    for t in TICKERS:
        s = close[t].dropna() if t in close.columns else pd.Series(dtype=float)
        rows[t] = {
            "observations": int(len(s)),
            "first_date": None if s.empty else str(s.index.min().date()),
            "last_date": None if s.empty else str(s.index.max().date()),
        }
    common = close[TICKERS].dropna(how="any") if set(TICKERS).issubset(close.columns) else pd.DataFrame()
    total_union = len(close.dropna(how="all"))
    missing_fraction = None if total_union == 0 else 1 - len(common) / total_union
    first_common = None if common.empty else common.index.min()
    ready = bool(
        not common.empty
        and first_common <= MIN_FIRST_DATE
        and missing_fraction is not None
        and missing_fraction <= MAX_MISSING_FRACTION
    )
    out = {
        "schema": "research.p555_price_coverage_r0",
        "parent": "P555",
        "decision": "PRICE_COVERAGE_READY" if ready else "PRICE_COVERAGE_NEEDS_REPAIR",
        "requested_start": START,
        "requested_end": END,
        "ticker_diagnostics": rows,
        "common_observations": int(len(common)),
        "common_first_date": None if common.empty else str(common.index.min().date()),
        "common_last_date": None if common.empty else str(common.index.max().date()),
        "union_observations": int(total_union),
        "common_missing_fraction_vs_union": missing_fraction,
        "gate": {"common_first_on_or_before": str(MIN_FIRST_DATE.date()), "max_missing_fraction": MAX_MISSING_FRACTION},
        "boundaries": {"scientific_alpha_claim": False, "portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p555_price_coverage_r0.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))

if __name__ == "__main__":
    main()
