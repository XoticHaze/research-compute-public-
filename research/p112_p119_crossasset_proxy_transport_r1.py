from __future__ import annotations

import json
from pathlib import Path

import research.p104_p111_crossasset_model_family_tournament_r1 as base

ALT_ASSETS = ("SPY", "EFA", "TLT", "GLD", "DBC")
ALT_ALL = (*ALT_ASSETS, "BIL", "QQQ")
RENAME = {f"P{104+i}": f"P{112+i}" for i in range(8)}


def main() -> None:
    base.ASSETS = ALT_ASSETS
    base.ALL = ALT_ALL
    frame, meta = base.build_frame()
    raw = base.evaluate(frame)
    results = {RENAME[k]: v for k, v in raw.items()}
    for pid, rec in results.items():
        rec["transport_of"] = f"P{104 + (int(pid[1:]) - 112)}"
        rec["representation"] = list(ALT_ASSETS)
    survivors = [k for k, v in results.items() if v["decision"] == "SURVIVES_MATCHED_ALPHA_GATE"]
    ranked = sorted(results, key=lambda k: results[k]["25"]["excess_cagr_vs_equal_weight"], reverse=True)
    out = {
        "schema": "research.p112_p119_crossasset_proxy_transport_r1",
        "parent_ids": list(results),
        "contract": {
            "purpose": "independent proxy-universe transport of exact P104-P111 model-family definitions",
            "representation": list(ALT_ASSETS),
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
        "next_rule": "Cross-representation survivors require intersection with P104-P111 before any deeper mutation. Exact-model failures rotate without nearby tuning.",
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p112_p119_crossasset_proxy_transport_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {k: {"25_excess": results[k]["25"]["excess_cagr_vs_equal_weight"], "50_excess": results[k]["50"]["excess_cagr_vs_equal_weight"], "folds": results[k]["25"]["positive_folds_vs_equal_weight"], "vs_three_factor": results[k]["25"]["incremental_cagr_vs_p87"], "decision": results[k]["decision"]} for k in ranked}
    print(json.dumps({"survivors": survivors, "ranked": compact, "source_sha256": meta["source_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
