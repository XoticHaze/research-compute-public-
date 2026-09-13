#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

HOLD = 5
COST_BPS = 10.0
RECENT_YEAR = 2015
SOURCE_ARTIFACT_ID = 10294324888
PARENTS = [
    "F1B-CROSSROOT-DATED-CORPUS-RELEASE",
    "SLP-20260913-NQ-DATED-TREND-TRANSPORT-R1",
    "SLP-20260913-ES-DATED-TREND-TRANSPORT-R1",
    "SLP-20260913-6E-DATED-TREND-CASH-SUFFICIENCY-R1",
]


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def contract_month(path: Path) -> str:
    return path.parent.name.split("-", 1)[1]


def parse_day(text: str) -> date:
    return date.fromisoformat(text[:10])


def load_contract(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                d = parse_day(row["timestamp"])
                close = float(row["close"])
                volume = float(row["volume"])
                oi = float(row["open_interest"])
            except Exception:
                continue
            if math.isfinite(close) and close > 0 and volume > 0 and oi > 0:
                rows.append((d, close))
    rows.sort(key=lambda x: x[0])
    return rows


def summary(events):
    if not events:
        return {}
    sr = [x["strategy_return_after_cost"] for x in events]
    br = [x["matched_long_return_after_cost"] for x in events]
    ex = [x["excess_return"] for x in events]
    return {
        "n": len(events),
        "mean_strategy_return_pct": 100 * mean(sr),
        "median_strategy_return_pct": 100 * statistics.median(sr),
        "positive_strategy_fraction": sum(x > 0 for x in sr) / len(sr),
        "mean_matched_long_return_pct": 100 * mean(br),
        "mean_excess_return_pct": 100 * mean(ex),
        "median_excess_return_pct": 100 * statistics.median(ex),
        "positive_excess_fraction": sum(x > 0 for x in ex) / len(ex),
    }


def build_events(root: str, staging: Path):
    files = sorted(staging.glob(f"**/{root}-*/1Day.csv"))
    if not files:
        raise RuntimeError(f"no released {root} dated-contract files found")

    by_contract = {}
    idx_by_contract = {}
    active_on_day = defaultdict(list)
    for path in files:
        cm = contract_month(path)
        rows = load_contract(path)
        if not rows:
            continue
        by_contract[cm] = rows
        idx_by_contract[cm] = {d: i for i, (d, _c) in enumerate(rows)}
        for d, close in rows:
            active_on_day[d].append((cm, close))

    events = []
    last_exit = None
    for signal_day in sorted(active_on_day):
        if last_exit is not None and signal_day <= last_exit:
            continue
        ym = signal_day.strftime("%Y%m")
        curve = sorted((cm, close) for cm, close in active_on_day[signal_day] if cm >= ym)
        if len(curve) < 2:
            continue
        near_cm, near_close = curve[0]
        deferred_cm, deferred_close = curve[1]
        if near_close <= 0 or deferred_close <= 0 or near_close == deferred_close:
            continue
        rows = by_contract[near_cm]
        signal_idx = idx_by_contract[near_cm].get(signal_day)
        if signal_idx is None:
            continue
        entry_idx = signal_idx + 1
        exit_idx = entry_idx + HOLD
        if exit_idx >= len(rows):
            continue
        entry_day, entry_close = rows[entry_idx]
        exit_day, exit_close = rows[exit_idx]
        if not (signal_day < entry_day < exit_day):
            continue

        # Frozen economic hypothesis: backwardation -> long near; contango -> short near.
        # Signal uses signal-close information, but execution starts at the next active close.
        position = 1 if near_close > deferred_close else -1
        fwd = exit_close / entry_close - 1.0
        cost = COST_BPS / 10000.0
        strategy = position * fwd - cost
        matched_long = fwd - cost
        events.append({
            "signal_date": signal_day.isoformat(),
            "entry_date": entry_day.isoformat(),
            "exit_date": exit_day.isoformat(),
            "signal_year": signal_day.year,
            "near_contract": near_cm,
            "deferred_contract": deferred_cm,
            "curve_spread_pct": 100 * (near_close / deferred_close - 1.0),
            "position": position,
            "strategy_return_after_cost": strategy,
            "matched_long_return_after_cost": matched_long,
            "excess_return": strategy - matched_long,
        })
        last_exit = exit_day
    return files, events


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", choices=["NG", "ZS"], required=True)
    ap.add_argument("--staging", type=Path, default=Path("input/staging"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    root = args.root
    files, events = build_events(root, args.staging)
    recent = [e for e in events if e["signal_year"] >= RECENT_YEAR]
    full = summary(events)
    rec = summary(recent)

    by_contract = defaultdict(list)
    by_year = defaultdict(list)
    for e in events:
        by_contract[e["near_contract"]].append(e)
        by_year[e["signal_year"]].append(e)
    contract_stats = {k: summary(v) for k, v in sorted(by_contract.items())}
    year_stats = {str(k): summary(v) for k, v in sorted(by_year.items())}
    positive_contract_fraction = (
        sum(v.get("mean_strategy_return_pct", -999) > 0 for v in contract_stats.values()) / len(contract_stats)
        if contract_stats else 0.0
    )
    positive_year_fraction = (
        sum(v.get("mean_strategy_return_pct", -999) > 0 for v in year_stats.values()) / len(year_stats)
        if year_stats else 0.0
    )

    loo = {}
    for year in sorted(by_year):
        s = summary([e for e in events if e["signal_year"] != year])
        loo[str(year)] = {
            "mean_strategy_return_pct": s.get("mean_strategy_return_pct"),
            "mean_excess_return_pct": s.get("mean_excess_return_pct"),
        }
    loo_values = list(loo.values())
    loo_positive = bool(loo_values) and all(
        x.get("mean_strategy_return_pct", -999) > 0 and x.get("mean_excess_return_pct", -999) > 0
        for x in loo_values
    )

    gates = {
        "minimum_event_count": len(events) >= 250,
        "full_absolute_expectancy_positive": full.get("mean_strategy_return_pct", -999) > 0,
        "full_matched_excess_positive": full.get("mean_excess_return_pct", -999) > 0,
        "recent_absolute_expectancy_positive": rec.get("mean_strategy_return_pct", -999) > 0,
        "recent_matched_excess_positive": rec.get("mean_excess_return_pct", -999) > 0,
        "majority_contracts_positive_absolute": positive_contract_fraction > 0.5,
        "majority_signal_years_positive_absolute": positive_year_fraction > 0.5,
        "all_leave_one_signal_year_out_absolute_and_excess_positive": loo_positive,
    }
    survives = all(gates.values())
    experiment_id = f"{root}-DATED-CURVE-CARRY-TRANSPORT-R1"
    result = {
        "schema": "public.dated_curve_carry_transport_r1.v1",
        "experiment_id": experiment_id,
        "inherited_learning_ids": PARENTS,
        "uncertainty_resolved": "whether a chronology-safe raw near/deferred curve-state mechanism has positive absolute and matched after-cost expectancy in an untested physical-commodity dated-contract root",
        "claim_tested": "At each admissible dated-contract curve observation, backwardation (near close > next-deferred close) predicts positive next-session-entered near-contract returns and contango predicts negative returns over the next five active sessions, after 10 bp normalized round-trip cost, with positive cash sufficiency and excess over an always-long same-contract opportunity.",
        "root": root,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "design": {
            "signal": "sign(near_close / next_deferred_close - 1): backwardation=long, contango=short",
            "information_time": "signal session close",
            "earliest_execution": "next active session close in the selected near contract",
            "hold_active_sessions_after_entry": HOLD,
            "normalized_round_trip_cost_bps": COST_BPS,
            "active_row_filter": "volume>0 and open_interest>0",
            "near_deferred_selection": "two earliest active contract months not earlier than signal YYYYMM",
            "sampling": "single-capital non-overlapping events; next signal strictly after prior exit",
            "cash_control": "zero return before normalized strategy cost",
            "matched_control": "always-long same near contract / same entry-exit windows / same normalized cost",
            "recent_signal_year_gte": RECENT_YEAR,
            "continuous_series_constructed": False,
            "roll_cutoff_selected": False,
            "back_adjustment": False,
        },
        "contract_files_seen": len(files),
        "events": len(events),
        "full": full,
        "recent": rec,
        "backwardation_fraction": (sum(e["position"] > 0 for e in events) / len(events)) if events else None,
        "positive_contract_fraction_absolute": positive_contract_fraction,
        "positive_signal_year_fraction_absolute": positive_year_fraction,
        "signal_year_stats": year_stats,
        "leave_one_signal_year_out": loo,
        "gates": gates,
        "survives_transport": survives,
        "decision": "SURVIVES_TRANSPORT" if survives else "REJECT_NO_PARAMETER_RESCUE",
        "forbidden_parameter_rescue": [
            "curve threshold tuning",
            "holding-period change",
            "cost reduction",
            "same-close execution",
            "exclude bad years",
            "select favorable delivery months",
            "volume/open-interest threshold tuning",
            "switching to a continuous/back-adjusted series",
        ],
        "authority": "SCIENTIFIC_EVIDENCE_ONLY",
        "portfolio_allocation_authority": False,
        "strategy_spec_mutation": False,
        "runtime_authority_change": False,
        "broker_submission": False,
        "live_trading_change": False,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
