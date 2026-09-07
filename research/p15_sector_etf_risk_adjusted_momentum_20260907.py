#!/usr/bin/env python3
"""P15: prospective sector-ETF risk-adjusted momentum scarce-capital discriminator.

Frozen before first execution:
- Universe: nine long-lived US Select Sector SPDR ETFs: XLB XLE XLF XLI XLK XLP XLU XLV XLY.
- Decision cadence: month-end signal, next-session entry, hold until next decision.
- Candidate score: prior 126-session total return / prior 63-session annualized realized volatility.
- Eligibility: prior 126-session return > 0. Select top 3 eligible, otherwise cash for missing slots.
- Controls: raw 126-session momentum top 3 with same positive-return eligibility; equal-weight sector basket; SPY; QQQ.
- Costs: 10/25/50 bps one-way turnover charge at each rebalance. Primary 25 bps.
- No parameter search, no tuning after results.

Data source is Stooq public daily adjusted-price CSV. The script fails closed if any required series
cannot be loaded or if the common matched calendar is insufficient.
"""
from __future__ import annotations

import csv
import io
import json
import math
import statistics
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

UNIVERSE = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
BASELINES = ["SPY", "QQQ"]
ALL = UNIVERSE + BASELINES
START = "20000101"
END = "20260904"
LOOKBACK = 126
VOL_WINDOW = 63
TOP_N = 3
COSTS_BPS = [10.0, 25.0, 50.0]
PRIMARY_COST = 25.0
OUT = Path("results/p15_sector_etf_risk_adjusted_momentum_result_20260907.json")


def fetch_stooq(symbol: str) -> dict[str, float]:
    params = urllib.parse.urlencode({"s": symbol.lower() + ".us", "d1": START, "d2": END, "i": "d"})
    url = "https://stooq.com/q/d/l/?" + params
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 research-only"})
    with urllib.request.urlopen(req, timeout=45) as r:
        raw = r.read().decode("utf-8", errors="strict")
    rows = list(csv.DictReader(io.StringIO(raw)))
    out: dict[str, float] = {}
    for row in rows:
        try:
            d = row["Date"]
            close = float(row["Close"])
            if close > 0:
                out[d] = close
        except (KeyError, ValueError, TypeError):
            continue
    if len(out) < LOOKBACK + 252:
        raise RuntimeError(f"insufficient_source_rows:{symbol}:{len(out)}")
    return out


def ret(px: list[float], i0: int, i1: int) -> float:
    return px[i1] / px[i0] - 1.0


def ann_vol(px: list[float], end_idx: int, window: int) -> float:
    rs = [math.log(px[j] / px[j - 1]) for j in range(end_idx - window + 1, end_idx + 1)]
    return statistics.stdev(rs) * math.sqrt(252.0) if len(rs) >= 2 else float("nan")


def month_key(date_str: str) -> str:
    return date_str[:7]


def max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def summarize(period_returns: list[tuple[str, float]]) -> dict:
    eq = [1.0]
    by_year: dict[str, float] = defaultdict(lambda: 1.0)
    for d, r in period_returns:
        eq.append(eq[-1] * (1.0 + r))
        by_year[d[:4]] *= 1.0 + r
    total = eq[-1] - 1.0
    if period_returns:
        d0 = datetime.strptime(period_returns[0][0], "%Y-%m-%d")
        d1 = datetime.strptime(period_returns[-1][0], "%Y-%m-%d")
        years = max((d1 - d0).days / 365.25, 1.0 / 12.0)
        cagr = eq[-1] ** (1.0 / years) - 1.0
    else:
        cagr = float("nan")
    return {
        "periods": len(period_returns),
        "total_return": total,
        "cagr": cagr,
        "max_drawdown": max_drawdown(eq),
        "year_returns": {y: v - 1.0 for y, v in sorted(by_year.items())},
    }


def weights(selected: list[str]) -> dict[str, float]:
    if not selected:
        return {}
    w = 1.0 / TOP_N
    return {s: w for s in selected[:TOP_N]}


