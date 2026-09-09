from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import p47_temporal_factor_discriminators_r1 as p47
import fixed_multifactor_cross_sectional_r1 as base

N_REPS = 2000
BLOCK = 6
SEED = 470064
BP = 50
WINDOWS = {"2015_forward": "2015-01-01", "2020_forward": "2020-01-01"}


def cagr(r):
    r = pd.Series(r, dtype=float).dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1)


def monthly_rows():
    close = base.load(p47.SYMBOLS)
    panel, monthly = p47.panel(close, p47.FACTORS)
    rows = []
    prev = {s: 0.0 for s in p47.SYMBOLS}
    for month in sorted(panel.month.unique()):
        ranked = panel[panel.month == month].sort_values(["score", "symbol"], ascending=[False, True])
        loc = monthly.index.get_loc(month)
        if len(ranked) != len(p47.SYMBOLS) or not isinstance(loc, (int, np.integer)) or loc + 1 >= len(monthly):
            continue
        nxt = monthly.index[loc + 1]
        ret = monthly.loc[nxt, list(p47.SYMBOLS)] / monthly.loc[month, list(p47.SYMBOLS)] - 1
        if ret.isna().any():
            continue
        chosen = list(ranked.symbol.iloc[:3])
        rest = [s for s in p47.SYMBOLS if s not in chosen]
        w = {s: (1 / 3 if s in chosen else 0.0) for s in p47.SYMBOLS}
        turnover = 0.5 * sum(abs(w[s] - prev[s]) for s in p47.SYMBOLS)
        prev = w
        score = ranked.set_index("symbol").score.astype(float)
        rr = ret.astype(float)
        rows.append(
            {
                "date": pd.Timestamp(nxt),
                "candidate": float(rr[chosen].mean()) - turnover * BP / 10000,
                "ew": float(rr.mean()),
                "rank_ic": float(score.rank().corr(rr.rank())),
                "spread": float(rr[chosen].mean() - rr[rest].mean()),
            }
        )
    return pd.DataFrame(rows).set_index("date"), close


def stats(q):
    return {
        "after_cost_excess_cagr": cagr(q.candidate) - cagr(q.ew),
        "mean_rank_ic": float(q.rank_ic.mean()),
        "spread_mean": float(q.spread.mean()),
    }


def circular_block(q, rng):
    n = len(q)
    take = []
    while len(take) < n:
        start = int(rng.integers(0, n))
        take.extend((start + j) % n for j in range(BLOCK))
    return q.iloc[take[:n]].reset_index(drop=True)


def main():
    f, close = monthly_rows()
    rng = np.random.default_rng(SEED)
    out = {
        "schema": "research.p47_score_block_bootstrap_r1",
        "parent": "P47",
        "hypothesis": "P47's direct score mechanism statistics should remain positive under paired serial-dependence-preserving resampling if the observed rank/spread/economic evidence is persistent rather than a fragile chronology artifact.",
        "scientific_contract": {
            "factors": list(p47.FACTORS),
            "top_k": 3,
            "cost_bps": BP,
            "matched_control": "same-universe equal weight",
            "windows": WINDOWS,
            "bootstrap": "circular moving blocks of complete monthly candidate/control/rank-IC/spread rows",
            "block_months": BLOCK,
            "replications": N_REPS,
            "seed": SEED,
            "no_parameter_tuning": True,
        },
        "source": {"provider": "Yahoo Finance via yfinance; research-only", "panel_sha256": base.source_hash(close)},
        "windows": {},
    }
    keys = ["after_cost_excess_cagr", "mean_rank_ic", "spread_mean"]
    for name, start in WINDOWS.items():
        q = f.loc[pd.Timestamp(start):].copy()
        actual = stats(q)
        boot = {k: [] for k in keys}
        for _ in range(N_REPS):
            b = stats(circular_block(q, rng))
            for k in keys:
                boot[k].append(b[k])
        metrics = {}
        for k in keys:
            a = np.asarray(boot[k], dtype=float)
            if not np.isfinite(a).all():
                raise RuntimeError(f"non-finite bootstrap statistic: {name} {k}")
            metrics[k] = {
                "actual": actual[k],
                "p_nonpositive": float(np.mean(a <= 0)),
                "p05": float(np.quantile(a, 0.05)),
                "median": float(np.quantile(a, 0.50)),
                "p95": float(np.quantile(a, 0.95)),
            }
        out["windows"][name] = {"months": int(len(q)), "metrics": metrics}
    z = out["windows"]["2020_forward"]["metrics"]
    out["decision"] = (
        "P47_DIRECT_SCORE_MECHANISM_BLOCK_BOOTSTRAP_SUPPORTED"
        if all(z[k]["actual"] > 0 and z[k]["p_nonpositive"] <= 0.10 for k in keys)
        else "P47_DIRECT_SCORE_MECHANISM_BLOCK_BOOTSTRAP_FRAGILE"
    )
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p47_score_block_bootstrap_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(out, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
