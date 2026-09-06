from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = {"biotech": {"primary_industry_etf": "XBI", "development_universe": ["REGN", "VRTX", "GILD", "BIIB", "ALNY", "INCY", "BMRN", "UTHR"]}}
CUTOFF = "2026-09-01T13:30:00+00:00"
TOP_K = 2
PRIMARY_COST = 25.0
STRESS_COST = 50.0


def load_runner(path: Path):
    spec = importlib.util.spec_from_file_location("stagea_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Stage-A runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mean(values):
    vals = [float(v) for v in values]
    return None if not vals else float(np.mean(vals))


def evaluate(runner_path: Path) -> dict:
    r = load_runner(runner_path)
    cutoff = pd.Timestamp(CUTOFF)
    symbols = tuple(FAMILY["biotech"]["development_universe"])
    raw = {s: r._bounded(s, cutoff) for s in (*r.TRAIN, *symbols, "QQQ")}
    calendar = pd.DatetimeIndex(sorted(set.intersection(*[set(f.timestamp) for f in raw.values()])))
    if len(calendar) < 1500 or calendar[-1] != cutoff:
        raise RuntimeError("frozen common calendar failed")
    prices = {s: raw[s].set_index("timestamp").price.reindex(calendar) for s in raw}
    if any(v.isna().any() for v in prices.values()):
        raise RuntimeError("missing price on common calendar")
    xbi = r._bounded("XBI", cutoff).set_index("timestamp").price.reindex(calendar)
    if xbi.isna().any():
        raise RuntimeError("XBI missing common-calendar rows")

    data = r._engineer(prices, calendar, (*r.TRAIN, *symbols))
    folds = r._global_folds(len(calendar))
    train_states = r._state_frame(r.TRAIN, data, folds)
    test_states = r._state_frame(symbols, data, folds)

    records = []
    for symbol in symbols:
        for fold in range(r.EVAL_FIRST_FOLD, r.FOLDS + 1):
            start, _ = folds[fold - 1]
            train = train_states[train_states.signal_i < start - r.PURGE]
            test = test_states[(test_states.symbol == symbol) & (test_states.fold == fold)]
            model = r._fit(train)
            chosen = test.loc[model.predict(test[r.FEATURES].to_numpy(float)) > 0].copy()
            prior = data[symbol].iloc[: start - r.PURGE].mom20.dropna()
            threshold = float(prior.quantile(1.0 - r.TAIL))
            primary = chosen.loc[chosen.mom20 < threshold]
            for row in primary.itertuples(index=False):
                i = int(row.signal_i)
                entry = i + r.DELAY
                exit_ = entry + r.HOLD
                stock_gross = float(prices[symbol].iloc[exit_] / prices[symbol].iloc[entry] - 1.0) * 10000.0
                xbi_gross = float(xbi.iloc[exit_] / xbi.iloc[entry] - 1.0) * 10000.0
                qqq_gross = float(prices["QQQ"].iloc[exit_] / prices["QQQ"].iloc[entry] - 1.0) * 10000.0
                records.append({
                    "symbol": symbol,
                    "fold": fold,
                    "entry_date": calendar[entry].isoformat(),
                    "exit_date": calendar[exit_].isoformat(),
                    "stock_gross_bps": stock_gross,
                    "net25_bps": stock_gross - PRIMARY_COST,
                    "net50_bps": stock_gross - STRESS_COST,
                    "xbi_excess25_bps": stock_gross - PRIMARY_COST - xbi_gross,
                    "xbi_excess50_bps": stock_gross - STRESS_COST - xbi_gross,
                    "qqq_excess25_bps": stock_gross - PRIMARY_COST - qqq_gross,
                })

    rec = pd.DataFrame(records)
    if rec.empty:
        raise RuntimeError("empty selected population")

    fold_results = []
    selections = []
    # Fold 2 supplies only prior OOS evidence. Folds 3-6 are genuinely forward selection tests.
    for fold in range(3, r.FOLDS + 1):
        prior = rec[rec.fold < fold]
        current = rec[rec.fold == fold]
        rank_rows = []
        current_symbol = {}
        for symbol in symbols:
            p = prior[prior.symbol == symbol]
            c = current[current.symbol == symbol]
            if p.empty or c.empty:
                raise RuntimeError(f"insufficient causal support for {symbol} fold {fold}")
            rank_rows.append((mean(p.xbi_excess25_bps), symbol, len(p)))
            current_symbol[symbol] = c
        ranked = sorted(rank_rows, key=lambda x: (-x[0], x[1]))
        selected = [x[1] for x in ranked[:TOP_K]]
        selections.append({
            "fold": fold,
            "selected_symbols": selected,
            "prior_rank": [{"symbol": s, "prior_xbi_excess25_mean_bps": v, "prior_states": n} for v, s, n in ranked],
        })

        def ew_symbol_mean(symbols_, key):
            return mean([mean(current_symbol[s][key]) for s in symbols_])

        top2_net25 = ew_symbol_mean(selected, "net25_bps")
        all8_net25 = ew_symbol_mean(symbols, "net25_bps")
        top2_xbi25 = ew_symbol_mean(selected, "xbi_excess25_bps")
        top2_xbi50 = ew_symbol_mean(selected, "xbi_excess50_bps")
        top2_qqq25 = ew_symbol_mean(selected, "qqq_excess25_bps")
        fold_results.append({
            "fold": fold,
            "selected_symbols": selected,
            "candidate_net25_mean_bps": top2_net25,
            "equal_weight_all_biotech_net25_mean_bps": all8_net25,
            "excess_vs_equal_weight_biotech_bps": top2_net25 - all8_net25,
            "matched_xbi_excess25_mean_bps": top2_xbi25,
            "matched_xbi_excess50_mean_bps": top2_xbi50,
            "matched_qqq_excess25_mean_bps": top2_qqq25,
        })

    aggregate = {
        "candidate_net25_mean_bps": mean([x["candidate_net25_mean_bps"] for x in fold_results]),
        "equal_weight_all_biotech_net25_mean_bps": mean([x["equal_weight_all_biotech_net25_mean_bps"] for x in fold_results]),
        "excess_vs_equal_weight_biotech_bps": mean([x["excess_vs_equal_weight_biotech_bps"] for x in fold_results]),
        "matched_xbi_excess25_mean_bps": mean([x["matched_xbi_excess25_mean_bps"] for x in fold_results]),
        "matched_xbi_excess50_mean_bps": mean([x["matched_xbi_excess50_mean_bps"] for x in fold_results]),
        "matched_qqq_excess25_mean_bps": mean([x["matched_qqq_excess25_mean_bps"] for x in fold_results]),
        "positive_equal_weight_excess_folds": sum(x["excess_vs_equal_weight_biotech_bps"] > 0 for x in fold_results),
        "positive_xbi_excess25_folds": sum(x["matched_xbi_excess25_mean_bps"] > 0 for x in fold_results),
        "positive_xbi_excess50_folds": sum(x["matched_xbi_excess50_mean_bps"] > 0 for x in fold_results),
        "positive_qqq_excess25_folds": sum(x["matched_qqq_excess25_mean_bps"] > 0 for x in fold_results),
    }
    supported = bool(
        aggregate["excess_vs_equal_weight_biotech_bps"] > 0
        and aggregate["matched_xbi_excess25_mean_bps"] > 0
        and aggregate["matched_xbi_excess50_mean_bps"] > 0
        and aggregate["positive_equal_weight_excess_folds"] >= 3
        and aggregate["positive_xbi_excess25_folds"] >= 3
    )
    decision = "CAUSAL_CONCENTRATION_CAPTURE_SUPPORTED" if supported else "CAUSAL_COMPONENT_SELECTION_NOT_SUPPORTED"
    return {
        "schema": "public_research.biotech_causal_component_selector.v1",
        "research_only": True,
        "external_holdouts_loaded": False,
        "selection_rule": "top2 by cumulative prior-OOS matched-XBI excess at 25bps; ticker ascending exact ties",
        "evaluation_folds": [3, 4, 5, 6],
        "window": {"selection_calendar_first": calendar[0].isoformat(), "selection_calendar_last": calendar[-1].isoformat(), "first_selected_entry": min(records, key=lambda x: x["entry_date"])["entry_date"], "last_selected_exit": max(records, key=lambda x: x["exit_date"])["exit_date"]},
        "selections": selections,
        "folds": fold_results,
        "aggregate": aggregate,
        "decision": decision,
        "consequence": (
            "If supported, the concentrated Biotech effect is causally rankable within development chronology and merits a separately frozen external confirmation cohort. If unsupported, preserve the family alpha observation but do not build a scarcity selector from retrospective component winners."
        ),
        "promotion_authority": False,
        "allocation_authority": False,
        "runtime_authority": False,
        "broker_authority": False,
        "live_trading_change": False,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runner", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    result = evaluate(args.runner)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("BIOTECH_CAUSAL_COMPONENT_SELECTOR=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
