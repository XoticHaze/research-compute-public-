from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import p104_p111_crossasset_model_family_tournament_r1 as base

REPRESENTATIONS = {
    "base": ("VTI", "VEA", "IEF", "IAU", "GSG"),
    "proxy": ("SPY", "EFA", "TLT", "GLD", "DBC"),
    "industry": ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT"),
}


def folds(a: pd.Series, b: pd.Series, n: int = 3) -> int:
    wins = 0
    for idx in np.array_split(np.arange(len(a)), n):
        if len(idx) and base.metrics(a.iloc[idx])["cagr"] > base.metrics(b.iloc[idx])["cagr"]:
            wins += 1
    return wins


def eval_window(f: pd.DataFrame, start: str, bps: int) -> dict:
    g = f.loc[f.index >= pd.Timestamp(start)].copy()
    corr = g.p109_gross - g.p109_turn * bps / 10000
    dual = g.p105_gross - g.p105_turn * bps / 10000
    ew = g.equal_weight
    inc = corr - dual
    keep = inc.sort_values(ascending=False).index[min(5, len(inc)):]
    cm, dm, em = base.metrics(corr), base.metrics(dual), base.metrics(ew)
    return {
        "window": {"start": str(g.index.min().date()), "end": str(g.index.max().date()), "months": len(g)},
        "correlation_penalty": cm,
        "dual_horizon_momentum": dm,
        "equal_weight": em,
        "incremental_cagr_vs_dual_horizon": cm["cagr"] - dm["cagr"],
        "excess_cagr_vs_equal_weight": cm["cagr"] - em["cagr"],
        "positive_chronological_folds_vs_dual_horizon": folds(corr, dual),
        "five_strongest_incremental_months_removed_cagr_vs_dual_horizon": base.metrics(corr.loc[keep])["cagr"] - base.metrics(dual.loc[keep])["cagr"],
        "correlation_penalty_annual_turnover": float(g.p109_turn.mean() * 12),
        "dual_horizon_annual_turnover": float(g.p105_turn.mean() * 12),
    }


def main() -> None:
    out = {
        "schema": "research.p131_correlation_penalty_incremental_mechanism_r1",
        "parent_ids": ["P109", "P117", "P125", "P130", "P131"],
        "contract": {
            "mechanism": "fixed 6m momentum minus recent peer-correlation penalty top2",
            "reference": "fixed dual-horizon 6m/12m momentum top2",
            "representations": {k: list(v) for k, v in REPRESENTATIONS.items()},
            "holdouts": ["2018-01-31", "2022-01-31"],
            "costs_bps": [25, 50],
            "chronological_folds": 3,
            "concentration_test": "remove five strongest correlation-penalty-minus-dual-horizon months",
            "no_parameter_horizon_topk_or_weight_tuning": True,
        },
        "results": {},
    }
    for name, assets in REPRESENTATIONS.items():
        base.ASSETS = assets
        base.ALL = (*assets, "BIL", "SPY", "QQQ")
        f, meta = base.build_frame()
        rec = {"source": meta, "holdouts": {}}
        for start in ("2018-01-31", "2022-01-31"):
            rec["holdouts"][start] = {str(bps): eval_window(f, start, bps) for bps in (25, 50)}
        out["results"][name] = rec
    cells = [out["results"][rep][start][str(bps)]["incremental_cagr_vs_dual_horizon"] for rep in REPRESENTATIONS for start in ("2018-01-31", "2022-01-31") for bps in (25, 50)]
    folds_ok = [out["results"][rep][start]["25"]["positive_chronological_folds_vs_dual_horizon"] >= 2 for rep in REPRESENTATIONS for start in ("2018-01-31", "2022-01-31")]
    trims = [out["results"][rep][start]["25"]["five_strongest_incremental_months_removed_cagr_vs_dual_horizon"] for rep in REPRESENTATIONS for start in ("2018-01-31", "2022-01-31")]
    if all(x > 0 for x in cells) and all(folds_ok) and all(x > 0 for x in trims):
        decision = "CORRELATION_PENALTY_INCREMENTAL_MECHANISM_BROADLY_SUPPORTED"
    elif sum(x > 0 for x in cells) >= 8 and sum(folds_ok) >= 4:
        decision = "CORRELATION_PENALTY_INCREMENTAL_SUPPORT_MIXED_OR_CONCENTRATED"
    else:
        decision = "CORRELATION_PENALTY_NOT_SEPARABLE_FROM_GENERIC_MOMENTUM"
    out["decision"] = decision
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p131_correlation_penalty_incremental_mechanism_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {rep: {start: {"25_inc": out["results"][rep][start]["25"]["incremental_cagr_vs_dual_horizon"], "25_folds": out["results"][rep][start]["25"]["positive_chronological_folds_vs_dual_horizon"], "25_trim": out["results"][rep][start]["25"]["five_strongest_incremental_months_removed_cagr_vs_dual_horizon"], "50_inc": out["results"][rep][start]["50"]["incremental_cagr_vs_dual_horizon"]} for start in ("2018-01-31", "2022-01-31")} for rep in REPRESENTATIONS}
    print(json.dumps({"decision": decision, "results": compact}, sort_keys=True))


if __name__ == "__main__":
    main()
