from __future__ import annotations

import io
import json
import math
import time
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

EPU_URL = "https://www.policyuncertainty.com/media/US_Policy_Uncertainty_Data.xlsx"
START = "1999-01-01"
END = "2026-09-11"
COST_BPS = 10.0
FOLDS = [
    ("2000-01-01", "2007-12-31"),
    ("2008-01-01", "2015-12-31"),
    ("2016-01-01", "2021-12-31"),
    ("2022-01-01", END),
]


def cagr(r: pd.Series) -> float | None:
    if len(r) < 2:
        return None
    years = (r.index[-1] - r.index[0]).days / 365.25
    total = float((1 + r).prod())
    if years <= 0 or total <= 0:
        return None
    return total ** (1 / years) - 1


def mdd(r: pd.Series) -> float:
    e = (1 + r).cumprod()
    return float((e / e.cummax() - 1).min())


def stats(r: pd.Series) -> dict:
    return {"cagr": cagr(r), "max_drawdown": mdd(r), "vol": float(r.std() * math.sqrt(252)), "days": int(len(r))}


def fetch_epu() -> pd.Series:
    raw = None
    last = None
    for attempt in range(4):
        try:
            r = requests.get(EPU_URL, headers={"User-Agent": "XoticHaze-Research/1.0"}, timeout=(15, 90))
            r.raise_for_status()
            raw = r.content
            if len(raw) > 5000:
                break
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    if raw is None or len(raw) <= 5000:
        raise RuntimeError(f"EPU download failed: {last!r}")
    x = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
    required = {"Year", "Month", "News_Based_Policy_Uncert_Index"}
    if not required.issubset(set(x.columns)):
        raise RuntimeError(f"unexpected EPU columns: {list(x.columns)}")
    x = x.dropna(subset=["Year", "Month", "News_Based_Policy_Uncert_Index"]).copy()
    x["date"] = pd.to_datetime(dict(year=x["Year"].astype(int), month=x["Month"].astype(int), day=1))
    x["epu"] = pd.to_numeric(x["News_Based_Policy_Uncert_Index"], errors="coerce")
    x = x.dropna(subset=["epu"]).sort_values("date")
    # Source states the preceding two months may be revised. To keep the latest-vintage
    # history from informing a live decision too early, wait three month-ends before use.
    x["available"] = x["date"].dt.to_period("M").dt.to_timestamp("M") + pd.offsets.MonthEnd(3)
    x["median"] = x["epu"].expanding(min_periods=24).median()
    x["defensive_w"] = (x["epu"] > x["median"]).astype(float)
    return x.set_index("available")["defensive_w"].dropna().sort_index()


def evaluate(d: pd.DataFrame, a: str, b: str) -> dict:
    z = d.loc[a:b]
    return {
        "strategy": stats(z["strategy"]),
        "control": stats(z["control"]),
        "XLP": stats(z["XLP"]),
        "XLY": stats(z["XLY"]),
        "SPY": stats(z["SPY"]),
        "matched_excess_cagr": cagr(z["strategy"]) - cagr(z["control"]),
        "spy_excess_cagr": cagr(z["strategy"]) - cagr(z["SPY"]),
        "switches": int(z["switch"].sum()),
        "defensive_weight_mean": float(z["defensive_w"].mean()),
    }


def main() -> None:
    sig = fetch_epu()
    raw = yf.download(["XLP", "XLY", "SPY"], start=START, end="2026-09-12", auto_adjust=True, progress=False, group_by="column")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[["XLP", "XLY", "SPY"]].dropna(how="any")
    r = close.pct_change().dropna()
    d = r.join(sig.reindex(r.index, method="ffill").rename("defensive_w")).dropna()
    d["cyclical_w"] = 1 - d["defensive_w"]
    d["switch"] = d["defensive_w"].diff().abs().fillna(0.0)
    d["strategy"] = d["defensive_w"] * d["XLP"] + d["cyclical_w"] * d["XLY"] - d["switch"] * (COST_BPS / 10000.0)
    d["control"] = 0.5 * d["XLP"] + 0.5 * d["XLY"]

    overall = evaluate(d, "2000-01-01", END)
    folds = [evaluate(d, a, b) for a, b in FOLDS]
    positive = sum(1 for f in folds if f["matched_excess_cagr"] > 0)
    decision = "P549_SUPPORTED" if overall["matched_excess_cagr"] > 0 and positive >= 3 else "P549_NOT_SUPPORTED_NO_RESCUE"
    out = {
        "schema": "research.p549_epu_defensive_cyclical_r1",
        "parent": "P549",
        "claim": "News-derived US economic policy uncertainty can causally rotate between defensive and cyclical consumer-sector funds with durable after-cost excess over a static matched sector mix.",
        "frozen_contract": {
            "source": EPU_URL,
            "source_field": "News_Based_Policy_Uncert_Index",
            "revision_guard": "three month-ends after observation month because source states preceding two months may revise",
            "signal": "XLP when EPU exceeds its expanding median after 24 months of history; XLY otherwise",
            "control": "static 50/50 XLP/XLY",
            "opportunity_controls": ["XLP", "XLY", "SPY"],
            "cost_bps_per_full_switch": COST_BPS,
            "folds": FOLDS,
            "no_parameter_rescue": True,
        },
        "overall": overall,
        "folds": folds,
        "positive_fold_count": positive,
        "decision": decision,
        "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p549_epu_defensive_cyclical_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
