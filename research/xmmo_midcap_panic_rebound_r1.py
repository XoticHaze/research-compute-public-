from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from pathlib import Path

from us_crosscap_momentum_factor_r2 import fetch_prices

CONTRACT = Path("research/xmmo-midcap-panic-rebound-r1.json")
OUTPUT = Path("research/results/xmmo_midcap_panic_rebound_r1.json")


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    candidate = contract["candidate"]
    control = contract["matched_control"]
    state = contract["market_state_symbol"]
    symbols = [candidate, control, state]
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
            "iwb": prices[state][d1] / prices[state][d0] - 1.0,
        })
    if len(rows) < 72:
        raise RuntimeError(f"INSUFFICIENT_COMPLETED_MONTHS:{len(rows)}")

    monthly_cost = (contract["candidate_annual_cost_drag_bps"] / 10000.0) / 12.0
    classified = []
    vols: list[float] = []
    for i, row in enumerate(rows):
        if i > 0:
            prior_for_vol = [r["iwb"] for r in rows[max(0, i - 12):i]]
            prior_vol = statistics.pstdev(prior_for_vol) * math.sqrt(12) if len(prior_for_vol) > 1 else 0.0
        else:
            prior_vol = 0.0
        if i >= 12:
            prior = [r["iwb"] for r in rows[i - 12:i]]
            prior_ret = math.prod(1.0 + x for x in prior) - 1.0
            high_vol = bool(vols) and prior_vol > statistics.median(vols)
            rebound = row["iwb"] > 0.0
            panic = prior_ret < 0.0 and high_vol and rebound
            excess = row["candidate"] - row["control"] - monthly_cost
            classified.append({"month":row["month"],"after_cost_matched_excess":excess,"prior_12m_iwb_return":prior_ret,"prior_12m_iwb_ann_vol":prior_vol,"high_vol_vs_expanding_median":high_vol,"iwb_rebound_month":rebound,"panic_rebound":panic})
        if i > 0:
            vols.append(prior_vol)

    panic = [r["after_cost_matched_excess"] for r in classified if r["panic_rebound"]]
    nonpanic = [r["after_cost_matched_excess"] for r in classified if not r["panic_rebound"]]
    if not panic:
        raise RuntimeError("NO_PANIC_REBOUND_MONTHS_UNDER_FROZEN_STATE")
    panic_mean = statistics.fmean(panic)
    nonpanic_mean = statistics.fmean(nonpanic)
    panic_negative_share = sum(v < 0.0 for v in panic) / len(panic)
    gates = contract["gates"]
    gate_results = {
        "panic_mean_positive": panic_mean > gates["panic_mean_after_cost_matched_excess_gt"],
        "panic_negative_share": panic_negative_share <= gates["panic_negative_excess_share_max"],
        "nonpanic_mean_positive": nonpanic_mean > gates["nonpanic_mean_after_cost_matched_excess_gt"],
    }
    survives = all(gate_results.values())
    out = {
        "schema":"public_research.xmmo_midcap_panic_rebound_result.v1",
        "scientific_id":contract["scientific_id"],
        "months_classified":len(classified),
        "panic_rebound_months":len(panic),
        "panic_mean_after_cost_matched_excess":panic_mean,
        "nonpanic_mean_after_cost_matched_excess":nonpanic_mean,
        "panic_minus_nonpanic_excess":panic_mean-nonpanic_mean,
        "panic_negative_excess_share":panic_negative_share,
        "gate_results":gate_results,
        "decision":"XMMO_MIDCAP_PANIC_REBOUND_SURVIVES_R1" if survives else "XMMO_MIDCAP_REVERSAL_EXPOSURE_DETECTED_R1",
        "classified_months":classified,
        "research_only":True,
        "live_trading_change":False
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps({k:v for k,v in out.items() if k != "classified_months"}, sort_keys=True))


if __name__ == "__main__":
    main()
