from __future__ import annotations

import io
import json
import math
import time
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

SERIES = "DRTSCILM"
FRED_URL = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES}"
START = "2000-06-01"
END = "2026-09-11"
COST_BPS = 10.0
FOLDS = [
    ("2000-06-01", "2007-12-31"),
    ("2008-01-01", "2013-12-31"),
    ("2014-01-01", "2019-12-31"),
    ("2020-01-01", END),
]


def fetch_fred() -> pd.Series:
    raw = None
    last = None
    for attempt in range(4):
        try:
            r = requests.get(
                FRED_URL,
                headers={"User-Agent": "XoticHaze-Research/1.0"},
                timeout=(15, 90),
            )
            r.raise_for_status()
            raw = r.content
            if len(raw) > 500:
                break
        except Exception as exc:
            last = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    if raw is None or len(raw) <= 500:
        raise RuntimeError(f"FRED {SERIES} fetch failed: {last!r}")
    x = pd.read_csv(io.BytesIO(raw))
    x.columns = ["date", "tightening"]
    x["date"] = pd.to_datetime(x["date"])
    x["tightening"] = pd.to_numeric(x["tightening"], errors="coerce")
    x = x.dropna()
    # Orthogonal causality stress of P546 only: keep the <=0 rule fixed but
    # require two full month-ends after each observation month before use.
    x["available"] = x["date"].dt.to_period("M").dt.to_timestamp("M") + pd.offsets.MonthEnd(2)
    x["equity_w"] = (x["tightening"] <= 0).astype(float)
    return x.set_index("available")["equity_w"].sort_index()


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
    return {
        "cagr": cagr(r),
        "max_drawdown": mdd(r),
        "days": int(len(r)),
        "vol": float(r.std() * math.sqrt(252)),
    }


def evaluate(df: pd.DataFrame, a: str, b: str) -> dict:
    z = df.loc[a:b].copy()
    mean_w = float(z["equity_w"].mean())
    z["control"] = mean_w * z["SPY"]
    s = z["strategy"]
    c = z["control"]
    return {
        "strategy": stats(s),
        "control": stats(c),
        "spy": stats(z["SPY"]),
        "matched_excess_cagr": cagr(s) - cagr(c),
        "equity_weight_mean": mean_w,
        "switches": int(z["switch"].sum()),
    }


def main() -> None:
    signal = fetch_fred()
    px = yf.download("SPY", start=START, end="2026-09-12", auto_adjust=True, progress=False)
    if isinstance(px.columns, pd.MultiIndex):
        close = px["Close"].iloc[:, 0]
    else:
        close = px["Close"]
    r = close.pct_change().dropna().rename("SPY")
    d = r.to_frame().join(signal.reindex(r.index, method="ffill").rename("equity_w")).dropna()
    d["switch"] = d["equity_w"].diff().abs().fillna(0.0)
    d["strategy"] = d["equity_w"] * d["SPY"] - d["switch"] * (COST_BPS / 10000.0)

    overall = evaluate(d, START, END)
    folds = [evaluate(d, a, b) for a, b in FOLDS]
    positive = sum(1 for f in folds if f["matched_excess_cagr"] > 0)
    recent_positive = folds[-1]["matched_excess_cagr"] > 0
    if overall["matched_excess_cagr"] > 0 and positive >= 3 and recent_positive:
        decision = "P547_DURABLE_CAUSAL_STRESS_SUPPORTED"
    elif overall["matched_excess_cagr"] > 0 and positive >= 3:
        decision = "P547_LAG_ROBUST_BUT_RECENT_DURABILITY_FAIL"
    else:
        decision = "P547_NOT_SUPPORTED_NO_RESCUE"

    out = {
        "schema": "research.p547_sloos_conservative_lag_r1",
        "parent": "P547",
        "relationship": "orthogonal causality stress of frozen P546 SLOOS <=0 SPY/cash rule",
        "claim": "P546's lending-standards edge remains after a more conservative two-month-end information-availability lag and persists across chronology, including the recent regime.",
        "frozen_contract": {
            "source": f"FRED {SERIES}",
            "signal": "SPY when net tightening <= 0; zero-return cash otherwise",
            "availability": "two complete month-ends after observation month",
            "cost_bps_per_equity_transition": COST_BPS,
            "control": "static SPY exposure matched to strategy mean equity exposure within each evaluation window; zero-return cash residual",
            "folds": FOLDS,
            "no_parameter_rescue": True,
        },
        "overall": overall,
        "folds": folds,
        "positive_fold_count": positive,
        "recent_fold_positive": recent_positive,
        "decision": decision,
        "survey_points": int(len(signal)),
        "boundaries": {
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p547_sloos_conservative_lag_r1.json").write_text(
        json.dumps(out, indent=2, sort_keys=True)
    )
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
