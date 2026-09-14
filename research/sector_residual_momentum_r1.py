from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

WORKLOAD_ID = "SECTOR_RESIDUAL_MOMENTUM_R1"
UNIVERSE = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
BENCHMARK = "SPY"
START = "1999-01-01"
TOP_K = 3
BETA_MONTHS = 36
MOMENTUM_SKIP_MONTHS = 1
MOMENTUM_LOOKBACK_MONTHS = 11
SWITCH_COST = 0.001
WINDOWS = ["2005-01-01", "2010-01-01", "2015-01-01", "2020-01-01", "2022-01-01"]


def metrics(r: pd.Series) -> dict:
    x = pd.Series(r, dtype=float).dropna()
    n = len(x)
    if not n:
        return {"months": 0, "cagr": None, "maxdd": None, "sharpe_rf0": None}
    eq = (1 + x).cumprod()
    cagr = float(eq.iloc[-1] ** (12 / n) - 1)
    maxdd = float((eq / eq.cummax() - 1).min())
    vol = float(x.std(ddof=1) * math.sqrt(12)) if n > 1 else 0.0
    sharpe = float(x.mean() * 12 / vol) if vol > 0 else None
    return {"months": int(n), "cagr": cagr, "maxdd": maxdd, "sharpe_rf0": sharpe}


def beta_est(asset: pd.Series, market: pd.Series) -> float:
    z = pd.concat([asset, market], axis=1).dropna()
    if len(z) < BETA_MONTHS:
        return float("nan")
    a = z.iloc[-BETA_MONTHS:, 0].to_numpy(float)
    m = z.iloc[-BETA_MONTHS:, 1].to_numpy(float)
    v = float(np.var(m, ddof=1))
    return float(np.cov(a, m, ddof=1)[0, 1] / v) if v > 1e-15 else float("nan")


raw = yf.download(UNIVERSE + [BENCHMARK], start=START, auto_adjust=True, progress=False, threads=False)
close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
close = close[UNIVERSE + [BENCHMARK]].dropna(how="all")
monthly_close = close.resample("ME").last().dropna(subset=UNIVERSE + [BENCHMARK])
ret = monthly_close.pct_change()
logret = np.log(monthly_close / monthly_close.shift(1))

candidate = []
control = []
spy = []
selection_rows = []
prev_weights = pd.Series(0.0, index=UNIVERSE)

for i in range(BETA_MONTHS + MOMENTUM_LOOKBACK_MONTHS + MOMENTUM_SKIP_MONTHS, len(monthly_close) - 1):
    signal_date = monthly_close.index[i]
    hold_date = monthly_close.index[i + 1]
    market_hist = ret[BENCHMARK].iloc[:i]
    scores = {}
    for ticker in UNIVERSE:
        b = beta_est(ret[ticker].iloc[:i], market_hist)
        if not np.isfinite(b):
            continue
        # Frozen 12-1 style signal: eleven completed months ending one month before signal month.
        asset_mom = float(logret[ticker].iloc[i - 11:i].sum())
        market_mom = float(logret[BENCHMARK].iloc[i - 11:i].sum())
        scores[ticker] = asset_mom - b * market_mom
    if len(scores) != len(UNIVERSE):
        continue
    selected = sorted(scores, key=scores.get, reverse=True)[:TOP_K]
    new_weights = pd.Series(0.0, index=UNIVERSE)
    new_weights.loc[selected] = 1.0 / TOP_K
    turnover = float(0.5 * np.abs(new_weights - prev_weights).sum())
    if prev_weights.sum() == 0:
        turnover = 1.0
    next_ret = ret.loc[hold_date, UNIVERSE]
    gross = float((new_weights * next_ret).sum())
    net = gross - SWITCH_COST * turnover
    ew = float(next_ret.mean())
    candidate.append((hold_date, net))
    control.append((hold_date, ew))
    spy.append((hold_date, float(ret.loc[hold_date, BENCHMARK])))
    selection_rows.append({"signal_date": signal_date.date().isoformat(), "hold_date": hold_date.date().isoformat(), "selected": selected, "turnover": turnover})
    prev_weights = new_weights

