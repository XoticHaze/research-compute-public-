from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from us_crosscap_momentum_factor_r2 import cagr, fetch_prices

CONTRACT = Path("research/xmmo-midcap-loco-year-r1.json")
OUTPUT = Path("research/results/xmmo_midcap_loco_year_r1.json")


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    candidate = contract["candidate"]
    control = contract["matched_control"]
    symbols = [candidate, control]
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
        d1, d0 = month_end[month], month_end[prior]
        rows.append({
            "month": month,
            "candidate": prices[candidate][d1] / prices[candidate][d0] - 1.0,
            "control": prices[control][d1] / prices[control][d0] - 1.0,
        })
    if len(rows) < 72:
        raise RuntimeError(f"INSUFFICIENT_COMPLETED_MONTHS:{len(rows)}")
    annual_cost = contract["candidate_annual_cost_drag_bps"] / 10000.0

    def excess(source):
        return cagr([r["candidate"] for r in source]) - cagr([r["control"] for r in source]) - annual_cost

    recent = [r for r in rows if r["month"] >= contract["recent_start_month"]]
    years = sorted({r["month"][:4] for r in rows})
    full_years = [y for y in years if sum(r["month"].startswith(y) for r in rows) >= 10]
    recent_full_years = [y for y in full_years if y >= contract["recent_start_month"][:4]]
    full_loco = []
    for year in full_years:
        subset = [r for r in rows if not r["month"].startswith(year)]
        full_loco.append({"omitted_year": year, "months": len(subset), "after_cost_excess": excess(subset)})
    recent_loco = []
    for year in recent_full_years:
        subset = [r for r in recent if not r["month"].startswith(year)]
        recent_loco.append({"omitted_year": year, "months": len(subset), "after_cost_excess": excess(subset)})
    if not full_loco or not recent_loco:
        raise RuntimeError("INSUFFICIENT_LOCO_YEARS")
    gates = contract["gates"]
    gate_results = {
        "all_full_loco_positive": all(r["after_cost_excess"] > gates["all_full_leave_one_year_out_excess_gt"] for r in full_loco),
        "all_recent_loco_positive": all(r["after_cost_excess"] > gates["all_recent_leave_one_year_out_excess_gt"] for r in recent_loco),
    }
    survives = all(gate_results.values())
    out = {
        "schema": "public_research.xmmo_midcap_loco_year_result.v1",
        "scientific_id": contract["scientific_id"],
        "months": len(rows),
        "recent_months": len(recent),
        "last_scored_month": rows[-1]["month"],
        "base_full_after_cost_excess": excess(rows),
        "base_recent_after_cost_excess": excess(recent),
        "full_leave_one_year_out": full_loco,
        "recent_leave_one_year_out": recent_loco,
        "worst_full_loco_excess": min(r["after_cost_excess"] for r in full_loco),
        "worst_recent_loco_excess": min(r["after_cost_excess"] for r in recent_loco),
        "gate_results": gate_results,
        "decision": "XMMO_MIDCAP_LOCO_YEAR_SURVIVES_R1" if survives else "XMMO_MIDCAP_LOCO_YEAR_REJECTED_R1",
        "research_only": True,
        "live_trading_change": False
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
