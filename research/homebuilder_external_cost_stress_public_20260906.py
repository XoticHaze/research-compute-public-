from __future__ import annotations

"""Born-public Homebuilder external cost-stress consumer.

This adapter consumes only the already-public Stage-A research adapter plus public
market prices. It first reproduces the accepted original Stage-A family decisions,
then reproduces the frozen Homebuilder external 25-bps population before varying
only ex-post stock cost. No model refit, threshold search, ticker identity, sizing,
runtime, broker, promotion, or live-trading authority is introduced.
"""

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

CAMPAIGN = Path(".campaign")
BASE_PATH = CAMPAIGN / "stagea.py"
CONTRACT_PATH = CAMPAIGN / "stagea_contract.json"
OUT = Path("homebuilder_external_cost_stress_public_20260906.json")

CUTOFF = "2026-09-01T13:30:00+00:00"
HOLDOUT = ("CCS", "MHO", "HOV", "BZH")
BENCHMARK = "ITB"
COSTS = (25.0, 50.0, 100.0, 150.0, 200.0)
EXPECTED_NATIVE = {
    "CCS": {"states": 1082, "pass": True},
    "MHO": {"states": 1025, "pass": False},
    "HOV": {"states": 984, "pass": True},
    "BZH": {"states": 1050, "pass": True},
}
EXPECTED_NATIVE_AGG_ALPHA_BPS = 41.110290221860005


