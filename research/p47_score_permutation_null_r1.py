from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import p47_temporal_factor_discriminators_r1 as p47
import fixed_multifactor_cross_sectional_r1 as base

BP = 50
WINDOWS = {"2015_forward": "2015-01-01", "2020_forward": "2020-01-01"}
N_REPS = 2000
SEED = 470047


def cagr(r):
    r = pd.Series(r, dtype=float).dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1) if len(r) else float("nan")


def monthly_panel():
    close = base.load(p47.SYMBOLS)
    panel, monthly = p47.panel(close, p47.FACTORS)
    rows = []
    for month in sorted(panel.month.unique()):
        ranked = panel[panel.month == month].sort_values(["score", "symbol"], ascending=[False, True])
        loc = monthly.index.get_loc(month)
        if len(ranked) != len(p47.SYMBOLS) or not isinstance(loc, (int, np.integer)) or loc + 1 >= len(monthly):
            continue
        nxt = monthly.index[loc + 1]
        ret = monthly.loc[nxt, list(p47.SYMBOLS)] / monthly.loc[month, list(p47.SYMBOLS)] - 1
        if ret.isna().any():
            continue
        rows.append(
            {
                "date": nxt,
                "symbols": list(ranked.symbol),
                "scores": list(ranked.score.astype(float)),
                "returns": {s: float(ret[s]) for s in p47.SYMBOLS},
            }
        )
    return rows, close


def path_returns(rows, permute: bool, rng: np.random.Generator | None = None):
    prev = {s: 0.0 for s in p47.SYMBOLS}
    candidate, ew, rank_ics, spreads, dates = [], [], [], [], []
    for row in rows:
        symbols = list(row["symbols"])
        scores = np.asarray(row["scores"], dtype=float)
        if permute:
            scores = rng.permutation(scores)
        ranked = sorted(zip(symbols, scores), key=lambda x: (-x[1], x[0]))
        chosen = [s for s, _ in ranked[:3]]
        rest = [s for s in p47.SYMBOLS if s not in chosen]
        r = pd.Series(row["returns"], dtype=float)
        score = pd.Series({s: sc for s, sc in zip(symbols, scores)}, dtype=float)
        rank_ics.append(float(score.rank().corr(r.rank())))
        selected = float(r[chosen].mean())
        spreads.append(selected - float(r[rest].mean()))
        w = {s: (1 / 3 if s in chosen else 0.0) for s in p47.SYMBOLS}
        turnover = 0.5 * sum(abs(w[s] - prev[s]) for s in p47.SYMBOLS)
        prev = w
        candidate.append(selected - turnover * BP / 10000)
        ew.append(float(r.mean()))
        dates.append(pd.Timestamp(row["date"]))
    return pd.DataFrame({"candidate": candidate, "ew": ew, "rank_ic": rank_ics, "spread": spreads}, index=dates)


def folds(q):
    out = []
    for i, ids in enumerate(np.array_split(np.arange(len(q)), 5), 1):
        z = q.iloc[ids]
        out.append(
            {
                "fold": i,
                "excess_cagr": cagr(z.candidate) - cagr(z.ew),
                "mean_rank_ic": float(z.rank_ic.mean()),
                "spread_mean": float(z.spread.mean()),
            }
        )
    return out


def summarize(q):
    fs = folds(q)
    return {
        "months": int(len(q)),
        "after_cost_excess_cagr": cagr(q.candidate) - cagr(q.ew),
        "mean_rank_ic": float(q.rank_ic.mean()),
        "spread_mean": float(q.spread.mean()),
        "positive_excess_folds": int(sum(x["excess_cagr"] > 0 for x in fs)),
        "positive_ic_folds": int(sum(x["mean_rank_ic"] > 0 for x in fs)),
        "positive_spread_folds": int(sum(x["spread_mean"] > 0 for x in fs)),
        "folds": fs,
    }


def main():
    rows, close = monthly_panel()
    actual = path_returns(rows, permute=False)
    rng = np.random.default_rng(SEED)
    null = {name: [] for name in WINDOWS}
    null_ic = {name: [] for name in WINDOWS}
    null_spread = {name: [] for name in WINDOWS}
    for _ in range(N_REPS):
        q = path_returns(rows, permute=True, rng=rng)
        for name, start in WINDOWS.items():
            z = q.loc[pd.Timestamp(start):]
            null[name].append(cagr(z.candidate) - cagr(z.ew))
            null_ic[name].append(float(z.rank_ic.mean()))
            null_spread[name].append(float(z.spread.mean()))

    out = {
        "schema": "research.p47_score_permutation_null_r1",
        "parent": "P47",
        "hypothesis": "If P47's frozen score mapping contains genuine cross-sectional information, the correctly mapped score should outperform month-by-month cross-sectional score permutations under the same universe, top-3 allocation, 50-bps costs, and windows.",
        "scientific_contract": {
            "universe": "industry",
            "factors": list(p47.FACTORS),
            "top_k": 3,
            "cost_bps": BP,
            "matched_control": "same-universe equal weight",
            "null": "independently permute the frozen monthly cross-sectional score vector across symbols",
            "replications": N_REPS,
            "seed": SEED,
            "windows": WINDOWS,
            "chronological_folds": 5,
            "no_parameter_tuning": True,
        },
        "windows": {},
        "source": {"provider": "Yahoo Finance via yfinance; research-only", "panel_sha256": base.source_hash(close)},
    }

    for name, start in WINDOWS.items():
        a = summarize(actual.loc[pd.Timestamp(start):])
        ex = np.asarray(null[name], dtype=float)
        ic = np.asarray(null_ic[name], dtype=float)
        sp = np.asarray(null_spread[name], dtype=float)
        out["windows"][name] = {
            "actual": a,
            "null": {
                "excess_cagr_mean": float(ex.mean()),
                "excess_cagr_p05": float(np.quantile(ex, 0.05)),
                "excess_cagr_p95": float(np.quantile(ex, 0.95)),
                "p_null_ge_actual_excess": float(np.mean(ex >= a["after_cost_excess_cagr"])),
                "actual_excess_percentile": float(np.mean(ex < a["after_cost_excess_cagr"])),
                "rank_ic_mean": float(ic.mean()),
                "p_null_ge_actual_ic": float(np.mean(ic >= a["mean_rank_ic"])),
                "spread_mean": float(sp.mean()),
                "p_null_ge_actual_spread": float(np.mean(sp >= a["spread_mean"])),
            },
        }

    z = out["windows"]["2020_forward"]
    actual_z, null_z = z["actual"], z["null"]
    out["decision"] = (
        "P47_SCORE_MAPPING_SUPPORTED_AGAINST_PERMUTATION_NULL"
        if actual_z["after_cost_excess_cagr"] > 0
        and actual_z["mean_rank_ic"] > 0
        and actual_z["spread_mean"] > 0
        and null_z["p_null_ge_actual_excess"] <= 0.05
        and null_z["p_null_ge_actual_ic"] <= 0.05
        and null_z["p_null_ge_actual_spread"] <= 0.05
        else "P47_SCORE_MAPPING_NOT_DISTINGUISHED_FROM_PERMUTATION_NULL"
    )

    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p47_score_permutation_null_r1.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, allow_nan=False)
    )
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
