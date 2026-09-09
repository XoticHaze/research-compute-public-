from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import p104_p111_crossasset_model_family_tournament_r1 as base

MAP = {"P128": "p104", "P129": "p105", "P130": "p109"}
SOURCE = {"P128": "P104", "P129": "P105", "P130": "P109"}


def folds(a: pd.Series, b: pd.Series, n: int = 3) -> int:
    out = 0
    for idx in np.array_split(np.arange(len(a)), n):
        if len(idx) and base.metrics(a.iloc[idx])["cagr"] > base.metrics(b.iloc[idx])["cagr"]:
            out += 1
    return out


def eval_one(g: pd.DataFrame, key: str, bps: int) -> dict:
    r = g[f"{key}_gross"] - g[f"{key}_turn"] * bps / 10000
    p87 = g.p87_gross - g.p87_turn * bps / 10000
    ew = g.equal_weight
    excess = r - ew
    drop_n = min(5, len(excess))
    keep = excess.sort_values(ascending=False).index[drop_n:]
    rm, em, pm = base.metrics(r), base.metrics(ew), base.metrics(p87)
    rm_trim, em_trim = base.metrics(r.loc[keep]), base.metrics(ew.loc[keep])
    return {
        "strategy": rm,
        "equal_weight": em,
        "p87": pm,
        "excess_cagr_vs_equal_weight": rm["cagr"] - em["cagr"],
        "incremental_cagr_vs_p87": rm["cagr"] - pm["cagr"],
        "positive_chronological_folds_vs_equal_weight": folds(r, ew),
        "five_strongest_relative_months_removed_excess_cagr": rm_trim["cagr"] - em_trim["cagr"],
        "annual_turnover": float(g[f"{key}_turn"].mean() * 12),
    }


def main() -> None:
    f, meta = base.build_frame()
    out = {
        "schema": "research.p128_p130_survivor_temporal_concentration_r1",
        "parent_ids": list(MAP),
        "contract": {
            "source_models": SOURCE,
            "holdouts": ["2018-01-31", "2022-01-31"],
            "costs_bps": [25, 50],
            "controls": ["same-universe equal weight", "frozen P87", "SPY", "QQQ"],
            "chronological_folds_per_holdout": 3,
            "concentration_test": "remove five strongest strategy-minus-equal-weight months without re-optimizing",
            "no_model_definition_parameter_or_weight_tuning": True,
        },
        "source": meta,
        "results": {},
    }
    for pid, key in MAP.items():
        rec = {"source_model": SOURCE[pid], "holdouts": {}}
        for start in ("2018-01-31", "2022-01-31"):
            g = f.loc[f.index >= pd.Timestamp(start)].copy()
            h = {"window": {"start": str(g.index.min().date()), "end": str(g.index.max().date()), "months": len(g)}}
            for bps in (25, 50):
                h[str(bps)] = eval_one(g, key, bps)
            rec["holdouts"][start] = h
        robust = all(
            rec["holdouts"][start][str(bps)]["excess_cagr_vs_equal_weight"] > 0
            for start in ("2018-01-31", "2022-01-31") for bps in (25, 50)
        ) and all(rec["holdouts"][start]["25"]["positive_chronological_folds_vs_equal_weight"] >= 2 for start in ("2018-01-31", "2022-01-31"))
        concentrated = any(rec["holdouts"][start]["25"]["five_strongest_relative_months_removed_excess_cagr"] <= 0 for start in ("2018-01-31", "2022-01-31"))
        rec["decision"] = "LATE_ERA_PERSISTENT_BUT_CONCENTRATED" if robust and concentrated else "LATE_ERA_PERSISTENT" if robust else "LATE_ERA_SUPPORT_NOT_ROBUST"
        out["results"][pid] = rec
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p128_p130_survivor_temporal_concentration_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {pid: {"decision": rec["decision"], "2018_25_excess": rec["holdouts"]["2018-01-31"]["25"]["excess_cagr_vs_equal_weight"], "2018_trim": rec["holdouts"]["2018-01-31"]["25"]["five_strongest_relative_months_removed_excess_cagr"], "2022_25_excess": rec["holdouts"]["2022-01-31"]["25"]["excess_cagr_vs_equal_weight"], "2022_trim": rec["holdouts"]["2022-01-31"]["25"]["five_strongest_relative_months_removed_excess_cagr"]} for pid, rec in out["results"].items()}
    print(json.dumps(compact, sort_keys=True))


if __name__ == "__main__":
    main()