candidate = pd.Series(dict(candidate), dtype=float).sort_index()
control = pd.Series(dict(control), dtype=float).sort_index()
spy = pd.Series(dict(spy), dtype=float).sort_index()
common = pd.concat([candidate.rename("candidate"), control.rename("control"), spy.rename("spy")], axis=1).dropna()

windows = {}
for start in WINDOWS:
    q = common.loc[common.index >= pd.Timestamp(start)]
    cm = metrics(q.candidate)
    bm = metrics(q.control)
    sm = metrics(q.spy)
    windows[start] = {
        "candidate": cm,
        "equal_weight_control": bm,
        "spy": sm,
        "matched_excess_cagr": None if cm["cagr"] is None else cm["cagr"] - bm["cagr"],
        "vs_spy_cagr": None if cm["cagr"] is None else cm["cagr"] - sm["cagr"],
    }

folds = []
for fold, ix in enumerate(np.array_split(np.arange(len(common)), 5), 1):
    q = common.iloc[ix]
    cm = metrics(q.candidate)
    bm = metrics(q.control)
    folds.append({"fold": fold, "months": len(q), "matched_excess_cagr": cm["cagr"] - bm["cagr"]})

positive_windows = sum(v["matched_excess_cagr"] > 0 for v in windows.values())
positive_folds = sum(v["matched_excess_cagr"] > 0 for v in folds)
recent_positive = windows["2022-01-01"]["matched_excess_cagr"] > 0
full = windows["2005-01-01"]
drawdown_ok = full["candidate"]["maxdd"] >= full["equal_weight_control"]["maxdd"] - 0.10
gate = bool(positive_windows >= 4 and positive_folds >= 4 and recent_positive and drawdown_ok)

out = {
    "schema": "research.sector_residual_momentum_r1",
    "workload_id": WORKLOAD_ID,
    "claim": "A fixed 12-1 beta-residual momentum ranking across nine long-lived US sector ETFs produces durable after-cost excess over an equal-weight sector control.",
    "decision": "SECTOR_RESIDUAL_MOMENTUM_SURVIVES_R1" if gate else "SECTOR_RESIDUAL_MOMENTUM_REJECT_R1",
    "contract": {
        "universe": UNIVERSE,
        "universe_rule": "nine original Select Sector SPDR funds; fixed before execution",
        "score": "11-month log return ending one month before signal minus 36-month trailing beta times SPY 11-month log return",
        "top_k": TOP_K,
        "holding_period": "one month, monthly rebalance",
        "candidate_cost": "10 bps times half-L1 target-weight turnover; no cost search",
        "matched_control": "same-month equal-weight return of all nine sector ETFs",
        "broad_control": "SPY",
        "gate": ">=4/5 expanding windows positive matched excess including 2022+, >=4/5 chronology folds positive, full-window max drawdown no more than 10pp worse than equal-weight control",
        "no_universe_lookback_topk_threshold_window_or_cost_search": True,
    },
    "period": {"first_hold": common.index.min().date().isoformat(), "last_hold": common.index.max().date().isoformat(), "months": int(len(common))},
    "windows": windows,
    "chronology_folds": folds,
    "positive_windows": positive_windows,
    "positive_folds": positive_folds,
    "recent_positive": recent_positive,
    "drawdown_gate": drawdown_ok,
    "latest_selection": selection_rows[-1] if selection_rows else None,
    "limitations": ["ETF-history representation, not PIT constituent selection", "Yahoo adjusted prices are research-only", "equal-weight control does not deduct its small monthly rebalance drift cost"],
    "boundaries": {"allocation_authority": False, "portfolio_ranking": False, "runtime": False, "broker": False, "live_trading": False},
}
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/sector_residual_momentum_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
print(json.dumps(out, indent=2, sort_keys=True))
