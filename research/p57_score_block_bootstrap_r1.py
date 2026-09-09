from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import p57_score_monotonicity_r1 as p57

N_REPS = 2000
BLOCK = 6
SEED = 570064
WINDOWS = {"2015_forward": "2015-01-01", "2020_forward": "2020-01-01"}


def cagr(r):
    r = pd.Series(r, dtype=float).dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1)


def stats(q):
    return {
        "after_cost_excess_cagr": cagr(q.net) - cagr(q.ew),
        "mean_rank_ic": float(q.rank_ic.mean()),
        "selected_minus_nonselected_mean": float(q.selected_minus_nonselected.mean()),
    }


def circular_block(q, rng):
    n = len(q)
    take = []
    while len(take) < n:
        start = int(rng.integers(0, n))
        take.extend((start + j) % n for j in range(BLOCK))
    return q.iloc[take[:n]].reset_index(drop=True)


def main():
    f, close, cutoff = p57.build()
    rng = np.random.default_rng(SEED)
    out = {
        "schema": "research.p57_score_block_bootstrap_r1",
        "parent": "P57",
        "hypothesis": "P57's recent cross-sectional rank information and top-2 economics should remain positive under serial-dependence-preserving resampling if the partially supported score mechanism is persistent rather than a chronology artifact.",
        "scientific_contract": {
            "universe": list(p57.SYMS),
            "factors": ["mom6", "trend200"],
            "top_k": 2,
            "execution_delay_trading_days": p57.DELAY,
            "cost_bps": p57.BP,
            "matched_control": "same-universe equal weight over identical delayed intervals",
            "windows": WINDOWS,
            "bootstrap": "circular moving blocks of complete monthly candidate/control/rank-IC/spread rows",
            "block_months": BLOCK,
            "replications": N_REPS,
            "seed": SEED,
            "no_parameter_tuning": True
        },
        "source": {
            "provider": "Yahoo Finance via yfinance; research-only",
            "panel_sha256": p57.base.source_hash(close),
            "last_complete_month_end": str(cutoff.date())
        },
        "windows": {}
    }
    keys = ["after_cost_excess_cagr", "mean_rank_ic", "selected_minus_nonselected_mean"]
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
                "p95": float(np.quantile(a, 0.95))
            }
        out["windows"][name] = {"months": int(len(q)), "metrics": metrics}
    z = out["windows"]["2020_forward"]["metrics"]
    out["decision"] = (
        "P57_SCORE_MECHANISM_BLOCK_BOOTSTRAP_SUPPORTED"
        if all(z[k]["actual"] > 0 and z[k]["p_nonpositive"] <= 0.10 for k in keys)
        else "P57_SCORE_MECHANISM_BLOCK_BOOTSTRAP_FRAGILE"
    )
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p57_score_block_bootstrap_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(out, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
