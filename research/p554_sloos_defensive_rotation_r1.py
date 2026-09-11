from __future__ import annotations

import io
import json
import math
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

END = "2026-09-11"
COST_BPS = 10.0
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DRTSCILM"
FOLDS = [
    ("2000-01-01", "2007-12-31"),
    ("2008-01-01", "2013-12-31"),
    ("2014-01-01", "2019-12-31"),
    ("2020-01-01", END),
]


def cagr(r: pd.Series):
    if len(r) < 2:
        return None
    years = (r.index[-1] - r.index[0]).days / 365.25
    terminal = float((1 + r).prod())
    return None if years <= 0 or terminal <= 0 else terminal ** (1 / years) - 1


def mdd(r: pd.Series):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def stats(r: pd.Series):
    return {
        "cagr": cagr(r),
        "max_drawdown": mdd(r),
        "vol": float(r.std() * math.sqrt(252)),
        "days": int(len(r)),
    }


def get_sloos():
    r = requests.get(FRED_URL, timeout=(15, 60), headers={"User-Agent": "XoticHaze market research"})
    r.raise_for_status()
    x = pd.read_csv(io.BytesIO(r.content))
    x.columns = [str(c).strip() for c in x.columns]
    date_col = x.columns[0]
    value_col = next(c for c in x.columns if c != date_col)
    x[date_col] = pd.to_datetime(x[date_col], errors="coerce")
    x[value_col] = pd.to_numeric(x[value_col], errors="coerce")
    x = x.dropna().sort_values(date_col).set_index(date_col)[value_col]
    # Preserve P546's causal convention: observation is usable only from the following month.
    monthly = x.resample("ME").last().ffill()
    signal = (monthly > 0).astype(float).shift(1).dropna().rename("tightening")
    return signal, {
        "fred_series": "DRTSCILM",
        "observations": int(x.shape[0]),
        "first_observation": str(x.index.min().date()),
        "last_observation": str(x.index.max().date()),
    }


def evaluate(d: pd.DataFrame, start: str, end: str):
    z = d.loc[start:end]
    return {
        "strategy": stats(z.strategy),
        "SPY": stats(z.SPY),
        "XLP": stats(z.XLP),
        "matched_excess_cagr": cagr(z.strategy) - cagr(z.SPY),
        "xlp_excess_cagr": cagr(z.strategy) - cagr(z.XLP),
        "switches": int(z.switch.sum()),
        "defensive_weight_mean": float(z.xlp_w.mean()),
    }


def main():
    signal, source_diag = get_sloos()
    raw = yf.download(
        ["SPY", "XLP"],
        start="1999-01-01",
        end="2026-09-12",
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    r = close[["SPY", "XLP"]].dropna().pct_change().dropna()
    d = r.join(signal.reindex(r.index, method="ffill")).dropna()
    d["xlp_w"] = d.tightening
    d["spy_w"] = 1.0 - d.xlp_w
    d["switch"] = d.xlp_w.diff().abs().fillna(0.0)
    d["strategy"] = d.xlp_w * d.XLP + d.spy_w * d.SPY - d.switch * (COST_BPS / 10000.0)

    overall = evaluate(d, "2000-01-01", END)
    folds = [evaluate(d, a, b) for a, b in FOLDS]
    positive = sum(f["matched_excess_cagr"] > 0 for f in folds)
    current_positive = folds[-1]["matched_excess_cagr"] > 0
    supported = overall["matched_excess_cagr"] > 0 and positive >= 3 and current_positive
    decision = "P554_SUPPORTED" if supported else "P554_NOT_SUPPORTED_NO_RESCUE"

    out = {
        "schema": "research.p554_sloos_defensive_rotation_r1",
        "parent": "P554",
        "claim": "Causally lagged SLOOS C&I tightening can rotate fully-invested equity exposure from SPY into consumer staples (XLP) with durable after-cost excess over SPY, including the modern 2020+ regime.",
        "frozen_contract": {
            "series": "FRED DRTSCILM",
            "signal": ">0 => XLP; <=0 => SPY",
            "lag_months": 1,
            "transition_cost_bps": COST_BPS,
            "control": "SPY buy-and-hold over matched dates",
            "folds": FOLDS,
            "gate": "positive aggregate excess, at least 3/4 positive folds, and positive 2020+ fold",
            "no_parameter_rescue": True,
        },
        "source_diagnostics": source_diag,
        "overall": overall,
        "folds": folds,
        "positive_fold_count": positive,
        "current_regime_positive": current_positive,
        "decision": decision,
        "boundaries": {
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p554_sloos_defensive_rotation_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