def load_base():
    spec = importlib.util.spec_from_file_location("public_stagea", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load public Stage-A adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mean(values: list[float]) -> float | None:
    return None if not values else float(np.mean(values))


def stagea_decision_parity(base, contract: dict) -> dict:
    parity = contract["parity_control"]
    replay = base._evaluate_matrix(parity["families"], parity["common_cutoff"])
    families = {}
    decisions_match = True
    for family, expected in parity["accepted_family_summary"].items():
        got = replay["family_summary"][family]
        same = int(got["passing_symbols"]) == int(expected["passing_symbols"])
        decisions_match = decisions_match and same
        families[family] = {
            "expected_passing_symbols": int(expected["passing_symbols"]),
            "actual_passing_symbols": int(got["passing_symbols"]),
            "decision_match": same,
            "state_count_delta": int(got["aggregate_primary_states"]) - int(expected["aggregate_primary_states"]),
            "absolute_bps_delta": float(got["aggregate_stock_net25_mean_bps"]) - float(expected["aggregate_stock_net25_mean_bps"]),
            "matched_etf_excess_bps_delta": float(got["aggregate_stock_after25_minus_sector_etf_mean_bps"]) - float(expected["aggregate_stock_after25_minus_sector_etf_mean_bps"]),
        }
    if not decisions_match:
        raise RuntimeError(f"Stage-A scientific decision parity break: {families}")
    return {
        "passed": True,
        "classification": "DECISION_PARITY",
        "families": families,
    }


def build_frozen_records(base) -> tuple[pd.DatetimeIndex, list[dict]]:
    cutoff = pd.Timestamp(CUTOFF)
    selection_symbols = (*base.TRAIN, *HOLDOUT, "QQQ")
    raw = {symbol: base._bounded(symbol, cutoff) for symbol in selection_symbols}
    calendar = pd.DatetimeIndex(sorted(set.intersection(*[set(frame.timestamp) for frame in raw.values()])))
    if len(calendar) < 1500 or calendar[-1] != cutoff:
        raise RuntimeError(f"invalid frozen Homebuilder calendar rows={len(calendar)} last={calendar[-1] if len(calendar) else None}")
    prices = {symbol: raw[symbol].set_index("timestamp").price.reindex(calendar) for symbol in raw}
    if any(series.isna().any() for series in prices.values()):
        raise RuntimeError("missing price on frozen Homebuilder selection calendar")

    # Benchmark is observational only and loads after the selection calendar is frozen.
    itb = base._bounded(BENCHMARK, cutoff).set_index("timestamp").price.reindex(calendar)
    if itb.isna().any():
        raise RuntimeError("ITB missing rows on frozen selection calendar")

    modeled = (*base.TRAIN, *HOLDOUT)
    data = base._engineer(prices, calendar, modeled)
    folds = base._global_folds(len(calendar))
    train_states = base._state_frame(base.TRAIN, data, folds)
    holdout_states = base._state_frame(HOLDOUT, data, folds)

    records: list[dict] = []
    for symbol in HOLDOUT:
        for fold in range(base.EVAL_FIRST_FOLD, base.FOLDS + 1):
            start, _ = folds[fold - 1]
            train = train_states[train_states.signal_i < start - base.PURGE]
            test = holdout_states[(holdout_states.symbol == symbol) & (holdout_states.fold == fold)]
            if len(train) < 1000:
                raise RuntimeError(f"{symbol} fold {fold}: insufficient training rows={len(train)}")
            model = base._fit(train)
            pred = model.predict(test[base.FEATURES].to_numpy(float))
            chosen = test.loc[pred > 0].copy()
            prior = data[symbol].iloc[: start - base.PURGE].mom20.dropna()
            if len(prior) < 250:
                raise RuntimeError(f"{symbol} fold {fold}: insufficient threshold support={len(prior)}")
            threshold = float(prior.quantile(1.0 - base.TAIL))
            primary = chosen.loc[chosen.mom20 < threshold]
            for row in primary.itertuples(index=False):
                signal_i = int(row.signal_i)
                exec_i = signal_i + base.DELAY
                exit_i = exec_i + base.HOLD
                stock_gross = float(prices[symbol].iloc[exit_i] / prices[symbol].iloc[exec_i] - 1.0) * 10000.0
                itb_gross = float(itb.iloc[exit_i] / itb.iloc[exec_i] - 1.0) * 10000.0
                records.append({
                    "symbol": symbol,
                    "fold": fold,
                    "signal_date": calendar[signal_i].isoformat(),
                    "entry_date": calendar[exec_i].isoformat(),
                    "exit_date": calendar[exit_i].isoformat(),
                    "stock_gross_bps": stock_gross,
                    "itb_gross_bps": itb_gross,
                })
    return calendar, records


def stress_summary(records: list[dict], cost: float) -> dict:
    per_symbol = []
    all_net: list[float] = []
    all_alpha: list[float] = []
    for symbol in HOLDOUT:
        rows = [r for r in records if r["symbol"] == symbol]
        net = [float(r["stock_gross_bps"]) - cost for r in rows]
        alpha = [float(r["stock_gross_bps"]) - cost - float(r["itb_gross_bps"]) for r in rows]
        fold_net = []
        fold_alpha = []
        for fold in range(2, 7):
            frows = [r for r in rows if r["fold"] == fold]
            fold_net.append(mean([float(r["stock_gross_bps"]) - cost for r in frows]))
            fold_alpha.append(mean([float(r["stock_gross_bps"]) - cost - float(r["itb_gross_bps"]) for r in frows]))
        positive_net_folds = sum(v is not None and v > 0 for v in fold_net)
        positive_alpha_folds = sum(v is not None and v > 0 for v in fold_alpha)
        net_mean = mean(net)
        alpha_mean = mean(alpha)
        passed = bool(
            len(rows) >= 20
            and net_mean is not None and net_mean > 0
            and alpha_mean is not None and alpha_mean > 0
            and positive_net_folds >= 3
            and positive_alpha_folds >= 3
        )
        per_symbol.append({
            "symbol": symbol,
            "states": len(rows),
            "stock_net_mean_bps": net_mean,
            "matched_itb_excess_mean_bps": alpha_mean,
            "positive_stock_net_folds": positive_net_folds,
            "positive_matched_itb_excess_folds": positive_alpha_folds,
            "passes": passed,
        })
        all_net.extend(net)
        all_alpha.extend(alpha)
    passing = sum(int(r["passes"]) for r in per_symbol)
    aggregate_alpha = mean(all_alpha)
    return {
        "cost_bps": cost,
        "passing_symbols": passing,
        "required_passing_symbols": 3,
        "aggregate_stock_net_mean_bps": mean(all_net),
        "aggregate_matched_itb_excess_mean_bps": aggregate_alpha,
        "passes": bool(passing >= 3 and aggregate_alpha is not None and aggregate_alpha > 0),
        "per_symbol": per_symbol,
    }


def main() -> None:
    base = load_base()
    contract = json.loads(CONTRACT_PATH.read_text())
    stagea_parity = stagea_decision_parity(base, contract)
    calendar, records = build_frozen_records(base)
    stresses = [stress_summary(records, cost) for cost in COSTS]
    native = stresses[0]

    expected_count_match = True
    expected_pass_match = True
    for row in native["per_symbol"]:
        expected = EXPECTED_NATIVE[row["symbol"]]
        expected_count_match = expected_count_match and int(row["states"]) == int(expected["states"])
        expected_pass_match = expected_pass_match and bool(row["passes"]) == bool(expected["pass"])
    aggregate_delta = float(native["aggregate_matched_itb_excess_mean_bps"]) - EXPECTED_NATIVE_AGG_ALPHA_BPS
    if not expected_count_match or not expected_pass_match or native["passing_symbols"] != 3 or not native["passes"]:
        raise RuntimeError(
            "native Homebuilder replay parity break: "
            + json.dumps({"count_match": expected_count_match, "pass_match": expected_pass_match, "native": native}, sort_keys=True)
        )

    surviving = [float(row["cost_bps"]) for row in stresses if row["passes"]]
    max_surviving = max(surviving) if surviving else None
    classification = (
        "HOMEBUILDERS_EXTERNAL_COST_STRESS_SURVIVES_200BPS"
        if stresses[-1]["passes"]
        else "HOMEBUILDERS_EXTERNAL_COST_STRESS_BREAKS_BEFORE_200BPS"
    )
    out = {
        "schema": "research_compute_public.homebuilder_external_cost_stress.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scientific_parent": {
            "private_foundry_pr": 146,
            "accepted_run": 33626440109,
            "frozen_cutoff": CUTOFF,
            "external_population": list(HOLDOUT),
            "benchmark": BENCHMARK,
        },
        "stagea_public_parity": stagea_parity,
        "native_replay": {
            "state_counts_match": expected_count_match,
            "symbol_passes_match": expected_pass_match,
            "aggregate_matched_itb_excess_expected_bps": EXPECTED_NATIVE_AGG_ALPHA_BPS,
            "aggregate_matched_itb_excess_actual_bps": native["aggregate_matched_itb_excess_mean_bps"],
            "aggregate_delta_bps": aggregate_delta,
            "selection_calendar_rows": len(calendar),
            "selection_calendar_first": calendar[0].isoformat(),
            "selection_calendar_last": calendar[-1].isoformat(),
        },
        "stresses": stresses,
        "max_broad_surviving_cost_bps": max_surviving,
        "classification": classification,
        "external_holdout_targets_used_in_training": False,
        "threshold_search": False,
        "hyperparameter_search": False,
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("HOMEBUILDER_COST_STRESS_TERMINAL=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
