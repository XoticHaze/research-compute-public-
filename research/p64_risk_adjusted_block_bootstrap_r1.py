from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import p64_component_contribution_r1 as p64

N_REPS = 2000
BLOCK = 6
SEED = 640064
WINDOWS = {"2020_forward": "2020-01-01", "2022_forward": "2022-01-01"}


def cagr(r):
    r = pd.Series(r, dtype=float).dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1)


def sharpe(r):
    r = pd.Series(r, dtype=float).dropna()
    s = r.std(ddof=1)
    return float(r.mean() / s * np.sqrt(12)) if s > 0 else float("nan")


def mdd(r):
    r = pd.Series(r, dtype=float).dropna()
    e = (1 + r).cumprod()
    return float((e / e.cummax() - 1).min())


def calmar(r):
    dd = mdd(r)
    return float(cagr(r) / abs(dd)) if dd < 0 else float("nan")


def deltas(q):
    return {
        "cagr_vs_matched": cagr(q.candidate) - cagr(q.matched),
        "cagr_vs_qqq": cagr(q.candidate) - cagr(q.qqq),
        "sharpe_vs_matched": sharpe(q.candidate) - sharpe(q.matched),
        "sharpe_vs_qqq": sharpe(q.candidate) - sharpe(q.qqq),
        "calmar_vs_matched": calmar(q.candidate) - calmar(q.matched),
        "calmar_vs_qqq": calmar(q.candidate) - calmar(q.qqq),
    }


def circular_block_sample(q, rng):
    n = len(q)
    take = []
    while len(take) < n:
        start = int(rng.integers(0, n))
        take.extend((start + j) % n for j in range(BLOCK))
    return q.iloc[take[:n]].reset_index(drop=True)


def main():
    f, cc, ic, cutoff = p64.build()
    frame = pd.DataFrame(
        {
            "candidate": 0.5 * f.cross + 0.5 * f.industry,
            "matched": 0.5 * f.cross_ctrl + 0.5 * f.industry_ctrl,
            "qqq": f.qqq,
        }
    ).dropna()
    rng = np.random.default_rng(SEED)
    out = {
        "schema": "research.p64_risk_adjusted_block_bootstrap_r1",
        "parent": "P64",
        "hypothesis": "P64's later-period risk-adjusted advantage should remain positive under paired serial-dependence-preserving resampling if it is more than a fragile point estimate.",
        "scientific_contract": {
            "component_cost_bps": 50,
            "sleeve_weights": [0.5, 0.5],
            "controls": ["fixed matched blend", "QQQ"],
            "windows": WINDOWS,
            "bootstrap": "paired circular moving blocks of candidate/matched/QQQ monthly returns",
            "block_months": BLOCK,
            "replications": N_REPS,
            "seed": SEED,
            "metrics": ["CAGR delta", "Sharpe rf0 delta", "Calmar delta"],
            "no_parameter_gate_or_weight_tuning": True,
        },
        "source": {
            "provider": "Yahoo Finance via yfinance; research-only",
            "cross_panel_sha256": p64.base.source_hash(cc),
            "industry_panel_sha256": p64.base.source_hash(ic),
            "last_complete_month_end": str(cutoff.date()),
        },
        "windows": {},
    }
    keys = ["cagr_vs_matched", "cagr_vs_qqq", "sharpe_vs_matched", "sharpe_vs_qqq", "calmar_vs_matched", "calmar_vs_qqq"]
    for name, start in WINDOWS.items():
        q = frame.loc[pd.Timestamp(start):].copy()
        actual = deltas(q)
        boot = {k: [] for k in keys}
        for _ in range(N_REPS):
            d = deltas(circular_block_sample(q, rng))
            for k in keys:
                boot[k].append(d[k])
        stats = {}
        for k in keys:
            a = np.asarray(boot[k], dtype=float)
            if not np.isfinite(a).all():
                raise RuntimeError(f"non-finite bootstrap statistic: {name} {k}")
            stats[k] = {
                "actual": actual[k],
                "p_nonpositive": float(np.mean(a <= 0)),
                "p05": float(np.quantile(a, 0.05)),
                "median": float(np.quantile(a, 0.50)),
                "p95": float(np.quantile(a, 0.95)),
            }
        out["windows"][name] = {"months": int(len(q)), "metrics": stats}

    z = out["windows"]["2022_forward"]["metrics"]
    out["decision"] = (
        "P64_RECENT_RISK_ADJUSTED_ADVANTAGE_BOOTSTRAP_SUPPORTED"
        if z["sharpe_vs_qqq"]["actual"] > 0
        and z["calmar_vs_qqq"]["actual"] > 0
        and z["cagr_vs_matched"]["actual"] > 0
        and z["sharpe_vs_qqq"]["p_nonpositive"] <= 0.10
        and z["calmar_vs_qqq"]["p_nonpositive"] <= 0.10
        and z["cagr_vs_matched"]["p_nonpositive"] <= 0.10
        else "P64_RECENT_RISK_ADJUSTED_ADVANTAGE_BOOTSTRAP_FRAGILE"
    )
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p64_risk_adjusted_block_bootstrap_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(out, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
