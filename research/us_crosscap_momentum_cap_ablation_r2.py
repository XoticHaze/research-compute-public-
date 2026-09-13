from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from us_crosscap_momentum_factor_r2 import cagr, fetch_prices, max_drawdown

CONTRACT = Path("research/us-crosscap-momentum-cap-ablation-r2.json")
OUTPUT = Path("research/results/us_crosscap_momentum_cap_ablation_r2.json")


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    candidates = contract["candidate_sleeves"]
    controls = contract["matched_control_sleeves"]
    symbols = candidates + controls
    now = dt.datetime.now(dt.timezone.utc)
    prices = {s: fetch_prices(s, dt.datetime(2017, 12, 1, tzinfo=dt.timezone.utc), now + dt.timedelta(days=1)) for s in symbols}
    common_dates = sorted(set.intersection(*(set(prices[s]) for s in symbols)))
    month_dates: dict[str, list[str]] = {}
    for day in common_dates:
        month_dates.setdefault(day[:7], []).append(day)
    month_end = {month: days[-1] for month, days in month_dates.items()}
    months = sorted(month_end)
    current_month = now.strftime("%Y-%m")
    rows = []
    for idx in range(1, len(months)):
        month = months[idx]
        if month < contract["evaluation_start_month"] or month >= current_month:
            continue
        prior = months[idx - 1]
        current_day, prior_day = month_end[month], month_end[prior]
        rows.append({"month": month, "returns": {s: prices[s][current_day] / prices[s][prior_day] - 1.0 for s in symbols}})
    if len(rows) < 72:
        raise RuntimeError(f"INSUFFICIENT_COMPLETED_MONTHS:{len(rows)}")
    recent = [r for r in rows if r["month"] >= contract["recent_start_month"]]
    annual_cost = contract["candidate_annual_cost_drag_bps"] / 10000.0
    omissions = []
    for omitted_index, omitted in enumerate(candidates):
        keep_indexes = [i for i in range(len(candidates)) if i != omitted_index]
        keep_candidates = [candidates[i] for i in keep_indexes]
        keep_controls = [controls[i] for i in keep_indexes]
        def series(source, names):
            return [sum(r["returns"][s] for s in names) / len(names) for r in source]
        fc, fb = series(rows, keep_candidates), series(rows, keep_controls)
        rc, rb = series(recent, keep_candidates), series(recent, keep_controls)
        rolling = []
        for j in range(11, len(rows)):
            subset = rows[j - 11:j + 1]
            sc, sb = series(subset, keep_candidates), series(subset, keep_controls)
            rolling.append(cagr(sc) - cagr(sb) - annual_cost)
        omissions.append({
            "omitted": omitted,
            "kept_candidates": keep_candidates,
            "kept_controls": keep_controls,
            "full_after_cost_excess": cagr(fc) - cagr(fb) - annual_cost,
            "recent_after_cost_excess": cagr(rc) - cagr(rb) - annual_cost,
            "rolling_12m_positive_share": sum(x > 0.0 for x in rolling) / len(rolling),
            "max_drawdown_penalty": max_drawdown(fc) - max_drawdown(fb),
        })
    gates = contract["gates"]
    gate_results = {
        "all_loco_full_positive": all(x["full_after_cost_excess"] > gates["all_loco_full_after_cost_excess_gt"] for x in omissions),
        "all_loco_recent_positive": all(x["recent_after_cost_excess"] > gates["all_loco_recent_after_cost_excess_gt"] for x in omissions),
        "all_loco_rolling_breadth": all(x["rolling_12m_positive_share"] >= gates["min_loco_rolling_12m_positive_share"] for x in omissions),
        "all_loco_drawdown": all(x["max_drawdown_penalty"] >= gates["min_loco_max_drawdown_penalty"] for x in omissions),
    }
    passed = all(gate_results.values())
    out = {
        "schema": "public_research.us_crosscap_momentum_cap_ablation_result.v2",
        "scientific_id": contract["scientific_id"],
        "invalidated_predecessor": contract["invalidated_predecessor"],
        "months": len(rows),
        "recent_months": len(recent),
        "last_scored_month": rows[-1]["month"],
        "omissions": omissions,
        "gate_results": gate_results,
        "decision": "US_CROSSCAP_MOMENTUM_CAP_ABLATION_SURVIVES_R2" if passed else "US_CROSSCAP_MOMENTUM_CAP_ABLATION_REJECTED_R2",
        "research_only": True,
        "live_trading_change": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
