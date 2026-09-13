#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

ROOT = "ES"
LOOKBACK = 20
HOLD = 5
COST_BPS = 10.0
RECENT_YEAR = 2015
SOURCE_ARTIFACT_ID = 10294324888
LEARNING_PARENTS = ["F1B-CROSSROOT-DATED-CORPUS-RELEASE", "SLP-20260913-NQ-DATED-TREND-TRANSPORT-R1"]
EXPERIMENT_ID = "ES-DATED-TREND-TRANSPORT-R1"


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def pct(x):
    return 100.0 * x


def load_contract(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                close = float(r["close"])
                volume = float(r["volume"])
                oi = float(r["open_interest"])
            except Exception:
                continue
            if not math.isfinite(close) or close <= 0 or volume <= 0 or oi <= 0:
                continue
            rows.append((r["timestamp"], close))
    rows.sort()
    return rows


def contract_month(path: Path):
    return path.parent.name.split("-", 1)[1]


def build_events(path: Path):
    month = contract_month(path)
    year = int(month[:4])
    rows = load_contract(path)
    out = []
    i = LOOKBACK
    while i + HOLD < len(rows):
        past = rows[i][1] / rows[i - LOOKBACK][1] - 1.0
        fwd = rows[i + HOLD][1] / rows[i][1] - 1.0
        pos = 1.0 if past > 0 else (-1.0 if past < 0 else 0.0)
        cost = COST_BPS / 10000.0 if pos != 0 else 0.0
        strat = pos * fwd - cost
        baseline = fwd - COST_BPS / 10000.0
        out.append({
            "contract_month": month,
            "contract_year": year,
            "signal_date": rows[i][0],
            "exit_date": rows[i + HOLD][0],
            "past_return": past,
            "forward_return": fwd,
            "position": int(pos),
            "strategy_return_after_cost": strat,
            "matched_long_return_after_cost": baseline,
            "excess_return": strat - baseline,
        })
        i += HOLD
    return out


def summarize(events):
    if not events:
        return {}
    ex = [e["excess_return"] for e in events]
    sr = [e["strategy_return_after_cost"] for e in events]
    br = [e["matched_long_return_after_cost"] for e in events]
    return {
        "n": len(events),
        "mean_strategy_return_pct": pct(mean(sr)),
        "mean_matched_long_return_pct": pct(mean(br)),
        "mean_excess_return_pct": pct(mean(ex)),
        "median_excess_return_pct": pct(statistics.median(ex)),
        "positive_excess_fraction": sum(x > 0 for x in ex) / len(ex),
    }


def main():
    files = sorted(Path("input/staging").glob("**/ES-*/1Day.csv"))
    if not files:
        raise RuntimeError("no released ES dated-contract files found")

    all_events = []
    per_contract = {}
    for p in files:
        ev = build_events(p)
        if ev:
            per_contract[contract_month(p)] = summarize(ev)
            all_events.extend(ev)

    recent = [e for e in all_events if e["contract_year"] >= RECENT_YEAR]
    contract_excess = {m: v["mean_excess_return_pct"] for m, v in per_contract.items()}
    positive_contract_fraction = sum(v > 0 for v in contract_excess.values()) / len(contract_excess) if contract_excess else 0.0

    years = sorted(set(e["contract_year"] for e in all_events))
    loo = {}
    for y in years:
        subset = [e for e in all_events if e["contract_year"] != y]
        loo[str(y)] = summarize(subset).get("mean_excess_return_pct")
    loo_vals = [v for v in loo.values() if v is not None and math.isfinite(v)]

    full = summarize(all_events)
    rec = summarize(recent)
    gates = {
        "full_mean_excess_positive": full.get("mean_excess_return_pct", -999) > 0,
        "recent_mean_excess_positive": rec.get("mean_excess_return_pct", -999) > 0,
        "majority_contracts_positive": positive_contract_fraction > 0.5,
        "all_leave_one_year_out_positive": bool(loo_vals) and min(loo_vals) > 0,
        "minimum_event_count": len(all_events) >= 250,
    }
    survives = all(gates.values())

    result = {
        "schema": "public.es_dated_trend_transport_r1.v1",
        "experiment_id": EXPERIMENT_ID,
        "inherited_learning_ids": LEARNING_PARENTS,
        "uncertainty_resolved": "whether the rejected NQ simple dated-contract trend representation transports differently to the nearest broad equity-index futures sibling",
        "claim_tested": "The identical frozen 20-active-session trend sign predicts the next 5 active sessions across independently released ES dated contracts and beats an always-long matched opportunity after a 10 bp normalized round-trip cost without constructing a continuous series.",
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "root": ROOT,
        "design": {
            "lookback_active_sessions": LOOKBACK,
            "hold_active_sessions": HOLD,
            "normalized_round_trip_cost_bps": COST_BPS,
            "active_row_filter": "volume>0 and open_interest>0",
            "sampling": "non-overlapping within each dated contract",
            "continuous_series_constructed": False,
            "roll_cutoff_selected": False,
            "back_adjustment": False,
            "matched_control": "always-long same contract/same decision windows/same normalized cost",
            "recent_contract_year_gte": RECENT_YEAR,
        },
        "contract_files_seen": len(files),
        "contracts_with_events": len(per_contract),
        "full": full,
        "recent": rec,
        "positive_contract_fraction": positive_contract_fraction,
        "leave_one_contract_year_out_mean_excess_pct": loo,
        "gates": gates,
        "survives_transport": survives,
        "decision": "SURVIVES_TRANSPORT" if survives else "REJECT_NO_PARAMETER_RESCUE",
        "forbidden_parameter_rescue": ["lookback change", "holding-period change", "cost reduction", "exclude bad contract years", "volume/open-interest threshold tuning", "select only favorable contract months"],
        "authority": "SCIENTIFIC_EVIDENCE_ONLY",
        "portfolio_allocation_authority": False,
        "strategy_spec_mutation": False,
        "runtime_authority_change": False,
        "broker_submission": False,
        "live_trading_change": False
    }
    Path("es-dated-trend-transport-r1-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
