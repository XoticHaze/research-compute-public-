#!/usr/bin/env python3
"""Frozen P23 first-child discriminator: VIX term structure as semiconductor risk-state."""
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SYMS = ["^VIX", "^VIX3M", "SMH", "QQQ", "SPY"]
START = 1230768000  # 2009-01-01; common window determined from returned data.
END = int(datetime.now(timezone.utc).timestamp())
COSTS = [0.0010, 0.0025, 0.0050]


def yahoo(sym):
    encoded = urllib.parse.quote(sym, safe="")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
           f"?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read())
    result = payload["chart"]["result"][0]
    adjusted = ((result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
                or result["indicators"]["quote"][0]["close"])
    return {datetime.fromtimestamp(ts, timezone.utc).date().isoformat(): float(px)
            for ts, px in zip(result["timestamp"], adjusted) if px is not None}


def cagr(value, years):
    return value ** (1 / years) - 1


def maxdd(values):
    peak = values[0]
    dd = 0.0
    for value in values:
        peak = max(peak, value)
        dd = min(dd, value / peak - 1)
    return dd


def run(cost, data, dates):
    equity = equal = smh = qqq = spy = 1.0
    previous = None
    curve = [1.0]
    daily = []
    switches = 0
    # Use today's closing term-structure observation only for next-session return.
    for i in range(len(dates) - 1):
        current, nxt = dates[i], dates[i + 1]
        contango = data["^VIX"][current] < data["^VIX3M"][current]
        state = "SMH" if contango else "QQQ"
        returns = {s: data[s][nxt] / data[s][current] - 1 for s in ["SMH", "QQQ", "SPY"]}
        switched = previous is not None and state != previous
        switches += int(switched)
        sr = returns[state] - (cost if switched else 0.0)
        er = 0.5 * (returns["SMH"] + returns["QQQ"])
        equity *= 1 + sr
        equal *= 1 + er
        smh *= 1 + returns["SMH"]
        qqq *= 1 + returns["QQQ"]
        spy *= 1 + returns["SPY"]
        curve.append(equity)
        daily.append((nxt, sr, er))
        previous = state
    years = (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).days / 365.25
    n = len(daily)
    chunk = n // 5
    fold_wins = 0
    for fold in range(5):
        a = b = 1.0
        lo = fold * chunk
        hi = n if fold == 4 else (fold + 1) * chunk
        for _, sr, er in daily[lo:hi]:
            a *= 1 + sr
            b *= 1 + er
        fold_wins += a > b
    yearly = {}
    for date, sr, er in daily:
        bucket = yearly.setdefault(date[:4], [1.0, 1.0])
        bucket[0] *= 1 + sr
        bucket[1] *= 1 + er
    sc = cagr(equity, years)
    ec = cagr(equal, years)
    return {"window_start": daily[0][0], "window_end": daily[-1][0], "sessions": n,
            "switches": switches, "strategy_cagr": sc, "equal_smh_qqq_cagr": ec,
            "smh_cagr": cagr(smh, years), "qqq_cagr": cagr(qqq, years),
            "spy_cagr": cagr(spy, years), "strategy_max_dd": maxdd(curve),
            "excess_vs_equal_pp": 100 * (sc - ec), "positive_equal_excess_folds": fold_wins,
            "positive_equal_excess_years": sum(a > b for a, b in yearly.values()),
            "represented_years": len(yearly)}


def main():
    data = {s: yahoo(s) for s in SYMS}
    dates = sorted(set.intersection(*(set(v) for v in data.values())))
    if len(dates) < 1000:
        raise RuntimeError(f"insufficient exact common window: {len(dates)} sessions")
    results = {str(int(c * 10000)): run(c, data, dates) for c in COSTS}
    primary = results["25"]
    supported = (primary["excess_vs_equal_pp"] > 0 and primary["positive_equal_excess_folds"] >= 3
                 and results["50"]["excess_vs_equal_pp"] > 0)
    output = {"schema": "p23.vix_term_structure_allocator.v1",
              "frozen_contract": {"signal": "CBOE VIX close < CBOE VIX3M close (contango)",
                  "causality": "close-observed state applies only to next-session return",
                  "allocation": "SMH in contango, otherwise QQQ",
                  "controls": ["SMH", "QQQ", "SPY", "equal SMH/QQQ"],
                  "cost_bps_per_allocation_switch": [10, 25, 50],
                  "support_gate": "positive CAGR excess vs equal SMH/QQQ at 25 and 50 bps plus >=3/5 positive chronological folds at 25 bps",
                  "no_search": True},
              "results": results,
              "decision": "P23_VIX_TERM_STRUCTURE_SUPPORTED" if supported else "P23_VIX_TERM_STRUCTURE_NOT_SUPPORTED"}
    rendered = json.dumps(output, indent=2, sort_keys=True)
    print(rendered)
    with open("p23_vix_term_structure_result.json", "w", encoding="utf-8") as f:
        f.write(rendered + "\n")


if __name__ == "__main__":
    main()
