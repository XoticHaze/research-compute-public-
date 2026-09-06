from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = {
    "utilities": {
        "primary_industry_etf": "XLU",
        "development_universe": ["NEE", "SO", "DUK", "AEP", "EXC", "SRE", "XEL", "ED"],
    }
}
CUTOFF = "2026-09-01T13:30:00+00:00"
COSTS = (25.0, 50.0, 75.0, 100.0)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("utilities_stagea_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load pinned Stage-A runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mean(rows: list[dict], key: str) -> float:
    if not rows:
        raise RuntimeError("empty event population")
    return float(np.mean([float(row[key]) for row in rows]))


def evaluate(runner_path: Path) -> dict:
    r = _load(runner_path)
    parent = r._evaluate_matrix(FAMILY, CUTOFF)
    parent_summary = parent["family_summary"]["utilities"]
    parent_rows = {row["symbol"]: row for row in parent["per_symbol"] if row["family"] == "utilities"}

    cutoff = pd.Timestamp(CUTOFF)
    symbols = tuple(FAMILY["utilities"]["development_universe"])
    selection_symbols = (*r.TRAIN, *symbols, "QQQ")
    raw = {symbol: r._bounded(symbol, cutoff) for symbol in selection_symbols}
    calendar = pd.DatetimeIndex(sorted(set.intersection(*[set(frame.timestamp) for frame in raw.values()])))
    if calendar.empty or calendar[-1] != cutoff:
        raise RuntimeError("selection calendar cutoff mismatch")
    prices = {symbol: raw[symbol].set_index("timestamp").price.reindex(calendar) for symbol in raw}
    if any(series.isna().any() for series in prices.values()):
        raise RuntimeError("selection price gap")

    xlu = r._bounded("XLU", cutoff).set_index("timestamp").price.reindex(calendar)
    if xlu.isna().any():
        raise RuntimeError("XLU missing on frozen selection calendar")

    modeled = (*r.TRAIN, *symbols)
    data = r._engineer(prices, calendar, modeled)
    folds = r._global_folds(len(calendar))
    train_states = r._state_frame(r.TRAIN, data, folds)
    test_states = r._state_frame(symbols, data, folds)

    events: list[dict] = []
    per_symbol: list[dict] = []
    for symbol in symbols:
        symbol_events: list[dict] = []
        fold_stats: list[dict] = []
        for fold in range(r.EVAL_FIRST_FOLD, r.FOLDS + 1):
            start, _ = folds[fold - 1]
            train = train_states[train_states.signal_i < start - r.PURGE]
            test = test_states[(test_states.symbol == symbol) & (test_states.fold == fold)]
            if len(train) < 1000:
                raise RuntimeError(f"{symbol} fold {fold}: insufficient training rows={len(train)}")
            model = r._fit(train)
            prediction = model.predict(test[r.FEATURES].to_numpy(float))
            chosen = test.loc[prediction > 0].copy()
            prior = data[symbol].iloc[: start - r.PURGE].mom20.dropna()
            if len(prior) < 250:
                raise RuntimeError(f"{symbol} fold {fold}: insufficient threshold support")
            threshold = float(prior.quantile(1.0 - r.TAIL))
            primary = chosen.loc[chosen.mom20 < threshold]

            fold_events: list[dict] = []
            for row in primary.itertuples(index=False):
                signal_i = int(row.signal_i)
                entry_i = signal_i + r.DELAY
                exit_i = entry_i + r.HOLD
                stock_gross = float(prices[symbol].iloc[exit_i] / prices[symbol].iloc[entry_i] - 1.0) * 10000.0
                xlu_gross = float(xlu.iloc[exit_i] / xlu.iloc[entry_i] - 1.0) * 10000.0
                qqq_gross = float(prices["QQQ"].iloc[exit_i] / prices["QQQ"].iloc[entry_i] - 1.0) * 10000.0
                event = {
                    "symbol": symbol,
                    "fold": fold,
                    "signal_date": calendar[signal_i].isoformat(),
                    "entry_date": calendar[entry_i].isoformat(),
                    "exit_date": calendar[exit_i].isoformat(),
                    "stock_gross_bps": stock_gross,
                    "xlu_gross_bps": xlu_gross,
                    "qqq_gross_bps": qqq_gross,
                    "stock_net25_bps": stock_gross - 25.0,
                    "xlu_excess25_bps": stock_gross - 25.0 - xlu_gross,
                    "qqq_excess25_bps": stock_gross - 25.0 - qqq_gross,
                }
                fold_events.append(event)
                symbol_events.append(event)
                events.append(event)
            fold_stats.append({
                "fold": fold,
                "states": len(fold_events),
                "candidate_net25_mean_bps": None if not fold_events else _mean(fold_events, "stock_net25_bps"),
                "matched_xlu_excess25_mean_bps": None if not fold_events else _mean(fold_events, "xlu_excess25_bps"),
                "matched_qqq_excess25_mean_bps": None if not fold_events else _mean(fold_events, "qqq_excess25_bps"),
            })

        parent_symbol = parent_rows[symbol]
        reconstructed_net = _mean(symbol_events, "stock_net25_bps")
        reconstructed_xlu = _mean(symbol_events, "xlu_excess25_bps")
        if len(symbol_events) != int(parent_symbol["primary_states"]):
            raise RuntimeError(f"{symbol}: state-count reconstruction mismatch")
        if abs(reconstructed_net - float(parent_symbol["stock_net25_mean_bps"])) > 1e-8:
            raise RuntimeError(f"{symbol}: net25 reconstruction mismatch")
        if abs(reconstructed_xlu - float(parent_symbol["stock_after25_minus_sector_etf_mean_bps"])) > 1e-8:
            raise RuntimeError(f"{symbol}: XLU-excess reconstruction mismatch")

        positive_qqq_folds = sum(
            1 for fold in fold_stats
            if fold["matched_qqq_excess25_mean_bps"] is not None and fold["matched_qqq_excess25_mean_bps"] > 0
        )
        per_symbol.append({
            "symbol": symbol,
            "states": len(symbol_events),
            "candidate_net25_mean_bps": reconstructed_net,
            "matched_xlu_excess25_mean_bps": reconstructed_xlu,
            "matched_qqq_excess25_mean_bps": _mean(symbol_events, "qqq_excess25_bps"),
            "positive_xlu_excess_folds": int(parent_symbol["positive_sector_excess_folds"]),
            "positive_qqq_excess_folds": positive_qqq_folds,
            "development_transport_pass": bool(parent_symbol["development_transport_pass"]),
            "folds": fold_stats,
        })

    if len(events) != int(parent_summary["aggregate_primary_states"]):
        raise RuntimeError("aggregate state-count reconstruction mismatch")
    aggregate_net25 = _mean(events, "stock_net25_bps")
    aggregate_xlu25 = _mean(events, "xlu_excess25_bps")
    if abs(aggregate_net25 - float(parent_summary["aggregate_stock_net25_mean_bps"])) > 1e-8:
        raise RuntimeError("aggregate net25 reconstruction mismatch")
    if abs(aggregate_xlu25 - float(parent_summary["aggregate_stock_after25_minus_sector_etf_mean_bps"])) > 1e-8:
        raise RuntimeError("aggregate XLU reconstruction mismatch")

    aggregate_qqq25 = _mean(events, "qqq_excess25_bps")
    cost_grid = []
    for cost in COSTS:
        cost_grid.append({
            "stock_round_trip_cost_bps": cost,
            "candidate_net_mean_bps": float(np.mean([event["stock_gross_bps"] - cost for event in events])),
            "matched_xlu_excess_mean_bps": float(np.mean([event["stock_gross_bps"] - cost - event["xlu_gross_bps"] for event in events])),
            "matched_qqq_excess_mean_bps": float(np.mean([event["stock_gross_bps"] - cost - event["qqq_gross_bps"] for event in events])),
        })

    loo = []
    for symbol in symbols:
        kept = [event for event in events if event["symbol"] != symbol]
        loo.append({
            "excluded_symbol": symbol,
            "remaining_states": len(kept),
            "matched_xlu_excess25_mean_bps": _mean(kept, "xlu_excess25_bps"),
            "matched_qqq_excess25_mean_bps": _mean(kept, "qqq_excess25_bps"),
        })

    positive_contributions: dict[str, float] = {}
    all_contributions: dict[str, float] = {}
    for symbol in symbols:
        value = float(sum(event["xlu_excess25_bps"] for event in events if event["symbol"] == symbol))
        all_contributions[symbol] = value
        if value > 0:
            positive_contributions[symbol] = value
    positive_total = float(sum(positive_contributions.values()))
    contribution_rows = [
        {
            "symbol": symbol,
            "matched_xlu_excess25_sum_bps": all_contributions[symbol],
            "share_of_positive_xlu_contribution": (
                all_contributions[symbol] / positive_total
                if all_contributions[symbol] > 0 and positive_total > 0 else 0.0
            ),
        }
        for symbol in symbols
    ]

    passing = int(parent_summary["passing_symbols"])
    family_gate = bool(parent_summary["development_family_gate_pass"])
    worst_loo_xlu = min(row["matched_xlu_excess25_mean_bps"] for row in loo)
    max_positive_share = max(row["share_of_positive_xlu_contribution"] for row in contribution_rows)
    if family_gate and aggregate_xlu25 > 0 and aggregate_qqq25 > 0:
        decision = "UTILITIES_DEVELOPMENT_ALPHA_CANDIDATE"
    elif family_gate and aggregate_xlu25 > 0:
        decision = "UTILITIES_SECTOR_ALPHA_NOT_BROAD_MARKET_ALPHA"
    elif passing == 4 and aggregate_xlu25 > 0 and aggregate_qqq25 > 0:
        decision = "UTILITIES_DEVELOPMENT_NEAR_MISS"
    else:
        decision = "UTILITIES_GENERIC_TRANSPORT_REJECTED"

    return {
        "schema": "research_compute_public.utilities_stagea_alpha_discovery.v1",
        "research_only": True,
        "external_holdouts_loaded": False,
        "promotion_authority": False,
        "allocation_authority": False,
        "runtime_authority": False,
        "broker_authority": False,
        "live_trading_change": False,
        "family": FAMILY["utilities"],
        "window": {
            "selection_calendar_first": calendar[0].isoformat(),
            "selection_calendar_last": calendar[-1].isoformat(),
            "first_selected_entry": min(event["entry_date"] for event in events),
            "last_selected_exit": max(event["exit_date"] for event in events),
            "states": len(events),
        },
        "stagea": {
            "passing_symbols": passing,
            "required_passing_symbols": int(parent_summary["required_passing_symbols"]),
            "development_family_gate_pass": family_gate,
            "aggregate_candidate_net25_mean_bps": aggregate_net25,
            "aggregate_matched_xlu_excess25_mean_bps": aggregate_xlu25,
            "aggregate_matched_qqq_excess25_mean_bps": aggregate_qqq25,
        },
        "per_symbol": per_symbol,
        "cost_grid": cost_grid,
        "break_even_round_trip_cost_bps": {
            "versus_matched_xlu": 25.0 + aggregate_xlu25,
            "versus_matched_qqq": 25.0 + aggregate_qqq25,
        },
        "leave_one_symbol_out": loo,
        "contribution_concentration": {
            "max_positive_xlu_contribution_share": max_positive_share,
            "worst_leave_one_symbol_out_xlu_excess25_mean_bps": worst_loo_xlu,
            "symbols": contribution_rows,
        },
        "decision": decision,
        "consequence": (
            "This is development-only evidence. External holdouts remain sealed. If rejected, do not threshold-rescue the generic transport. "
            "If candidate or near-miss, the next child must be a predeclared confirmation/robustness discriminator with the same matched XLU and broad-market baseline discipline."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = evaluate(args.runner)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("UTILITIES_STAGEA_ALPHA=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
