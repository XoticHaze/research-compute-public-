from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from us_crosscap_momentum_factor_r1 import cagr, fetch_prices, max_drawdown

CONTRACT = Path("research/us-crosscap-momentum-cap-ablation-r1.json")
OUTPUT = Path("research/results/us_crosscap_momentum_cap_ablation_r1.json")


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    start = dt.datetime.fromisoformat(contract["start"] + "T00:00:00+00:00")
    end = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    candidates = contract["candidate_sleeves"]
    controls = contract["matched_control_sleeves"]
    symbols = candidates + controls
    prices = {s: fetch_prices(s, start, end) for s in symbols}
    common_dates = sorted(set.intersection(*(set(prices[s]) for s in symbols)))
    months: dict[str, list[str]] = {}
    for day in common_dates:
        months.setdefault(day[:7], []).append(day)
    rows = []
    for month, days in sorted(months.items()):
        if len(days) < 10:
            continue
        rows.append({"month": month, "returns": {s: prices[s][days[-1]] / prices[s][days[0]] - 1.0 for s in symbols}})
    if len(rows) < 72:
        raise RuntimeError(f"INSUFFICIENT_COMMON_MONTHS:{len(rows)}")
    recent = [r for r in rows if r["month"] >= contract["recent_start"][:7]]
    cost = contract["candidate_annual_cost_drag_bps"] / 10000.0
    omissions = []
    for omitted_index, omitted in enumerate(candidates):
        keep_indexes = [i for i in range(len(candidates)) if i != omitted_index]
        keep_candidates = [candidates[i] for i in keep_indexes]
        keep_controls = [controls[i] for i in keep_indexes]
        def series(source, names):
            return [sum(r["returns"][s] for s in names) / len(names) for r in source]
        fc = series(rows, keep_candidates); fb = series(rows, keep_controls)
        rc = series(recent, keep_candidates); rb = series(recent, keep_controls)
        full_excess = cagr(fc) - cagr(fb) - cost
        recent_excess = cagr(rc) - cagr(rb) - cost
        rolling = []
        for j in range(11, len(rows)):
            subset = rows[j-11:j+1]
            sc = series(subset, keep_candidates); sb = series(subset, keep_controls)
            rolling.append(cagr(sc) - cagr(sb) - cost)
        rolling_positive_share = sum(x > 0.0 for x in rolling) / len(rolling)
        dd_penalty = max_drawdown(fc) - max_drawdown(fb)
        omissions.append({
            "omitted": omitted,
            "kept_candidates": keep_candidates,
            "kept_controls": keep_controls,
            "full_after_cost_excess": full_excess,
            "recent_after_cost_excess": recent_excess,
            "rolling_12m_positive_share": rolling_positive_share,
            "max_drawdown_penalty": dd_penalty,
        })
    gates = contract["gates"]
    gate_results = {
        "all_loco_full_positive": all(x["full_after_cost_excess"] > gates["all_loco_full_after_cost_excess_gt"] for x in omissions),
        "all_loco_recent_positive": all(x["recent_after_cost_excess"] > gates["all_loco_recent_after_cost_excess_gt"] for x in omissions),
        "all_loco_rolling_breadth": all(x["rolling_12m_positive_share"] >= gates["min_loco_rolling_12m_positive_share"] for x in omissions),
        "all_loco_drawdown": all(x["max_drawdown_penalty"] >= gates["min_loco_max_drawdown_penalty"] for x in omissions),
    }
    passed = all(gate_results.values())
    output = {
        "schema": "public_research.us_crosscap_momentum_cap_ablation_result.v1",
        "scientific_id": contract["scientific_id"],
        "months": len(rows),
        "recent_months": len(recent),
        "omissions": omissions,
        "gates": gates,
        "gate_results": gate_results,
        "decision": "US_CROSSCAP_MOMENTUM_CAP_ABLATION_SURVIVES_R1" if passed else "US_CROSSCAP_MOMENTUM_CAP_ABLATION_REJECTED_R1",
        "research_only": True,
        "live_trading_change": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True))
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
