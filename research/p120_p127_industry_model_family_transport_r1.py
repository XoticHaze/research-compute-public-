from __future__ import annotations

import json
from pathlib import Path

import research.p104_p111_crossasset_model_family_tournament_r1 as base

INDUSTRY_ASSETS = ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT")
INDUSTRY_ALL = (*INDUSTRY_ASSETS, "BIL", "SPY", "QQQ")
RENAME = {f"P{104+i}": f"P{120+i}" for i in range(8)}


def main() -> None:
    base.ASSETS = INDUSTRY_ASSETS
    base.ALL = INDUSTRY_ALL
    frame, meta = base.build_frame()
    raw = base.evaluate(frame)
    results = {RENAME[k]: v for k, v in raw.items()}
    for pid, rec in results.items():
        rec["transport_of"] = f"P{104 + (int(pid[1:]) - 120)}"
        rec["representation"] = list(INDUSTRY_ASSETS)
    survivors = [k for k, v in results.items() if v["decision"] == "SURVIVES_MATCHED_ALPHA_GATE"]
    ranked = sorted(results, key=lambda k: results[k]["25"]["excess_cagr_vs_equal_weight"], reverse=True)
    out = {
        "schema": "research.p120_p127_industry_model_family_transport_r1",
        "parent_ids": list(results),
        "contract": {
            "purpose": "industry/fund-family transport of exact P104-P111 allocation definitions",
            "representation": list(INDUSTRY_ASSETS),
            "costs_bps": list(base.COSTS),
            "matched_control": "same-universe monthly equal weight",
            "opportunity_cost_comparators": ["same-representation frozen three-factor composite", "SPY", "QQQ"],
            "chronological_folds": 5,
            "no_model_definition_or_parameter_changes": True,
        },
        "source": meta,
        "results": results,
        "ranked_by_25bps_matched_excess": ranked,
        "survivors": survivors,
        "next_rule": "Prefer model families surviving across base, proxy, and industry representations; exact-model failures rotate without nearby tuning.",
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p120_p127_industry_model_family_transport_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {k: {"25_excess": results[k]["25"]["excess_cagr_vs_equal_weight"], "50_excess": results[k]["50"]["excess_cagr_vs_equal_weight"], "folds": results[k]["25"]["positive_folds_vs_equal_weight"], "vs_three_factor": results[k]["25"]["incremental_cagr_vs_p87"], "decision": results[k]["decision"]} for k in ranked}
    print(json.dumps({"survivors": survivors, "ranked": compact, "source_sha256": meta["source_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
