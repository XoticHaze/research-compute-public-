from __future__ import annotations

import json
from pathlib import Path

import fixed_multifactor_cross_sectional_r1 as base
import fixed_multifactor_cross_sectional_r1_complete_month as guard

ALT = ("VTI", "VUG", "IEF", "IAU", "GSG")
base.UNIVERSES["crossasset"] = ALT
base.features = guard._complete_month_features

if __name__ == "__main__":
    result = base.evaluate("crossasset")
    result["schema"] = "research.crossasset_composite_proxy_transfer_r1"
    result["representation"] = {
        "original_categories": ["broad_equity", "growth_equity", "treasury", "gold", "broad_commodities"],
        "alternate_proxies": list(ALT),
        "economics_unchanged": True,
        "score_unchanged": "mom6+trend200+inverse_vol6+drawdown6 equal-weight percentile rank",
        "top_k": 2,
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/crossasset_composite_proxy_transfer.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"decision": result["decision"], "excess25": result["costs"]["25"]["excess_cagr_vs_equal_weight"], "folds": result["costs"]["25"]["positive_excess_folds"], "excess50": result["costs"]["50"]["excess_cagr_vs_equal_weight"]}, sort_keys=True))
