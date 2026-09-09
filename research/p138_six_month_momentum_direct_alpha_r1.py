from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import p137_p105_dual_horizon_incremental_mechanism_r1 as p137
import p104_p111_crossasset_model_family_tournament_r1 as base


def folds(a: pd.Series, b: pd.Series, n: int = 3) -> int:
    return sum(base.metrics(a.iloc[idx])["cagr"] > base.metrics(b.iloc[idx])["cagr"] for idx in np.array_split(np.arange(len(a)), n) if len(idx))


def evaluate(f: pd.DataFrame, start: str, bps: int) -> dict:
    g = f if start == "full" else f.loc[f.index >= pd.Timestamp(start)]
    m6 = g.m6_gross - g.m6_turn * bps / 10000
    m12 = g.m12_gross - g.m12_turn * bps / 10000
    ew = g.equal_weight
    inc = m6 - ew
    keep = inc.sort_values(ascending=False).index[min(5, len(inc)):]
    mm, em = base.metrics(m6), base.metrics(ew)
    return {
        "window": {"start": str(g.index.min().date()), "end": str(g.index.max().date()), "months": len(g)},
        "six_month": mm,
        "equal_weight": em,
        "twelve_month": base.metrics(m12),
        "spy": base.metrics(g.spy),
        "qqq": base.metrics(g.qqq),
        "excess_cagr_vs_equal_weight": mm["cagr"] - em["cagr"],
        "excess_cagr_vs_twelve_month": mm["cagr"] - base.metrics(m12)["cagr"],
        "excess_cagr_vs_spy": mm["cagr"] - base.metrics(g.spy)["cagr"],
        "excess_cagr_vs_qqq": mm["cagr"] - base.metrics(g.qqq)["cagr"],
        "positive_folds_vs_equal_weight": folds(m6, ew),
        "five_strongest_m6_minus_ew_months_removed_cagr": base.metrics(m6.loc[keep])["cagr"] - base.metrics(ew.loc[keep])["cagr"],
        "annual_turnover": float(g.m6_turn.mean() * 12),
    }


def main() -> None:
    out = {"schema": "research.p138_six_month_momentum_direct_alpha_r1", "parent_ids": ["P138"], "contract": {"mechanism": "fixed six-month cross-sectional momentum top2", "representations": {k:list(v) for k,v in p137.REPRESENTATIONS.items()}, "windows": ["full","2018-01-31","2022-01-31"], "costs_bps": [25,50], "matched_control": "same-universe equal weight", "opportunity_cost": ["fixed 12m-only top2","SPY","QQQ"], "chronological_folds": 3, "concentration_test": "remove five strongest six-month-minus-equal-weight months", "no_parameter_topk_horizon_or_threshold_tuning": True}, "results": {}}
    for rep, assets in p137.REPRESENTATIONS.items():
        f, meta = p137.build_rep(assets)
        out["results"][rep] = {"source": meta}
        for start in ("full","2018-01-31","2022-01-31"):
            out["results"][rep][start] = {str(bps): evaluate(f,start,bps) for bps in (25,50)}
    late = [(r,s) for r in p137.REPRESENTATIONS for s in ("2018-01-31","2022-01-31")]
    cells = [out["results"][r][s][str(b)]["excess_cagr_vs_equal_weight"] > 0 for r,s in late for b in (25,50)]
    folds_ok = [out["results"][r][s]["25"]["positive_folds_vs_equal_weight"] >= 2 for r,s in late]
    trims = [out["results"][r][s]["25"]["five_strongest_m6_minus_ew_months_removed_cagr"] > 0 for r,s in late]
    if all(cells) and all(folds_ok) and all(trims):
        decision = "SIX_MONTH_MOMENTUM_BROAD_DURABLE_ALPHA_SUPPORTED"
    elif sum(cells) >= 8 and sum(folds_ok) >= 4:
        decision = "SIX_MONTH_MOMENTUM_ALPHA_MIXED_OR_CONCENTRATED"
    else:
        decision = "SIX_MONTH_MOMENTUM_NOT_BROADLY_SUPPORTED"
    out["decision"] = decision
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p138_six_month_momentum_direct_alpha_r1.json").write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False))
    compact={r:{s:{"25_ew":out["results"][r][s]["25"]["excess_cagr_vs_equal_weight"],"25_spy":out["results"][r][s]["25"]["excess_cagr_vs_spy"],"25_qqq":out["results"][r][s]["25"]["excess_cagr_vs_qqq"],"25_folds":out["results"][r][s]["25"]["positive_folds_vs_equal_weight"],"25_trim":out["results"][r][s]["25"]["five_strongest_m6_minus_ew_months_removed_cagr"],"50_ew":out["results"][r][s]["50"]["excess_cagr_vs_equal_weight"]} for s in ("full","2018-01-31","2022-01-31")} for r in p137.REPRESENTATIONS}
    print(json.dumps({"decision":decision,"results":compact},sort_keys=True))

if __name__ == "__main__":
    main()
