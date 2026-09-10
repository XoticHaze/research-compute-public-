import hashlib, json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
ALL = SECTORS + ["SPY"]
COSTS = [10, 25, 50]
WINDOWS = {"2010": "2010-01-01", "2015": "2015-01-01", "2020": "2020-01-01"}
PRIMARY_COST = 25
TOP_K = 3


def cagr(r):
    r = pd.Series(r).dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1)


def maxdd(r):
    e = (1 + pd.Series(r).fillna(0)).cumprod()
    return float((e / e.cummax() - 1).min())


def sharpe(r):
    r = pd.Series(r).dropna()
    s = r.std(ddof=1)
    return float(np.sqrt(12) * r.mean() / s) if s > 0 else float("nan")


def metrics(r):
    return {"cagr": cagr(r), "maxdd": maxdd(r), "sharpe": sharpe(r)}


def evaluate(z, cost_bps):
    cand = z.gross - z.turnover * cost_bps / 10000
    eq = z.equal_weight
    spy = z.SPY_ret
    return {
        "candidate": metrics(cand),
        "sector_equal_weight": metrics(eq),
        "spy": metrics(spy),
        "excess_equal_weight": cagr(cand) - cagr(eq),
        "excess_spy": cagr(cand) - cagr(spy),
        "mean_turnover": float(z.turnover.mean()),
        "months": int(len(z)),
    }


def folds(z, cost_bps):
    out = []
    for i, idx in enumerate(np.array_split(np.arange(len(z)), 5), 1):
        x = evaluate(z.iloc[idx], cost_bps)
        out.append({
            "fold": i,
            "equal_weight_excess": x["excess_equal_weight"],
            "spy_excess": x["excess_spy"],
        })
    return out


raw = yf.download(
    ALL,
    start="2000-01-01",
    end="2026-09-01",
    auto_adjust=True,
    progress=False,
    group_by="column",
)
close = raw["Close"][ALL] if isinstance(raw.columns, pd.MultiIndex) else raw[ALL]
close = close.dropna(how="all").ffill().dropna()
monthly = close.resample("ME").last()
ret = monthly.pct_change()
# Standard cross-sectional 12-1 momentum: at completed month t, rank return from t-12 to t-1,
# deliberately excluding month t; hold the fixed top-3 equally during month t+1.
mom_12_1 = monthly[SECTORS].shift(1) / monthly[SECTORS].shift(12) - 1
rows = []
prev = None
for i in range(12, len(monthly.index) - 1):
    dt = monthly.index[i]
    nxt = monthly.index[i + 1]
    ranks = mom_12_1.loc[dt].dropna().sort_values(ascending=False)
    if len(ranks) < TOP_K:
        continue
    chosen = list(ranks.index[:TOP_K])
    w = pd.Series(0.0, index=SECTORS)
    w.loc[chosen] = 1.0 / TOP_K
    r = ret.loc[nxt]
    gross = float((w * r[SECTORS]).sum())
    eq = float(r[SECTORS].mean())
    turnover = 0.0 if prev is None else float(np.abs(w.values - prev).sum() / 2)
    rows.append({
        "date": nxt,
        "gross": gross,
        "turnover": turnover,
        "equal_weight": eq,
        "SPY_ret": float(r.SPY),
        "selected": ",".join(chosen),
    })
    prev = w.values.copy()

z = pd.DataFrame(rows).set_index("date")
panel_sha = hashlib.sha256(close.to_csv().encode()).hexdigest()
out = {
    "schema": "research.p183_sector_xsec_momentum_r1",
    "parent": "P183",
    "hypothesis": "A fixed top-3 cross-sectional 12-1 momentum selector across the nine long-history US sector SPDRs creates durable after-cost excess versus static equal-weight sector exposure and SPY.",
    "contract": {
        "universe": SECTORS,
        "signal": "completed-month 12-1 total return; rank sectors at month t using prices t-12 to t-1; hold top 3 equally in month t+1",
        "top_k": TOP_K,
        "cost_bps": COSTS,
        "primary_cost_bps": PRIMARY_COST,
        "windows": WINDOWS,
        "folds": 5,
        "matched_control": "static equal-weight across the same nine sector ETFs",
        "opportunity_control": "SPY",
        "predeclared_gate": "2015+ at 25 bps: positive excess vs sector equal-weight and SPY, >=3/5 positive equal-weight folds, and max drawdown no worse than sector equal-weight",
        "no_search": True,
    },
    "source": {
        "provider": "Yahoo Finance via yfinance; research-only representation",
        "last_complete_month_end": str(monthly.index[-1].date()),
        "panel_sha256": panel_sha,
    },
    "tests": {},
}
for cost in COSTS:
    out["tests"][str(cost)] = {}
    for name, start in WINDOWS.items():
        q = z.loc[pd.Timestamp(start):]
        x = evaluate(q, cost)
        fs = folds(q, cost)
        x["folds"] = fs
        x["positive_equal_weight_folds"] = sum(a["equal_weight_excess"] > 0 for a in fs)
        x["positive_spy_folds"] = sum(a["spy_excess"] > 0 for a in fs)
        out["tests"][str(cost)][name] = x
p = out["tests"][str(PRIMARY_COST)]["2015"]
out["decision"] = (
    "P183_SECTOR_XSEC_MOMENTUM_SURVIVOR"
    if p["excess_equal_weight"] > 0
    and p["excess_spy"] > 0
    and p["positive_equal_weight_folds"] >= 3
    and p["candidate"]["maxdd"] >= p["sector_equal_weight"]["maxdd"]
    else "P183_SECTOR_XSEC_MOMENTUM_REJECT"
)
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/p183_sector_xsec_momentum_r1.json").write_text(json.dumps(out, sort_keys=True, indent=2))
print(json.dumps(out, sort_keys=True))
