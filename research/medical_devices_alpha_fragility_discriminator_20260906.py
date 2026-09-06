from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = {
    "medical_devices": {
        "primary_industry_etf": "IHI",
        "development_universe": ["ISRG", "ABT", "MDT", "SYK", "BSX", "EW", "BDX", "RMD"],
    }
}
CUTOFF = "2026-09-01T13:30:00+00:00"
EXPECTED = {
    "states": 9737,
    "stock_net25_mean_bps": 94.3369216641737,
    "ihi_excess25_mean_bps": 7.18340291329859,
    "passing_symbols": 4,
}
COSTS = (25.0, 50.0, 75.0, 100.0)


def _load_runner(path: Path):
    spec = importlib.util.spec_from_file_location("stagea_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load pinned Stage-A runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mean(records: list[dict], key: str) -> float:
    if not records:
        raise RuntimeError("empty record population")
    return float(np.mean([float(row[key]) for row in records]))


def evaluate(runner_path: Path) -> dict:
    r = _load_runner(runner_path)
    cutoff = pd.Timestamp(CUTOFF)
    symbols = tuple(FAMILY["medical_devices"]["development_universe"])
    selection_symbols = (*r.TRAIN, *symbols, "QQQ")

    raw = {symbol: r._bounded(symbol, cutoff) for symbol in selection_symbols}
    common_sets = [set(frame.timestamp) for frame in raw.values()]
    calendar = pd.DatetimeIndex(sorted(set.intersection(*common_sets)))
    if len(calendar) < 1500 or calendar[-1] != cutoff:
        raise RuntimeError("frozen common calendar failed")
    prices = {
        symbol: raw[symbol].set_index("timestamp").price.reindex(calendar)
        for symbol in raw
    }
    if any(series.isna().any() for series in prices.values()):
        raise RuntimeError("missing prices on frozen common calendar")

    ihi = r._bounded("IHI", cutoff).set_index("timestamp").price.reindex(calendar)
    if ihi.isna().any():
        raise RuntimeError("IHI missing rows on frozen common calendar")

    modeled = (*r.TRAIN, *symbols)
    data = r._engineer(prices, calendar, modeled)
    folds = r._global_folds(len(calendar))
    train_states = r._state_frame(r.TRAIN, data, folds)
    test_states = r._state_frame(symbols, data, folds)

    records: list[dict] = []
    per_symbol_gate: dict[str, bool] = {}
    for symbol in symbols:
        symbol_records: list[dict] = []
        positive_net_folds = 0
        positive_ihi_folds = 0
        for fold in range(r.EVAL_FIRST_FOLD, r.FOLDS + 1):
            start, _ = folds[fold - 1]
            train = train_states[train_states.signal_i < start - r.PURGE]
            test = test_states[(test_states.symbol == symbol) & (test_states.fold == fold)]
            model = r._fit(train)
            prediction = model.predict(test[r.FEATURES].to_numpy(float))
            chosen = test.loc[prediction > 0].copy()
            prior = data[symbol].iloc[: start - r.PURGE].mom20.dropna()
            threshold = float(prior.quantile(1.0 - r.TAIL))
            primary = chosen.loc[chosen.mom20 < threshold]

            fold_records: list[dict] = []
            for row in primary.itertuples(index=False):
                signal_i = int(row.signal_i)
                entry_i = signal_i + r.DELAY
                exit_i = entry_i + r.HOLD
                stock_gross = float(prices[symbol].iloc[exit_i] / prices[symbol].iloc[entry_i] - 1.0) * 10000.0
                ihi_gross = float(ihi.iloc[exit_i] / ihi.iloc[entry_i] - 1.0) * 10000.0
                qqq_gross = float(prices["QQQ"].iloc[exit_i] / prices["QQQ"].iloc[entry_i] - 1.0) * 10000.0
                rec = {
                    "symbol": symbol,
                    "fold": fold,
                    "signal_date": calendar[signal_i].isoformat(),
                    "entry_date": calendar[entry_i].isoformat(),
                    "exit_date": calendar[exit_i].isoformat(),
                    "stock_gross_bps": stock_gross,
                    "ihi_gross_bps": ihi_gross,
                    "qqq_gross_bps": qqq_gross,
                    "stock_net25_bps": stock_gross - 25.0,
                    "ihi_excess25_bps": stock_gross - 25.0 - ihi_gross,
                    "qqq_excess25_bps": stock_gross - 25.0 - qqq_gross,
                }
                fold_records.append(rec)
                symbol_records.append(rec)
                records.append(rec)
            if fold_records:
                if _mean(fold_records, "stock_net25_bps") > 0:
                    positive_net_folds += 1
                if _mean(fold_records, "ihi_excess25_bps") > 0:
                    positive_ihi_folds += 1

        symbol_net = _mean(symbol_records, "stock_net25_bps")
        symbol_ihi = _mean(symbol_records, "ihi_excess25_bps")
        per_symbol_gate[symbol] = bool(
            len(symbol_records) >= 20
            and symbol_net > 0
            and symbol_ihi > 0
            and positive_net_folds >= 3
            and positive_ihi_folds >= 3
        )

    passing_symbols = sum(int(value) for value in per_symbol_gate.values())
    aggregate_net25 = _mean(records, "stock_net25_bps")
    aggregate_ihi25 = _mean(records, "ihi_excess25_bps")
    if len(records) != EXPECTED["states"]:
        raise RuntimeError(f"Stage-A state parity failed: {len(records)} != {EXPECTED['states']}")
    if abs(aggregate_net25 - EXPECTED["stock_net25_mean_bps"]) > 1e-9:
        raise RuntimeError("Stage-A net25 parity failed")
    if abs(aggregate_ihi25 - EXPECTED["ihi_excess25_mean_bps"]) > 1e-9:
        raise RuntimeError("Stage-A IHI-excess parity failed")
    if passing_symbols != EXPECTED["passing_symbols"]:
        raise RuntimeError("Stage-A passing-symbol parity failed")

    cost_grid = []
    for cost in COSTS:
        stock_net = float(np.mean([row["stock_gross_bps"] - cost for row in records]))
        ihi_excess = float(np.mean([row["stock_gross_bps"] - cost - row["ihi_gross_bps"] for row in records]))
        qqq_excess = float(np.mean([row["stock_gross_bps"] - cost - row["qqq_gross_bps"] for row in records]))
        cost_grid.append({
            "round_trip_stock_cost_bps": cost,
            "candidate_net_mean_bps": stock_net,
            "matched_ihi_excess_mean_bps": ihi_excess,
            "matched_qqq_excess_mean_bps": qqq_excess,
        })

    loo_symbols = []
    for symbol in symbols:
        kept = [row for row in records if row["symbol"] != symbol]
        loo_symbols.append({
            "excluded_symbol": symbol,
            "remaining_states": len(kept),
            "matched_ihi_excess25_mean_bps": _mean(kept, "ihi_excess25_bps"),
            "matched_qqq_excess25_mean_bps": _mean(kept, "qqq_excess25_bps"),
        })

    loo_folds = []
    for fold in range(r.EVAL_FIRST_FOLD, r.FOLDS + 1):
        kept = [row for row in records if row["fold"] != fold]
        loo_folds.append({
            "excluded_fold": fold,
            "remaining_states": len(kept),
            "matched_ihi_excess25_mean_bps": _mean(kept, "ihi_excess25_bps"),
            "matched_qqq_excess25_mean_bps": _mean(kept, "qqq_excess25_bps"),
        })

    contributions = []
    positive_total = 0.0
    raw_contrib: dict[str, float] = {}
    for symbol in symbols:
        contribution = float(sum(row["ihi_excess25_bps"] for row in records if row["symbol"] == symbol))
        raw_contrib[symbol] = contribution
        if contribution > 0:
            positive_total += contribution
    for symbol in symbols:
        contribution = raw_contrib[symbol]
        contributions.append({
            "symbol": symbol,
            "matched_ihi_excess25_sum_bps": contribution,
            "share_of_positive_ihi_contribution": (contribution / positive_total if contribution > 0 and positive_total > 0 else 0.0),
        })

    first_entry = min(row["entry_date"] for row in records)
    last_exit = max(row["exit_date"] for row in records)
    break_even_ihi = 25.0 + aggregate_ihi25
    aggregate_qqq25 = _mean(records, "qqq_excess25_bps")
    break_even_qqq = 25.0 + aggregate_qqq25
    worst_symbol_loo = min(row["matched_ihi_excess25_mean_bps"] for row in loo_symbols)
    worst_fold_loo = min(row["matched_ihi_excess25_mean_bps"] for row in loo_folds)
    max_positive_share = max(row["share_of_positive_ihi_contribution"] for row in contributions)

    cost_fragile = break_even_ihi < 50.0
    concentration_fragile = worst_symbol_loo <= 0.0 or max_positive_share > 0.50
    temporal_fragile = worst_fold_loo <= 0.0
    if cost_fragile and (concentration_fragile or temporal_fragile):
        decision = "PARK_GENERIC_MEDICAL_DEVICE_TRANSPORT_FRAGILE"
    elif cost_fragile:
        decision = "MEDICAL_DEVICE_MATCHED_IHI_ALPHA_COST_FRAGILE"
    elif concentration_fragile or temporal_fragile:
        decision = "MEDICAL_DEVICE_MATCHED_IHI_ALPHA_DEPENDENCY_FRAGILE"
    else:
        decision = "MEDICAL_DEVICE_ALPHA_ROBUST_ENOUGH_FOR_NEW_ARCHITECTURE"

    return {
        "schema": "research_compute_public.medical_devices_alpha_fragility.v1",
        "research_only": True,
        "external_holdouts_loaded": False,
        "promotion_authority": False,
        "allocation_authority": False,
        "runtime_authority": False,
        "broker_authority": False,
        "live_trading_change": False,
        "scientific_parent": "Medical Devices generic Stage-A opportunity transport",
        "frozen_family": FAMILY["medical_devices"],
        "selection_window": {
            "calendar_first": calendar[0].isoformat(),
            "calendar_last": calendar[-1].isoformat(),
            "first_selected_entry": first_entry,
            "last_selected_exit": last_exit,
            "states": len(records),
        },
        "parity": {
            "status": "EXACT",
            "candidate_net25_mean_bps": aggregate_net25,
            "matched_ihi_excess25_mean_bps": aggregate_ihi25,
            "passing_symbols": passing_symbols,
        },
        "cost_grid": cost_grid,
        "break_even_round_trip_cost_bps": {
            "versus_matched_ihi": break_even_ihi,
            "versus_matched_qqq": break_even_qqq,
        },
        "leave_one_symbol_out": loo_symbols,
        "leave_one_fold_out": loo_folds,
        "symbol_contributions": contributions,
        "diagnostics": {
            "worst_leave_one_symbol_out_ihi_excess25_mean_bps": worst_symbol_loo,
            "worst_leave_one_fold_out_ihi_excess25_mean_bps": worst_fold_loo,
            "max_positive_ihi_contribution_share": max_positive_share,
            "cost_fragile_before_50bps": cost_fragile,
            "symbol_concentration_fragile": concentration_fragile,
            "temporal_fragile": temporal_fragile,
        },
        "decision": decision,
        "consequence": "Do not open Medical Devices external holdouts or threshold-rescue this generic transport. A future revisit must use a genuinely different prospectively frozen mechanism and beat matched IHI and broad-market baselines on exact windows after realistic costs.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(args.runner)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("MEDICAL_DEVICES_ALPHA_FRAGILITY=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