def turnover(prev: dict[str, float], new: dict[str, float]) -> float:
    names = set(prev) | set(new)
    # one-way traded notional as half L1; cash is implicit and included by residual difference
    risky_l1 = sum(abs(new.get(s, 0.0) - prev.get(s, 0.0)) for s in names)
    cash_prev = 1.0 - sum(prev.values())
    cash_new = 1.0 - sum(new.values())
    return 0.5 * (risky_l1 + abs(cash_new - cash_prev))


def run() -> dict:
    series = {s: fetch_stooq(s) for s in ALL}
    common = sorted(set.intersection(*(set(series[s]) for s in ALL)))
    if len(common) < LOOKBACK + 1000:
        raise RuntimeError(f"insufficient_common_calendar:{len(common)}")
    prices = {s: [series[s][d] for d in common] for s in ALL}

    # Month-end signal indices, requiring a next session for realized holding return.
    signal_idx = []
    for i in range(LOOKBACK, len(common) - 1):
        if month_key(common[i]) != month_key(common[i + 1]):
            signal_idx.append(i)
    if len(signal_idx) < 60:
        raise RuntimeError(f"insufficient_decisions:{len(signal_idx)}")

    decisions = []
    for k, i in enumerate(signal_idx[:-1]):
        next_i = signal_idx[k + 1]
        candidate_scores = {}
        raw_scores = {}
        for s in UNIVERSE:
            r126 = ret(prices[s], i - LOOKBACK, i)
            v63 = ann_vol(prices[s], i, VOL_WINDOW)
            raw_scores[s] = r126
            candidate_scores[s] = r126 / v63 if (r126 > 0 and math.isfinite(v63) and v63 > 0) else -math.inf
        cand = [s for s, sc in sorted(candidate_scores.items(), key=lambda kv: (-kv[1], kv[0])) if math.isfinite(sc)][:TOP_N]
        raw = [s for s, sc in sorted(raw_scores.items(), key=lambda kv: (-kv[1], kv[0])) if sc > 0][:TOP_N]
        decisions.append({
            "signal_date": common[i],
            "end_date": common[next_i],
            "i": i,
            "j": next_i,
            "candidate": cand,
            "raw": raw,
        })

    policy_returns: dict[str, dict[float, list[tuple[str, float]]]] = {
        "risk_adjusted": {c: [] for c in COSTS_BPS},
        "raw_momentum": {c: [] for c in COSTS_BPS},
    }
    baseline_returns: dict[str, list[tuple[str, float]]] = {"equal_sector": [], "SPY": [], "QQQ": []}
    prev_w = {"risk_adjusted": {}, "raw_momentum": {}}
    turn = defaultdict(list)

    for d in decisions:
        i, j, end_date = d["i"], d["j"], d["end_date"]
        for label, key in [("risk_adjusted", "candidate"), ("raw_momentum", "raw")]:
            w = weights(d[key])
            gross = sum(wt * ret(prices[s], i, j) for s, wt in w.items())
            to = turnover(prev_w[label], w)
            turn[label].append(to)
            for c in COSTS_BPS:
                net = gross - to * (c / 10000.0)
                policy_returns[label][c].append((end_date, net))
            prev_w[label] = w
        ew = sum(ret(prices[s], i, j) for s in UNIVERSE) / len(UNIVERSE)
        baseline_returns["equal_sector"].append((end_date, ew))
        baseline_returns["SPY"].append((end_date, ret(prices["SPY"], i, j)))
        baseline_returns["QQQ"].append((end_date, ret(prices["QQQ"], i, j)))

    summaries = {
        "risk_adjusted": {str(int(c)): summarize(policy_returns["risk_adjusted"][c]) for c in COSTS_BPS},
        "raw_momentum": {str(int(c)): summarize(policy_returns["raw_momentum"][c]) for c in COSTS_BPS},
        "equal_sector": summarize(baseline_returns["equal_sector"]),
        "SPY": summarize(baseline_returns["SPY"]),
        "QQQ": summarize(baseline_returns["QQQ"]),
    }

    ckey = str(int(PRIMARY_COST))
    cand_years = summaries["risk_adjusted"][ckey]["year_returns"]
    raw_years = summaries["raw_momentum"][ckey]["year_returns"]
    ew_years = summaries["equal_sector"]["year_returns"]
    spy_years = summaries["SPY"]["year_returns"]
    qqq_years = summaries["QQQ"]["year_returns"]
    full_years = sorted(set(cand_years) & set(raw_years) & set(ew_years) & set(spy_years) & set(qqq_years))
    # Remove partial endpoint years from robustness count.
    if full_years and common[decisions[0]["i"]][:4] in full_years:
        full_years = full_years[1:]
    if full_years and common[decisions[-1]["j"]][:4] in full_years:
        full_years = full_years[:-1]

    year_excess = {}
    for y in full_years:
        year_excess[y] = {
            "vs_raw": cand_years[y] - raw_years[y],
            "vs_equal_sector": cand_years[y] - ew_years[y],
            "vs_SPY": cand_years[y] - spy_years[y],
            "vs_QQQ": cand_years[y] - qqq_years[y],
        }

    primary = summaries["risk_adjusted"][ckey]
    rawp = summaries["raw_momentum"][ckey]
    ew = summaries["equal_sector"]
    spy = summaries["SPY"]
    qqq = summaries["QQQ"]
    positive_vs_raw = sum(1 for y in full_years if year_excess[y]["vs_raw"] > 0)
    positive_vs_ew = sum(1 for y in full_years if year_excess[y]["vs_equal_sector"] > 0)
    positive_vs_spy = sum(1 for y in full_years if year_excess[y]["vs_SPY"] > 0)

    # High bar: incremental mechanism must beat raw momentum and equal-sector in >=60% full years,
    # and beat both on pooled CAGR at primary cost. Broad-market deltas are context, not sole gate.
    robust = (
        len(full_years) >= 10
        and positive_vs_raw / len(full_years) >= 0.60
        and positive_vs_ew / len(full_years) >= 0.60
        and primary["cagr"] > rawp["cagr"]
        and primary["cagr"] > ew["cagr"]
    )
    decision = "P15_RISK_ADJUSTED_SECTOR_MOMENTUM_CONTINUE" if robust else "P15_RISK_ADJUSTED_SECTOR_MOMENTUM_NOT_SUPPORTED"

    return {
        "schema": "public_compute.p15_sector_etf_risk_adjusted_momentum.v1",
        "frozen_hypothesis": "Risk-adjusting 126-session sector-ETF momentum by prior 63-session realized volatility improves scarce-capital top-3 selection versus raw momentum.",
        "decision": decision,
        "source": {"provider": "Stooq", "start_request": START, "end_request": END},
        "matched_window": {"signal_start": decisions[0]["signal_date"], "return_end": decisions[-1]["end_date"], "common_daily_rows": len(common), "monthly_decisions": len(decisions)},
        "universe": UNIVERSE,
        "parameters": {"lookback_sessions": LOOKBACK, "vol_window_sessions": VOL_WINDOW, "top_n": TOP_N, "primary_cost_bps": PRIMARY_COST, "cost_stress_bps": COSTS_BPS},
        "summaries": summaries,
        "primary_25bps_excess": {
            "cagr_vs_raw": primary["cagr"] - rawp["cagr"],
            "cagr_vs_equal_sector": primary["cagr"] - ew["cagr"],
            "cagr_vs_SPY": primary["cagr"] - spy["cagr"],
            "cagr_vs_QQQ": primary["cagr"] - qqq["cagr"],
            "full_years": len(full_years),
            "positive_years_vs_raw": positive_vs_raw,
            "positive_years_vs_equal_sector": positive_vs_ew,
            "positive_years_vs_SPY": positive_vs_spy,
            "year_excess": year_excess,
        },
        "turnover": {k: {"mean_one_way": statistics.mean(v), "median_one_way": statistics.median(v)} for k, v in turn.items()},
        "capital_context": "Top-3 monthly sector ETFs; ETF liquidity/capacity is materially broader than single-stock micro-cap screens, but no market-impact model is claimed.",
        "limitations": ["Stooq adjusted-price semantics are used consistently across candidate and controls.", "This is an ETF-level allocator test, not constituent-level alpha.", "No parameter search or post-result tuning is permitted."],
    }


if __name__ == "__main__":
    try:
        result = run()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        print(f"P15_RESULT_PATH={OUT}")
    except Exception as exc:
        print(f"P15_EXECUTION_ERROR={type(exc).__name__}:{exc}", file=sys.stderr)
        raise
