from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ASSETS = ["SPY", "IEF", "GLD"]
COSTS = (25, 50, 100)
WINDOWS = {
    "2005": "2005-01-01",
    "2010": "2010-01-01",
    "2015": "2015-01-01",
    "2020": "2020-01-01",
    "2022": "2022-01-01",
}
SLEEVE = 1.0 / len(ASSETS)


def cagr(r: pd.Series) -> float:
    r = pd.Series(r, dtype=float).dropna()
    return float((1.0 + r).prod() ** (12.0 / len(r)) - 1.0) if len(r) else float("nan")


def stats(r: pd.Series) -> dict:
    r = pd.Series(r, dtype=float).dropna()
    eq = (1.0 + r).cumprod()
    vol = float(r.std(ddof=1) * math.sqrt(12.0)) if len(r) > 1 else 0.0
    return {
        "cagr": cagr(r),
        "sharpe_rf0": float(r.mean() * 12.0 / vol) if vol else None,
        "maxdd": float((eq / eq.cummax() - 1.0).min()) if len(eq) else None,
    }


def evaluate(q: pd.DataFrame, cost_bps: int) -> dict:
    z = q.copy()
    z["net"] = z["gross"] - z["turnover"] * cost_bps / 10000.0
    mean_weights = {a: float(z[f"w_{a}"].mean()) for a in ASSETS}
    z["matched"] = sum(mean_weights[a] * z[f"r_{a}"] for a in ASSETS)
    z["equal_weight"] = sum(SLEEVE * z[f"r_{a}"] for a in ASSETS)

    out = {k: stats(z[k]) for k in ("net", "matched", "equal_weight", "spy")}
    out.update(
        {
            "excess_matched": out["net"]["cagr"] - out["matched"]["cagr"],
            "excess_equal_weight": out["net"]["cagr"] - out["equal_weight"]["cagr"],
            "excess_spy": out["net"]["cagr"] - out["spy"]["cagr"],
            "months": len(z),
            "mean_risky_exposure": float(z["risky_exposure"].mean()),
            "mean_turnover": float(z["turnover"].mean()),
            "mean_asset_weights": mean_weights,
        }
    )

    folds = []
    for j, idx in enumerate(np.array_split(np.arange(len(z)), 5), 1):
        a = z.iloc[idx].copy()
        fw = {asset: float(a[f"w_{asset}"].mean()) for asset in ASSETS}
        matched = sum(fw[asset] * a[f"r_{asset}"] for asset in ASSETS)
        equal_weight = sum(SLEEVE * a[f"r_{asset}"] for asset in ASSETS)
        folds.append(
            {
                "fold": j,
                "matched_excess": cagr(a["net"]) - cagr(matched),
                "equal_weight_excess": cagr(a["net"]) - cagr(equal_weight),
                "spy_excess": cagr(a["net"]) - cagr(a["spy"]),
            }
        )
    out["positive_matched_folds"] = sum(x["matched_excess"] > 0 for x in folds)
    out["positive_equal_weight_folds"] = sum(x["equal_weight_excess"] > 0 for x in folds)
    out["positive_spy_folds"] = sum(x["spy_excess"] > 0 for x in folds)
    out["folds"] = folds
    return out


def main() -> None:
    px = yf.download(
        ASSETS,
        start="2002-01-01",
        auto_adjust=True,
        progress=False,
        threads=False,
    )["Close"].dropna(how="all").astype(float)
    last = pd.Timestamp(px.index.max())
    if last.tzinfo:
        last = last.tz_localize(None)
    cut = last.to_period("M").start_time - pd.Timedelta(days=1)
    px = px.loc[px.index <= cut].dropna()

    sma252 = px.rolling(252, min_periods=252).mean()
    month_close = px.resample("ME").last().dropna()
    month_sma = sma252.resample("ME").last().reindex(month_close.index)
    month_ret = month_close.pct_change(fill_method=None)

    prev_w = {a: 0.0 for a in ASSETS}
    rows = []
    for i, dt in enumerate(month_close.index[:-1]):
        sig_close = month_close.loc[dt]
        sig_sma = month_sma.loc[dt]
        if sig_sma.isna().any():
            continue
        w = {a: (SLEEVE if float(sig_close[a]) > float(sig_sma[a]) else 0.0) for a in ASSETS}
        risky = sum(w.values())
        prev_risky = sum(prev_w.values())
        turnover = 0.5 * (
            sum(abs(w[a] - prev_w[a]) for a in ASSETS)
            + abs((1.0 - risky) - (1.0 - prev_risky))
        )
        nxt = month_close.index[i + 1]
        rr = month_ret.loc[nxt]
        gross = sum(w[a] * float(rr[a]) for a in ASSETS)
        row = {
            "return_month": nxt,
            "gross": gross,
            "turnover": turnover,
            "risky_exposure": risky,
            "spy": float(rr["SPY"]),
        }
        for a in ASSETS:
            row[f"w_{a}"] = w[a]
            row[f"r_{a}"] = float(rr[a])
        rows.append(row)
        prev_w = w

    q = pd.DataFrame(rows).set_index("return_month")
    tests = {
        window: {
            str(cost): evaluate(q.loc[pd.Timestamp(start):], cost)
            for cost in COSTS
        }
        for window, start in WINDOWS.items()
    }

    a = tests["2015"]["50"]
    b = tests["2020"]["50"]
    supported = (
        a["excess_matched"] > 0
        and a["excess_equal_weight"] > 0
        and a["positive_matched_folds"] >= 3
        and b["excess_matched"] > 0
        and b["positive_matched_folds"] >= 3
    )
    decision = (
        "P159_CROSS_ASSET_TIME_SERIES_TREND_SUPPORTED_FOR_INDEPENDENT_VALIDATION"
        if supported
        else "P159_CROSS_ASSET_TIME_SERIES_TREND_NOT_SUPPORTED"
    )

    out = {
        "schema": "research.p159_cross_asset_time_series_trend_r1",
        "parent": "P159",
        "hypothesis": (
            "A diversified set of independent 252-session trend sleeves across SPY, IEF, and GLD, "
            "each allocated one-third only when its completed-month close is above its trailing "
            "252-session SMA and otherwise held in cash, creates durable after-cost excess versus "
            "the same average asset exposures and a static equal-weight cross-asset allocation."
        ),
        "contract": {
            "assets": ASSETS,
            "signal": "completed-month adjusted close above trailing 252-session adjusted-close SMA, independently per asset",
            "allocation": "one-third sleeve per asset when signal true; inactive sleeves remain cash",
            "rebalance": "monthly using only completed-month information",
            "cost_bps": list(COSTS),
            "matched_control": "static per-asset weights equal to evaluated mean realized sleeve weights, residual cash",
            "allocation_control": "static equal-weight SPY/IEF/GLD",
            "opportunity_control": "full SPY",
            "windows": list(WINDOWS),
            "folds": 5,
            "no_asset_lookback_sleeve_threshold_cost_or_window_search": True,
        },
        "source": {
            "provider": "Yahoo Finance via yfinance; research-only",
            "last_complete_month_end": str(cut.date()),
            "panel_sha256": hashlib.sha256(px.reset_index().to_csv(index=False).encode()).hexdigest(),
        },
        "tests": tests,
        "decision": decision,
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p159_cross_asset_time_series_trend_r1.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, allow_nan=False)
    )
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
