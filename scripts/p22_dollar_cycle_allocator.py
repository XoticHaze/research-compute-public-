#!/usr/bin/env python3
"""Frozen P22 second-child discriminator using an independent US-dollar state."""
import json
import urllib.request
from datetime import datetime, timezone

SYMS = ["UUP", "SMH", "QQQ", "SPY"]
START = 1325376000
END = int(datetime.now(timezone.utc).timestamp())
LOOKBACK = 126
COSTS = [0.0010, 0.0025, 0.0050]


def yahoo(sym):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        f"?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read())
    result = payload["chart"]["result"][0]
    adjusted = (
        (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
        or result["indicators"]["quote"][0]["close"]
    )
    return {
        datetime.fromtimestamp(ts, timezone.utc).date().isoformat(): float(px)
        for ts, px in zip(result["timestamp"], adjusted)
        if px is not None
    }


def cagr(value, years):
    return value ** (1 / years) - 1


def maxdd(values):
    peak = values[0]
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    return drawdown


def run(cost):
    data = {symbol: yahoo(symbol) for symbol in SYMS}
    dates = sorted(set.intersection(*(set(series) for series in data.values())))
    equity = benchmark = smh = qqq = spy = 1.0
    previous = None
    curve = [1.0]
    daily = []
    switches = 0

    for index in range(LOOKBACK, len(dates) - 1):
        current, nxt = dates[index], dates[index + 1]
        dollar_return = data["UUP"][current] / data["UUP"][dates[index - LOOKBACK]] - 1
        state = "SMH" if dollar_return < 0 else "QQQ"
        returns = {
            symbol: data[symbol][nxt] / data[symbol][current] - 1
            for symbol in ["SMH", "QQQ", "SPY"]
        }
        switched = previous is not None and state != previous
        if switched:
            switches += 1
        strategy_return = returns[state] - (cost if switched else 0)
        equal_return = 0.5 * (returns["SMH"] + returns["QQQ"])
        equity *= 1 + strategy_return
        benchmark *= 1 + equal_return
        smh *= 1 + returns["SMH"]
        qqq *= 1 + returns["QQQ"]
        spy *= 1 + returns["SPY"]
        curve.append(equity)
        daily.append((nxt, strategy_return, equal_return))
        previous = state

    years = (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[LOOKBACK])).days / 365.25
    count = len(daily)
    chunk = count // 5
    fold_wins = 0
    for fold in range(5):
        strategy_value = benchmark_value = 1.0
        start = fold * chunk
        stop = count if fold == 4 else (fold + 1) * chunk
        for _, strategy_return, equal_return in daily[start:stop]:
            strategy_value *= 1 + strategy_return
            benchmark_value *= 1 + equal_return
        fold_wins += strategy_value > benchmark_value

    yearly = {}
    for date, strategy_return, equal_return in daily:
        bucket = yearly.setdefault(date[:4], [1.0, 1.0])
        bucket[0] *= 1 + strategy_return
        bucket[1] *= 1 + equal_return

    strategy_cagr = cagr(equity, years)
    equal_cagr = cagr(benchmark, years)
    return {
        "window_start": daily[0][0],
        "window_end": daily[-1][0],
        "sessions": count,
        "switches": switches,
        "strategy_cagr": strategy_cagr,
        "equal_smh_qqq_cagr": equal_cagr,
        "smh_cagr": cagr(smh, years),
        "qqq_cagr": cagr(qqq, years),
        "spy_cagr": cagr(spy, years),
        "strategy_max_dd": maxdd(curve),
        "excess_vs_equal_pp": 100 * (strategy_cagr - equal_cagr),
        "positive_equal_excess_folds": fold_wins,
        "positive_equal_excess_years": sum(a > b for a, b in yearly.values()),
        "represented_years": len(yearly),
    }


def main():
    results = {str(int(cost * 10000)): run(cost) for cost in COSTS}
    primary = results["25"]
    supported = (
        primary["excess_vs_equal_pp"] > 0
        and primary["positive_equal_excess_folds"] >= 3
        and results["50"]["excess_vs_equal_pp"] > 0
    )
    decision = "P22_DOLLAR_CYCLE_SUPPORTED" if supported else "P22_DOLLAR_CYCLE_NOT_SUPPORTED"
    output = {
        "schema": "p22.dollar_cycle_allocator.v1",
        "frozen_contract": {
            "signal": "UUP 126-session total return < 0",
            "allocation": "SMH when the US-dollar proxy is weakening, otherwise QQQ",
            "controls": ["SMH", "QQQ", "SPY", "equal SMH/QQQ"],
            "cost_bps_per_allocation_switch": [10, 25, 50],
            "support_gate": "positive CAGR excess vs equal SMH/QQQ at 25 and 50 bps plus >=3/5 positive chronological folds at 25 bps",
            "no_search": True,
        },
        "results": results,
        "decision": decision,
    }
    rendered = json.dumps(output, indent=2, sort_keys=True)
    print(rendered)
    with open("p22_dollar_cycle_result.json", "w", encoding="utf-8") as handle:
        handle.write(rendered + "\n")


if __name__ == "__main__":
    main()
