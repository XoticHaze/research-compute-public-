from __future__ import annotations

import datetime as dt
import json
import urllib.request
from pathlib import Path

CONTRACT = Path("research/us-crosscap-momentum-factor-r2.json")
OUTPUT = Path("research/results/us_crosscap_momentum_factor_r2.json")


def fetch_prices(symbol: str, start: dt.datetime, end: dt.datetime) -> dict[str, float]:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={int(start.timestamp())}&period2={int(end.timestamp())}"
        "&interval=1d&events=history&includeAdjustedClose=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310 fixed HTTPS host
        result = json.load(response)["chart"]["result"][0]
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
    values = adjusted or result["indicators"]["quote"][0]["close"]
    return {
        dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat(): float(px)
        for ts, px in zip(result["timestamp"], values)
        if px is not None
    }


def cagr(returns: list[float]) -> float:
    growth = 1.0
    for value in returns:
        growth *= 1.0 + value
    return growth ** (12.0 / len(returns)) - 1.0


def max_drawdown(returns: list[float]) -> float:
    value = peak = 1.0
    worst = 0.0
    for ret in returns:
        value *= 1.0 + ret
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    candidates = contract["candidate_sleeves"]
    controls = contract["matched_control_sleeves"]
    symbols = candidates + controls
    # Warmup month supplies the prior month-end needed for January 2018 return.
    fetch_start = dt.datetime(2017, 12, 1, tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    prices = {s: fetch_prices(s, fetch_start, now + dt.timedelta(days=1)) for s in symbols}
    common_dates = sorted(set.intersection(*(set(prices[s]) for s in symbols)))
    month_dates: dict[str, list[str]] = {}
    for day in common_dates:
        month_dates.setdefault(day[:7], []).append(day)
    month_end = {month: days[-1] for month, days in month_dates.items()}
    months = sorted(month_end)
    current_month = now.strftime("%Y-%m")
    rows: list[dict] = []
    for idx in range(1, len(months)):
        month = months[idx]
        if month < contract["evaluation_start_month"] or month >= current_month:
            continue
        prev_month = months[idx - 1]
        current_day = month_end[month]
        previous_day = month_end[prev_month]
        sleeve_returns = {
            s: prices[s][current_day] / prices[s][previous_day] - 1.0
            for s in symbols
        }
        rows.append({
            "month": month,
            "candidate": sum(sleeve_returns[s] for s in candidates) / len(candidates),
            "control": sum(sleeve_returns[s] for s in controls) / len(controls),
            "sleeves": sleeve_returns,
        })
    if len(rows) < 72:
        raise RuntimeError(f"INSUFFICIENT_COMPLETED_MONTHS:{len(rows)}")

    recent = [r for r in rows if r["month"] >= contract["recent_start_month"]]
    annual_cost = contract["candidate_annual_cost_drag_bps"] / 10000.0
    full_candidate = [r["candidate"] for r in rows]
    full_control = [r["control"] for r in rows]
    recent_candidate = [r["candidate"] for r in recent]
    recent_control = [r["control"] for r in recent]
    full_excess = cagr(full_candidate) - cagr(full_control) - annual_cost
    recent_excess = cagr(recent_candidate) - cagr(recent_control) - annual_cost

    yearly = []
    for year in sorted({r["month"][:4] for r in rows}):
        subset = [r for r in rows if r["month"].startswith(year)]
        if len(subset) < 10:
            continue
        excess = cagr([r["candidate"] for r in subset]) - cagr([r["control"] for r in subset]) - annual_cost
        yearly.append({"year": year, "after_cost_excess": excess, "positive": excess > 0.0})

    rolling = []
    for idx in range(11, len(rows)):
        subset = rows[idx - 11: idx + 1]
        rolling.append(cagr([r["candidate"] for r in subset]) - cagr([r["control"] for r in subset]) - annual_cost)
    rolling_positive_share = sum(v > 0.0 for v in rolling) / len(rolling)

    segments = []
    for candidate, control in zip(candidates, controls):
        segments.append({
            "candidate": candidate,
            "control": control,
            "full_after_cost_excess": cagr([r["sleeves"][candidate] for r in rows]) - cagr([r["sleeves"][control] for r in rows]) - annual_cost,
            "recent_after_cost_excess": cagr([r["sleeves"][candidate] for r in recent]) - cagr([r["sleeves"][control] for r in recent]) - annual_cost,
        })

    candidate_dd = max_drawdown(full_candidate)
    control_dd = max_drawdown(full_control)
    dd_penalty = candidate_dd - control_dd
    gates = contract["gates"]
    gate_results = {
        "full_after_cost_excess": full_excess >= gates["full_after_cost_excess_min"],
        "recent_after_cost_excess": recent_excess >= gates["recent_after_cost_excess_min"],
        "positive_calendar_years": sum(r["positive"] for r in yearly) >= gates["min_positive_calendar_years"],
        "rolling_12m_positive_share": rolling_positive_share >= gates["rolling_12m_positive_share_min"],
        "max_drawdown_penalty": dd_penalty >= gates["max_drawdown_penalty_min"],
        "positive_segments_full": sum(r["full_after_cost_excess"] > 0.0 for r in segments) >= gates["min_positive_segments_full"],
        "positive_segments_recent": sum(r["recent_after_cost_excess"] > 0.0 for r in segments) >= gates["min_positive_segments_recent"],
    }
    passed = all(gate_results.values())
    out = {
        "schema": "public_research.us_crosscap_momentum_factor_result.v2",
        "scientific_id": contract["scientific_id"],
        "invalidated_predecessor": "US-CROSSCAP-MOMENTUM-FACTOR-R1-20260913",
        "correction": "month-end to prior-month-end adjusted-close returns; completed calendar months only",
        "months": len(rows),
        "recent_months": len(recent),
        "last_scored_month": rows[-1]["month"],
        "full_candidate_cagr": cagr(full_candidate),
        "full_control_cagr": cagr(full_control),
        "full_after_cost_excess": full_excess,
        "recent_candidate_cagr": cagr(recent_candidate),
        "recent_control_cagr": cagr(recent_control),
        "recent_after_cost_excess": recent_excess,
        "positive_calendar_years": sum(r["positive"] for r in yearly),
        "calendar_years_scored": len(yearly),
        "rolling_12m_positive_share": rolling_positive_share,
        "candidate_max_drawdown": candidate_dd,
        "control_max_drawdown": control_dd,
        "max_drawdown_penalty": dd_penalty,
        "segments": segments,
        "yearly": yearly,
        "gate_results": gate_results,
        "decision": "US_CROSSCAP_MOMENTUM_FACTOR_SURVIVES_R2" if passed else "US_CROSSCAP_MOMENTUM_FACTOR_REJECTED_R2",
        "research_only": True,
        "live_trading_change": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
