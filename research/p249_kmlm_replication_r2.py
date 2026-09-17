from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from research.p249_orthogonal_sleeve_tournament_r1 import (
    CASH, CORE_SYMBOLS, END, START_DOWNLOAD, START_EVAL,
    build_core_and_p266_monthly, frame,
)

OUT = Path("research/artifacts/p249_kmlm_replication_r2.json")
TICKERS = list(dict.fromkeys(list(CORE_SYMBOLS) + ["KMLM", CASH]))


def yahoo_chart(symbol: str) -> pd.Series:
    p1 = int(pd.Timestamp(START_DOWNLOAD, tz="UTC").timestamp())
    p2 = int(pd.Timestamp(END, tz="UTC").timestamp())
    q = urllib.parse.urlencode({"period1": p1, "period2": p2, "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    ts = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(None).normalize()
    adj = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
    if adj is None:
        adj = result["indicators"]["quote"][0]["close"]
    return pd.Series(adj, index=ts, name=symbol, dtype=float).dropna()


def main() -> None:
    series = []
    for symbol in TICKERS:
        series.append(yahoo_chart(symbol))
        time.sleep(0.15)
    close = pd.concat(series, axis=1).sort_index().dropna(how="all")
    core, _, diag = build_core_and_p266_monthly(close)
    simple = close[["KMLM", CASH]].resample("ME").last().pct_change(fill_method=None)
    kmlm, cash = simple["KMLM"], simple[CASH]
    windows = {
        "2021+": frame(core, kmlm, cash, "2021-01-01"),
        "2022+": frame(core, kmlm, cash, "2022-01-01"),
        "2023+": frame(core, kmlm, cash, "2023-01-01"),
    }
    blocks = {
        "2021_2022": frame(core, kmlm, cash, "2021-01-01", "2022-12-31"),
        "2023_2024": frame(core, kmlm, cash, "2023-01-01", "2024-12-31"),
        "2025_plus": frame(core, kmlm, cash, "2025-01-01"),
    }
    positive_windows = sum((v["matched_capital_excess_cagr_pp"] or -999) > 0 for v in windows.values())
    positive_blocks = sum(v["months"] >= 18 and (v["matched_capital_excess_cagr_pp"] or -999) > 0 for v in blocks.values())
    supported = bool(positive_windows >= 2 and positive_blocks >= 2 and windows["2021+"]["matched_capital_excess_cagr_pp"] > 0)
    result = {
        "schema": "research.p249_kmlm_replication_r2.v1",
        "workload_id": "P249_KMLM_REPLICATION_R2",
        "contract": {
            "inheritance": "P249_ORTHOGONAL_SLEEVE_TOURNAMENT_R1 KMLM child",
            "core_weight": 0.75,
            "candidate_weight": 0.25,
            "capital_parking_control": "25% BIL + 75% unchanged P249 core",
            "completed_month_cutoff": "2026-08-31",
            "parameter_search": False,
            "transport": "direct Yahoo chart JSON; no yfinance",
            "protected_boundary": "no weight/product/date/cost/control/window/threshold rescue",
        },
        "dynamic_materialization": diag,
        "windows": windows,
        "blocks": blocks,
        "positive_windows": positive_windows,
        "positive_blocks": positive_blocks,
        "decision": "P249_KMLM_REPLICATION_SUPPORTED" if supported else "P249_KMLM_REPLICATION_REJECTED",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
