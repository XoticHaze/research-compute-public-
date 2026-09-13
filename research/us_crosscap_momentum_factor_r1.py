from __future__ import annotations

import datetime as dt
import json
import math
import urllib.request
from pathlib import Path

CONTRACT = Path("research/us-crosscap-momentum-factor-r1.json")
OUTPUT = Path("research/results/us_crosscap_momentum_factor_r1.json")


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


def compound_excess(candidate: list[float], control: list[float]) -> float:
    return cagr(candidate) - cagr(control)


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    start = dt.datetime.fromisoformat(contract["start"] + "T00:00:00+00:00")
    end = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    candidates = contract["candidate_sleeves"]
    controls = contract["matched_control_sleeves"]
    symbols = candidates + controls
    prices = {symbol: fetch_prices(symbol, start, end) for symbol in symbols}
    common_dates = sorted(set.intersection(*(set(prices[symbol]) for symbol in symbols)))
    months: dict[str, list[str]] = {}
    for day in common_dates:
        months.setdefault(day[:7], []).append(day)

    rows: list[dict] = []
    for month, days in sorted(months.items()):
        if len(days) < 10:
            continue
        sleeve_returns = {
            symbol: prices[symbol][days[-1]] / prices[symbol][days[0]] - 1.0
            for symbol in symbols
        }
        candidate_return = sum(sleeve_returns[s] for s in candidates) / len(candidates)
        control_return = sum(sleeve_returns[s] for s in controls) / len(controls)
        rows.append(
            {
                "month": month,
                "candidate": candidate_return,
                "control": control_return,
                "sleeves": sleeve_returns,
            }
        )
    if len(rows) < 72:
        raise RuntimeError(f"INSUFFICIENT_COMMON_MONTHS:{len(rows)}")

    recent = [row for row in rows if row["month"] >= contract["recent_start"][:7]]
    annual_cost_drag = contract["candidate_annual_cost_drag_bps"] / 10000.0
    full_candidate = [row["candidate"] for row in rows]
    full_control = [row["control"] for row in rows]
    recent_candidate = [row["candidate"] for row in recent]
    recent_control = [row["control"] for row in recent]
    full_excess = compound_excess(full_candidate, full_control) - annual_cost_drag
    recent_excess = compound_excess(recent_candidate, recent_control) - annual_cost_drag

    yearly = []
    for year in sorted({row["month"][:4] for row in rows}):
        subset = [row for row in rows if row["month"].startswith(year)]
        if len(subset) < 10:
            continue
        excess = compound_excess(
            [row["candidate"] for row in subset],
            [row["control"] for row in subset],
        ) - annual_cost_drag
        yearly.append({"year": year, "after_cost_excess": excess, "positive": excess > 0.0})

    rolling = []
    for index in range(11, len(rows)):
        subset = rows[index - 11 : index + 1]
        excess = compound_excess(
            [row["candidate"] for row in subset],
            [row["control"] for row in subset],
        ) - annual_cost_drag
        rolling.append(excess)
    rolling_positive_share = sum(value > 0.0 for value in rolling) / len(rolling)

    segment_results = []
    for candidate, control in zip(candidates, controls):
        full_seg_candidate = [row["sleeves"][candidate] for row in rows]
        full_seg_control = [row["sleeves"][control] for row in rows]
        recent_seg_candidate = [row["sleeves"][candidate] for row in recent]
        recent_seg_control = [row["sleeves"][control] for row in recent]
        segment_results.append(
            {
                "candidate": candidate,
                "control": control,
                "full_after_cost_excess": compound_excess(full_seg_candidate, full_seg_control) - annual_cost_drag,
                "recent_after_cost_excess": compound_excess(recent_seg_candidate, recent_seg_control) - annual_cost_drag,
            }
        )

    candidate_dd = max_drawdown(full_candidate)
    control_dd = max_drawdown(full_control)
    dd_penalty = candidate_dd - control_dd
    positive_years = sum(row["positive"] for row in yearly)
    positive_segments_full = sum(row["full_after_cost_excess"] > 0.0 for row in segment_results)
    positive_segments_recent = sum(row["recent_after_cost_excess"] > 0.0 for row in segment_results)
    gates = contract["gates"]
    gate_results = {
        "full_after_cost_excess": full_excess >= gates["full_after_cost_excess_min"],
        "recent_after_cost_excess": recent_excess >= gates["recent_after_cost_excess_min"],
        "positive_calendar_years": positive_years >= gates["min_positive_calendar_years"],
        "rolling_12m_positive_share": rolling_positive_share >= gates["rolling_12m_positive_share_min"],
        "max_drawdown_penalty": dd_penalty >= gates["max_drawdown_penalty_min"],
        "positive_segments_full": positive_segments_full >= gates["min_positive_segments_full"],
        "positive_segments_recent": positive_segments_recent >= gates["min_positive_segments_recent"],
    }
    passed = all(gate_results.values())
    output = {
        "schema": "public_research.us_crosscap_momentum_factor_result.v1",
        "scientific_id": contract["scientific_id"],
        "months": len(rows),
        "recent_months": len(recent),
        "full_candidate_cagr": cagr(full_candidate),
        "full_control_cagr": cagr(full_control),
        "full_after_cost_excess": full_excess,
        "recent_candidate_cagr": cagr(recent_candidate),
        "recent_control_cagr": cagr(recent_control),
        "recent_after_cost_excess": recent_excess,
        "positive_calendar_years": positive_years,
        "calendar_years_scored": len(yearly),
        "rolling_12m_positive_share": rolling_positive_share,
        "candidate_max_drawdown": candidate_dd,
        "control_max_drawdown": control_dd,
        "max_drawdown_penalty": dd_penalty,
        "positive_segments_full": positive_segments_full,
        "positive_segments_recent": positive_segments_recent,
        "segments": segment_results,
        "yearly": yearly,
        "gates": gates,
        "gate_results": gate_results,
        "decision": "US_CROSSCAP_MOMENTUM_FACTOR_SURVIVES_R1" if passed else "US_CROSSCAP_MOMENTUM_FACTOR_REJECTED_R1",
        "research_only": True,
        "live_trading_change": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, sort_keys=True))
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
