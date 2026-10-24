"""Post-outcome P249/P266 outlier-month fragility diagnostic.

Not a fresh scientific alpha test: worst-case month omission uses realized
returns and must not become a parameter, switch, or portfolio admission rule.
Uses the same frozen P249+P266 and common P249+BIL capital construction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from research import p249_orthogonal_sleeve_tournament_r1 as m

SCHEMA = "research.p249_p266_monthly_outlier_fragility_r1"
FIXED_REMOVALS = (0, 1, 3, 5)


def diagnose(core: pd.Series, p266: pd.Series, cash: pd.Series) -> dict:
    q = pd.concat(
        [core.rename("core"), p266.rename("p266"), cash.rename("cash")], axis=1
    ).loc["2021-01-01":"2026-08-31"].dropna()
    if len(q) < 48 or len(q) != len(q.index.unique()):
        raise ValueError("matched frozen monthly observations >=48 required")
    if q.index.max() > pd.Timestamp("2026-08-31") or q.index.min() < pd.Timestamp("2021-01-01"):
        raise ValueError("window source drift")
    candidate = m.mix_net(q["core"], q["p266"])
    cash_control = m.mix_net(q["core"], q["cash"])
    core_net = q["core"]
    # Omit the strongest positive monthly differences for P266 vs frozen core,
    # never alter source weights or choose which months to omit by model tuning.
    monthly_increment = candidate - core_net
    ordered = monthly_increment.sort_values(ascending=False, kind="stable")
    out = []
    for k in FIXED_REMOVALS:
        dropped = list(ordered.iloc[:k].index)
        kept = q.index.difference(pd.DatetimeIndex(dropped))
        primary = m.stats(candidate.loc[kept])
        base = m.stats(core_net.loc[kept])
        parked = m.stats(cash_control.loc[kept])
        out.append({
            "removed_best_increment_months": k,
            "removed_months": [t.date().isoformat() for t in dropped],
            "remaining_months": len(kept),
            "candidate_cagr_pct": round(100 * primary["cagr"], 5),
            "core_cagr_pct": round(100 * base["cagr"], 5),
            "matched_bil_control_cagr_pct": round(100 * parked["cagr"], 5),
            "incremental_vs_core_cagr_pp": round(100 * (primary["cagr"] - base["cagr"]), 5),
            "matched_excess_vs_bil_cagr_pp": round(100 * (primary["cagr"] - parked["cagr"]), 5),
            "candidate_max_drawdown": primary["max_drawdown"],
            "incremental_monthly_excess_sum_pp": round(100 * float(monthly_increment.loc[kept].sum()), 5),
        })
    return {
        "schema": SCHEMA,
        "science_stage": "RETROSPECTIVE_POST_OUTCOME_FRAGILITY_ONLY",
        "frozen_capital": {"core": .75, "p266": .25, "bil_control": .25, "source_cutoff": "2026-08-31"},
        "baseline_months": len(q),
        "cohorts": out,
        "interpretation_boundary": [
            "All removed months are selected using realized candidate-core excess; NOT a tradable forward exclusion rule",
            "Keep identical omitted calendar dates for core, P266 candidate and BIL control",
            "End-point transaction costs are applied by existing frozen stats to each common retained window",
            "No model re-fit, weight search, strategy activation, or broker authority",
        ],
        "allocation_authority": False,
        "live_trading_change": False,
    }


def main():
    import yfinance as yf
    a = argparse.ArgumentParser()
    a.add_argument("--output", type=Path, required=True)
    args = a.parse_args()
    tickers = list(dict.fromkeys(list(m.CORE_SYMBOLS) + m.SIMPLE_CANDIDATES + [m.CASH]))
    raw = yf.download(tickers, start=m.START_DOWNLOAD, end=m.END, auto_adjust=True, progress=False, threads=False)
    if raw is None or raw.empty:
        raise SystemExit("SOURCE_FAILURE_EMPTY")
    close = (raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw).reindex(columns=tickers).dropna(how="all").astype(float)
    core, p266, _ = m.build_core_and_p266_monthly(close)
    simple = close[m.SIMPLE_CANDIDATES + [m.CASH]].resample("ME").last().pct_change(fill_method=None)
    result = diagnose(core, p266, simple[m.CASH])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
