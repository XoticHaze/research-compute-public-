from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import p104_p111_crossasset_model_family_tournament_r1 as base

REPRESENTATIONS = {
    "base": ("VTI", "VEA", "IEF", "IAU", "GSG"),
    "proxy": ("SPY", "EFA", "TLT", "GLD", "DBC"),
    "industry": ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT"),
}


def cagr(r: pd.Series) -> float:
    return base.metrics(r)["cagr"]


def net(gross: pd.Series, turn: pd.Series, bps: float) -> pd.Series:
    return gross - turn * bps / 10000.0


def break_even_vs_static(gross: pd.Series, turn: pd.Series, static: pd.Series, max_bps: float = 500.0) -> float | None:
    target = cagr(static)
    if cagr(net(gross, turn, 0.0)) <= target:
        return 0.0
    if cagr(net(gross, turn, max_bps)) > target:
        return None
    lo, hi = 0.0, max_bps
    for _ in range(40):
        mid = (lo + hi) / 2
        if cagr(net(gross, turn, mid)) > target:
            lo = mid
        else:
            hi = mid
    return hi


def break_even_vs_p105(g109: pd.Series, t109: pd.Series, g105: pd.Series, t105: pd.Series, max_bps: float = 500.0) -> float | None:
    def diff(bps: float) -> float:
        return cagr(net(g109, t109, bps)) - cagr(net(g105, t105, bps))
    if diff(0.0) <= 0:
        return 0.0
    if diff(max_bps) > 0:
        return None
    lo, hi = 0.0, max_bps
    for _ in range(40):
        mid = (lo + hi) / 2
        if diff(mid) > 0:
            lo = mid
        else:
            hi = mid
    return hi


def summarize(f: pd.DataFrame, start: str) -> dict:
    g = f.loc[f.index >= pd.Timestamp(start)].copy()
    p109_25 = net(g.p109_gross, g.p109_turn, 25)
    p109_50 = net(g.p109_gross, g.p109_turn, 50)
    p105_25 = net(g.p105_gross, g.p105_turn, 25)
    p105_50 = net(g.p105_gross, g.p105_turn, 50)
    return {
        "window": {"start": str(g.index.min().date()), "end": str(g.index.max().date()), "months": len(g)},
        "p109_annual_turnover": float(g.p109_turn.mean() * 12),
        "p105_annual_turnover": float(g.p105_turn.mean() * 12),
        "p109_mean_invested_fraction": float(g.p109_invested.mean()),
        "p109_cagr_25bps": cagr(p109_25),
        "p109_cagr_50bps": cagr(p109_50),
        "equal_weight_cagr": cagr(g.equal_weight),
        "p105_cagr_25bps": cagr(p105_25),
        "p105_cagr_50bps": cagr(p105_50),
        "p109_excess_vs_equal_weight_25bps": cagr(p109_25) - cagr(g.equal_weight),
        "p109_excess_vs_equal_weight_50bps": cagr(p109_50) - cagr(g.equal_weight),
        "p109_incremental_vs_p105_25bps": cagr(p109_25) - cagr(p105_25),
        "p109_incremental_vs_p105_50bps": cagr(p109_50) - cagr(p105_50),
        "break_even_cost_bps_vs_static_equal_weight": break_even_vs_static(g.p109_gross, g.p109_turn, g.equal_weight),
        "break_even_common_cost_bps_vs_p105": break_even_vs_p105(g.p109_gross, g.p109_turn, g.p105_gross, g.p105_turn),
        "p109_max_drawdown_25bps": base.metrics(p109_25)["max_drawdown_monthly"],
        "equal_weight_max_drawdown": base.metrics(g.equal_weight)["max_drawdown_monthly"],
        "p105_max_drawdown_25bps": base.metrics(p105_25)["max_drawdown_monthly"],
    }


def main() -> None:
    out = {
        "schema": "research.p135_p109_cost_capacity_break_even_r1",
        "parent_ids": ["P109", "P117", "P125", "P130", "P135"],
        "contract": {
            "purpose": "capital-usage and implementation-cost robustness for fixed P109",
            "representations": {k: list(v) for k, v in REPRESENTATIONS.items()},
            "windows": ["full", "2018-01-31", "2022-01-31"],
            "matched_controls": ["same-universe equal weight", "fixed P105 dual-horizon momentum"],
            "break_even_search_cap_bps": 500,
            "no_strategy_parameter_horizon_topk_or_weight_tuning": True,
        },
        "results": {},
    }
    for rep, assets in REPRESENTATIONS.items():
        base.ASSETS = assets
        base.ALL = (*assets, "BIL", "SPY", "QQQ")
        f, meta = base.build_frame()
        out["results"][rep] = {
            "source": meta,
            "full": summarize(f, str(f.index.min().date())),
            "2018-01-31": summarize(f, "2018-01-31"),
            "2022-01-31": summarize(f, "2022-01-31"),
        }
    full_bes = [out["results"][rep]["full"]["break_even_cost_bps_vs_static_equal_weight"] for rep in REPRESENTATIONS]
    late_bes = [out["results"][rep][start]["break_even_cost_bps_vs_static_equal_weight"] for rep in REPRESENTATIONS for start in ("2018-01-31", "2022-01-31")]
    out["decision"] = "COST_MARGIN_BROAD" if all(x is None or x >= 100 for x in full_bes + late_bes) else "COST_MARGIN_MIXED_OR_THIN"
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p135_p109_cost_capacity_break_even_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {rep: {w: {"be_ew": out["results"][rep][w]["break_even_cost_bps_vs_static_equal_weight"], "be_p105": out["results"][rep][w]["break_even_common_cost_bps_vs_p105"], "excess25": out["results"][rep][w]["p109_excess_vs_equal_weight_25bps"], "inc_p105_25": out["results"][rep][w]["p109_incremental_vs_p105_25bps"], "turn": out["results"][rep][w]["p109_annual_turnover"]} for w in ("full", "2018-01-31", "2022-01-31")} for rep in REPRESENTATIONS}
    print(json.dumps({"decision": out["decision"], "results": compact}, sort_keys=True))


if __name__ == "__main__":
    main()
