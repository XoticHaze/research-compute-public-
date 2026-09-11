from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import yfinance as yf

START = "2013-08-01"
END = "2026-09-11"
COST_BPS = 10.0
FOLDS = [
    ("2014-01-01", "2017-12-31"),
    ("2018-01-01", "2021-12-31"),
    ("2022-01-01", END),
]


def cagr(r: pd.Series) -> float | None:
    if len(r) < 2:
        return None
    years = (r.index[-1] - r.index[0]).days / 365.25
    total = float((1.0 + r).prod())
    if years <= 0 or total <= 0:
        return None
    return total ** (1.0 / years) - 1.0


def max_drawdown(r: pd.Series) -> float:
    equity = (1.0 + r).cumprod()
    return float((equity / equity.cummax() - 1.0).min())


def stats(r: pd.Series) -> dict:
    return {
        "cagr": cagr(r),
        "max_drawdown": max_drawdown(r),
        "vol": float(r.std() * math.sqrt(252)),
        "days": int(len(r)),
    }


def evaluate(d: pd.DataFrame, a: str, b: str) -> dict:
    z = d.loc[a:b]
    s = z["strategy"]
    c = z["control"]
    return {
        "strategy": stats(s),
        "control": stats(c),
        "QUAL": stats(z["QUAL"]),
        "MTUM": stats(z["MTUM"]),
        "SPY": stats(z["SPY"]),
        "matched_excess_cagr": cagr(s) - cagr(c),
        "spy_excess_cagr": cagr(s) - cagr(z["SPY"]),
        "switches": int(z["switch"].sum()),
        "qual_weight_mean": float(z["qual_w"].mean()),
    }


def main() -> None:
    raw = yf.download(
        ["^SKEW", "QUAL", "MTUM", "SPY"],
        start=START,
        end="2026-09-12",
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[["^SKEW", "QUAL", "MTUM", "SPY"]].dropna(how="any")
    returns = close[["QUAL", "MTUM", "SPY"]].pct_change().dropna()

    # Freeze decision topology before seeing performance: use each completed
    # month-end SKEW close, compare it only with the expanding median available
    # through that month, and apply the resulting style choice next month.
    skew_month = close["^SKEW"].resample("ME").last().dropna()
    expanding_median = skew_month.expanding(min_periods=12).median()
    high_tail_risk = (skew_month > expanding_median).astype(float)
    next_month_signal = high_tail_risk.shift(1).dropna()
    signal_daily = next_month_signal.reindex(returns.index, method="ffill").rename("qual_w")

    d = returns.join(signal_daily).dropna()
    d["mtum_w"] = 1.0 - d["qual_w"]
    d["switch"] = d["qual_w"].diff().abs().fillna(0.0)
    d["strategy"] = (
        d["qual_w"] * d["QUAL"]
        + d["mtum_w"] * d["MTUM"]
        - d["switch"] * (COST_BPS / 10000.0)
    )
    d["control"] = 0.5 * d["QUAL"] + 0.5 * d["MTUM"]

    overall = evaluate(d, "2014-01-01", END)
    folds = [evaluate(d, a, b) for a, b in FOLDS]
    positive = sum(1 for f in folds if f["matched_excess_cagr"] > 0)
    supported = overall["matched_excess_cagr"] > 0 and positive >= 2
    decision = "P548_SUPPORTED" if supported else "P548_NOT_SUPPORTED_NO_RESCUE"

    out = {
        "schema": "research.p548_skew_quality_momentum_r1",
        "parent": "P548",
        "claim": "Options-implied tail-risk pricing can causally rotate between US quality and momentum funds with durable after-cost excess over a static 50/50 style control.",
        "frozen_contract": {
            "information_source": "CBOE SKEW index via Yahoo Finance ^SKEW daily close",
            "signal": "high tail risk when completed month-end SKEW exceeds its expanding historical median; signal applied the following month",
            "allocation": "QUAL in high-tail-risk months, MTUM otherwise",
            "control": "static 50/50 QUAL/MTUM",
            "opportunity_controls": ["QUAL", "MTUM", "SPY"],
            "cost_bps_per_full_style_switch": COST_BPS,
            "minimum_signal_history_months": 12,
            "folds": FOLDS,
            "no_parameter_rescue": True,
        },
        "overall": overall,
        "folds": folds,
        "positive_fold_count": positive,
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
    Path("artifacts/p548_skew_quality_momentum_r1.json").write_text(
        json.dumps(out, indent=2, sort_keys=True)
    )
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
