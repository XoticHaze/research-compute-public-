from __future__ import annotations

import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

CONTRACT = Path("research/biotech-nearmiss-detail-contract.json")
ADAPTER = Path(".campaign/runner.py")
OUT = Path("opportunity_biotech_prior_edge_capacity_allocator_20260907.json")
CAPACITY = 3
EVAL_FOLDS = (4, 5, 6)


def load_runner():
    spec = importlib.util.spec_from_file_location("accepted_stagea_runner", ADAPTER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load accepted Stage-A adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_records(runner, contract):
    family = contract["family"]["biotech"]
    dev = tuple(family["development_universe"])
    cutoff = pd.Timestamp(contract["frozen_cutoff"])
    selection_symbols = (*runner.TRAIN, *dev, "QQQ")
    raw = {symbol: runner._bounded(symbol, cutoff) for symbol in selection_symbols}
    calendar = pd.DatetimeIndex(sorted(set.intersection(*[set(frame.timestamp) for frame in raw.values()])))
    if calendar[-1] != cutoff:
        raise RuntimeError("selection calendar cutoff drift")
    prices = {symbol: raw[symbol].set_index("timestamp").price.reindex(calendar) for symbol in raw}
    if any(series.isna().any() for series in prices.values()):
        raise RuntimeError("missing selection price")
    xbi = runner._bounded(family["primary_industry_etf"], cutoff).set_index("timestamp").price.reindex(calendar)
    if xbi.isna().any():
        raise RuntimeError("XBI missing on frozen selection calendar")

    data = runner._engineer(prices, calendar, (*runner.TRAIN, *dev))
    folds = runner._global_folds(len(calendar))
    train_states = runner._state_frame(runner.TRAIN, data, folds)
    test_states = runner._state_frame(dev, data, folds)
    records = []
    for fold in range(runner.EVAL_FIRST_FOLD, runner.FOLDS + 1):
        start, _ = folds[fold - 1]
        train = train_states[train_states.signal_i < start - runner.PURGE]
        if len(train) < 1000:
            raise RuntimeError(f"fold {fold}: insufficient train rows={len(train)}")
        model = runner._fit(train)
        for symbol in dev:
            test = test_states[(test_states.symbol == symbol) & (test_states.fold == fold)].copy()
            prediction = model.predict(test[runner.FEATURES].to_numpy(float))
            test["prediction_bps"] = prediction
            chosen = test.loc[test.prediction_bps > 0].copy()
            prior_mom = data[symbol].iloc[:start - runner.PURGE].mom20.dropna()
            if len(prior_mom) < 250:
                raise RuntimeError(f"{symbol} fold {fold}: insufficient momentum threshold history")
            threshold = float(prior_mom.quantile(1.0 - runner.TAIL))
            primary = chosen.loc[chosen.mom20 < threshold]
            for row in primary.itertuples(index=False):
                signal_i = int(row.signal_i)
                entry_i = signal_i + runner.DELAY
                exit_i = entry_i + runner.HOLD
                stock_gross = float(prices[symbol].iloc[exit_i] / prices[symbol].iloc[entry_i] - 1.0)
                xbi_gross = float(xbi.iloc[exit_i] / xbi.iloc[entry_i] - 1.0)
                records.append({
                    "fold": fold,
                    "symbol": symbol,
                    "signal_i": signal_i,
                    "entry_i": entry_i,
                    "exit_i": exit_i,
                    "signal_date": calendar[signal_i].isoformat(),
                    "entry_date": calendar[entry_i].isoformat(),
                    "exit_date": calendar[exit_i].isoformat(),
                    "prediction_bps": float(row.prediction_bps),
                    "stock_net25": stock_gross - runner.COST_BPS / 10000.0,
                    "xbi_net25": xbi_gross - runner.COST_BPS / 10000.0,
                    "stock_after25_minus_xbi_gross_bps": (stock_gross - runner.COST_BPS / 10000.0 - xbi_gross) * 10000.0,
                    "sector_substitution50_bps": (stock_gross - xbi_gross) * 10000.0 - 50.0,
                })
    return calendar, folds, dev, records


def prior_symbol_stats(records, before_fold, symbols):
    by_symbol = defaultdict(list)
    for record in records:
        if record["fold"] < before_fold:
            by_symbol[record["symbol"]].append(record)
    stats = {}
    prior_folds = tuple(range(2, before_fold))
    for symbol in symbols:
        rows = by_symbol[symbol]
        fold_excess = {}
        for fold in prior_folds:
            vals = [r["stock_after25_minus_xbi_gross_bps"] for r in rows if r["fold"] == fold]
            if vals:
                fold_excess[fold] = float(np.mean(vals))
        stats[symbol] = {
            "states": len(rows),
            "mean_stock_net25_bps": float(np.mean([r["stock_net25"] for r in rows]) * 10000.0) if rows else None,
            "mean_sector_excess_bps": float(np.mean([r["stock_after25_minus_xbi_gross_bps"] for r in rows])) if rows else None,
            "positive_sector_excess_folds": sum(v > 0 for v in fold_excess.values()),
            "observed_prior_folds": len(fold_excess),
        }
    return stats


def selector_sets(stats, symbols):
    ranked = sorted(
        symbols,
        key=lambda s: (
            -1e18 if stats[s]["mean_sector_excess_bps"] is None else stats[s]["mean_sector_excess_bps"],
            s,
        ),
        reverse=True,
    )
    top4 = set(ranked[:4])
    robust = {
        s for s in symbols
        if stats[s]["mean_sector_excess_bps"] is not None
        and stats[s]["mean_sector_excess_bps"] > 0
        and stats[s]["mean_stock_net25_bps"] is not None
        and stats[s]["mean_stock_net25_bps"] > 0
        and stats[s]["observed_prior_folds"] >= 2
        and stats[s]["positive_sector_excess_folds"] >= math.ceil(stats[s]["observed_prior_folds"] / 2)
    }
    return {
        "all8_prediction": set(symbols),
        "prior_excess_top4_prediction": top4,
        "prior_robust_positive_prediction": robust,
    }


def simulate_capacity(records, allowed_symbols, fold):
    candidates = [r for r in records if r["fold"] == fold and r["symbol"] in allowed_symbols]
    grouped = defaultdict(list)
    for record in candidates:
        grouped[record["entry_i"]].append(record)
    slots = [{"wealth": 1.0 / CAPACITY, "exit_i": -1, "symbol": None, "record": None} for _ in range(CAPACITY)]
    accepted = []

    def realize_through(index):
        for slot in slots:
            rec = slot["record"]
            if rec is not None and slot["exit_i"] <= index:
                slot["wealth"] *= 1.0 + rec["stock_net25"]
                slot["record"] = None
                slot["exit_i"] = -1
                slot["symbol"] = None

    for entry_i in sorted(grouped):
        realize_through(entry_i)
        free = [slot for slot in slots if slot["record"] is None]
        if not free:
            continue
        active_symbols = {slot["symbol"] for slot in slots if slot["symbol"] is not None}
        day_candidates = sorted(grouped[entry_i], key=lambda r: (-r["prediction_bps"], r["symbol"]))
        for rec in day_candidates:
            if not free:
                break
            if rec["symbol"] in active_symbols:
                continue
            slot = free.pop(0)
            slot["record"] = rec
            slot["exit_i"] = rec["exit_i"]
            slot["symbol"] = rec["symbol"]
            active_symbols.add(rec["symbol"])
            accepted.append(rec)
    realize_through(10**9)
    terminal = float(sum(slot["wealth"] for slot in slots))
    if not accepted:
        return {
            "terminal_wealth": terminal,
            "return": terminal - 1.0,
            "accepted_trades": 0,
            "mean_stock_net25_bps": None,
            "mean_sector_excess_bps": None,
            "mean_sector_substitution50_bps": None,
            "symbols_used": [],
        }
    return {
        "terminal_wealth": terminal,
        "return": terminal - 1.0,
        "accepted_trades": len(accepted),
        "mean_stock_net25_bps": float(np.mean([r["stock_net25"] for r in accepted]) * 10000.0),
        "mean_sector_excess_bps": float(np.mean([r["stock_after25_minus_xbi_gross_bps"] for r in accepted])),
        "mean_sector_substitution50_bps": float(np.mean([r["sector_substitution50_bps"] for r in accepted])),
        "symbols_used": sorted({r["symbol"] for r in accepted}),
    }


def main():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract["external_holdouts_loaded"] is not False:
        raise RuntimeError("contract unexpectedly permits external holdouts")
    runner = load_runner()
    calendar, folds, symbols, records = build_records(runner, contract)

    fold_results = []
    for fold in EVAL_FOLDS:
        stats = prior_symbol_stats(records, fold, symbols)
        selectors = selector_sets(stats, symbols)
        policies = {name: simulate_capacity(records, allowed, fold) for name, allowed in selectors.items()}
        fold_results.append({
            "fold": fold,
            "prior_folds": list(range(2, fold)),
            "prior_symbol_stats": stats,
            "selector_symbols": {k: sorted(v) for k, v in selectors.items()},
            "policies": policies,
        })

    policy_names = ("all8_prediction", "prior_excess_top4_prediction", "prior_robust_positive_prediction")
    aggregate = {}
    for policy in policy_names:
        rows = [fold["policies"][policy] for fold in fold_results]
        compound = float(np.prod([1.0 + row["return"] for row in rows]) - 1.0)
        aggregate[policy] = {
            "compound_fold_return": compound,
            "fold_returns": [row["return"] for row in rows],
            "accepted_trades": int(sum(row["accepted_trades"] for row in rows)),
            "mean_fold_sector_excess_bps": float(np.mean([row["mean_sector_excess_bps"] for row in rows if row["mean_sector_excess_bps"] is not None])) if any(row["mean_sector_excess_bps"] is not None for row in rows) else None,
            "mean_fold_sector_substitution50_bps": float(np.mean([row["mean_sector_substitution50_bps"] for row in rows if row["mean_sector_substitution50_bps"] is not None])) if any(row["mean_sector_substitution50_bps"] is not None for row in rows) else None,
        }

    baseline = aggregate["all8_prediction"]
    top4 = aggregate["prior_excess_top4_prediction"]
    robust = aggregate["prior_robust_positive_prediction"]
    top4_fold_wins = sum(
        fold["policies"]["prior_excess_top4_prediction"]["return"] > fold["policies"]["all8_prediction"]["return"]
        for fold in fold_results
    )
    robust_fold_wins = sum(
        fold["policies"]["prior_robust_positive_prediction"]["return"] > fold["policies"]["all8_prediction"]["return"]
        for fold in fold_results
    )
    top4_supported = bool(
        top4["compound_fold_return"] > baseline["compound_fold_return"]
        and top4["mean_fold_sector_excess_bps"] is not None
        and baseline["mean_fold_sector_excess_bps"] is not None
        and top4["mean_fold_sector_excess_bps"] > baseline["mean_fold_sector_excess_bps"]
        and top4_fold_wins >= 2
        and top4["accepted_trades"] >= 0.5 * baseline["accepted_trades"]
    )
    robust_supported = bool(
        robust["compound_fold_return"] > baseline["compound_fold_return"]
        and robust["mean_fold_sector_excess_bps"] is not None
        and baseline["mean_fold_sector_excess_bps"] is not None
        and robust["mean_fold_sector_excess_bps"] > baseline["mean_fold_sector_excess_bps"]
        and robust_fold_wins >= 2
        and robust["accepted_trades"] >= 0.4 * baseline["accepted_trades"]
    )

    receipt = {
        "schema": "public_research.opportunity_biotech_prior_edge_capacity_allocator.v1",
        "research_only": True,
        "parent": {
            "family": "biotech",
            "benchmark": "XBI",
            "development_family_gate": "FAILED_4_OF_8",
            "near_miss_detail_run": 34107736635,
            "accepted_stagea_adapter_commit": contract["scientific_parent"]["accepted_stagea_adapter_commit"],
        },
        "objective": "Test whether fold-causal ticker identity improves scarce-capital allocation even though the Biotech family-level breadth gate failed.",
        "causality": "For evaluation folds 4-6, symbol eligibility/ranking uses only realized matched-XBI evidence from earlier completed folds. Current-fold and later outcomes never enter selector construction.",
        "capacity": CAPACITY,
        "evaluation_folds": list(EVAL_FOLDS),
        "frozen_cutoff": contract["frozen_cutoff"],
        "development_universe": list(symbols),
        "selection_calendar": {"rows": len(calendar), "first": calendar[0].isoformat(), "last": calendar[-1].isoformat()},
        "candidate_primary_states": len(records),
        "fold_results": fold_results,
        "aggregate": aggregate,
        "decisions": {
            "prior_excess_top4_improves_capacity_allocation": "SUPPORTED" if top4_supported else "NOT_SUPPORTED",
            "prior_robust_positive_improves_capacity_allocation": "SUPPORTED" if robust_supported else "NOT_SUPPORTED",
            "top4_fold_wins_vs_all8": top4_fold_wins,
            "robust_fold_wins_vs_all8": robust_fold_wins,
        },
        "interpretation_boundary": "This tests an adaptive ticker-allocation rule inside the frozen Biotech development corpus. It does not overturn the failed family breadth gate or authorize external-holdout admission/promotion.",
        "external_holdouts_loaded": False,
        "threshold_search": False,
        "hyperparameter_search": False,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("OPPORTUNITY_BIOTECH_PRIOR_EDGE_CAPACITY_ALLOCATOR=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
