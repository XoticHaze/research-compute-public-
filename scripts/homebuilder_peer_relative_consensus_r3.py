from __future__ import annotations

"""Homebuilder peer-relative temporal-consensus alpha R3.

This child is frozen after R2 showed positive aggregate marginal alpha but failed
chronology and per-symbol robustness. No R2 holdout is reused. Fresh external
holdouts are DFH and LEGH, selected by source viability before any R3 economics.

Mechanism change: preserve the equal-weight external core and permit a 25% tilt
into one name only when three causal Ridge estimates (expanding, recent 504
sessions, recent 252 sessions) all predict positive peer-relative value after the
same 50 bps switching hurdle. Ranking uses the worst-case prediction. There is no
score-threshold, horizon, alpha, feature, or capacity sweep.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import homebuilder_peer_relative_alpha_r1 as base

EXTERNAL = ("DFH", "LEGH")
ALL = (*base.DEV, *EXTERNAL, *base.CONTEXT)
WINDOWS = {"expanding": None, "recent504": 504, "recent252": 252}
BURNIN = 504
DECISION_STEP = 20
MAX_TILT_NAMES = 1
TILT_WEIGHT = 0.25
MIN_TRAIN_ROWS = 240
MIN_DECISIONS = 40
MIN_TILT_DECISIONS = 12
MIN_SYMBOL_EVENTS = 5
FOLDS = 5
OUTPUT = Path("research/results/homebuilder_peer_relative_consensus_r3.json")
SOURCE_PREFLIGHT = {
    "commit": "86447f0fa6118cbe80b616e66cdaf83878b08978",
    "run": 34683785000,
    "job": 103527065432,
    "economic_results_observed_before_holdout_freeze": False,
    "DFH": {"first": "2021-01-21", "last": "2026-09-11", "sessions": 1417},
    "LEGH": {"first": "2019-01-02", "last": "2026-09-11", "sessions": 1934},
}


def fit_model(train: pd.DataFrame) -> Pipeline:
    if len(train) < MIN_TRAIN_ROWS:
        raise RuntimeError(f"insufficient causal train rows={len(train)}")
    model = Pipeline([("scale", StandardScaler()), ("ridge", Ridge(alpha=10.0))])
    model.fit(
        train[list(base.FEATURES)].to_numpy(float),
        train["target_peer_excess_after50_bps"].to_numpy(float),
    )
    return model


def mean(values: list[float]) -> float | None:
    return None if not values else float(np.mean(np.asarray(values, dtype=float)))


def main() -> None:
    raw = {symbol: base.load(symbol) for symbol in ALL}
    common = pd.DatetimeIndex(sorted(set.intersection(*[set(series.index) for series in raw.values()])))
    frame = pd.DataFrame({symbol: raw[symbol].reindex(common) for symbol in ALL}).dropna()
    if len(frame) < 1300:
        raise RuntimeError(f"insufficient fresh-holdout common calendar={len(frame)}")

    training = base.build_training_rows(frame)
    decision_indices = list(range(BURNIN, len(frame) - base.PURGE, DECISION_STEP))
    if len(decision_indices) < MIN_DECISIONS:
        raise RuntimeError(f"insufficient external decisions={len(decision_indices)}")

    fold_parts = [list(map(int, part)) for part in np.array_split(np.asarray(decision_indices), FOLDS)]
    fold_by_signal = {signal: fold_no for fold_no, part in enumerate(fold_parts, start=1) for signal in part}

    decisions: list[dict] = []
    per_symbol: dict[str, list[float]] = {symbol: [] for symbol in EXTERNAL}

    for signal_i in decision_indices:
        causal = training[training.signal_i < signal_i - base.PURGE].copy()
        features = pd.DataFrame(
            [{"symbol": symbol, **base.feature_vector(frame, symbol, signal_i)} for symbol in EXTERNAL]
        )

        model_predictions: dict[str, dict[str, float]] = {}
        train_rows: dict[str, int] = {}
        for label, window in WINDOWS.items():
            train = causal if window is None else causal[causal.signal_i >= signal_i - window]
            train_rows[label] = int(len(train))
            model = fit_model(train)
            preds = model.predict(features[list(base.FEATURES)].to_numpy(float))
            model_predictions[label] = {
                str(symbol): float(pred)
                for pred, symbol in zip(preds, features["symbol"], strict=True)
            }

        worst_case = {
            symbol: min(model_predictions[label][symbol] for label in WINDOWS)
            for symbol in EXTERNAL
        }
        candidates = sorted(
            [(score, symbol) for symbol, score in worst_case.items() if score > 0.0],
            key=lambda item: (-item[0], item[1]),
        )
        selected = [symbol for _, symbol in candidates[:MAX_TILT_NAMES]]

        external_returns = {symbol: base.future_ret(frame[symbol], signal_i) for symbol in EXTERNAL}
        baseline_gross = float(np.mean(list(external_returns.values())))
        baseline_net = baseline_gross - base.COMMON_REBALANCE_BPS / 10000.0

        if selected:
            selected_gross = float(np.mean([external_returns[symbol] for symbol in selected]))
            peer_excess_bps = (selected_gross - baseline_gross) * 10000.0 - base.SWITCH_HURDLE_BPS
            overlay_net = baseline_net + TILT_WEIGHT * (
                selected_gross - baseline_gross - base.SWITCH_HURDLE_BPS / 10000.0
            )
            for symbol in selected:
                per_symbol[symbol].append(
                    float((external_returns[symbol] - baseline_gross) * 10000.0 - base.SWITCH_HURDLE_BPS)
                )
        else:
            selected_gross = None
            peer_excess_bps = None
            overlay_net = baseline_net

        entry_i = signal_i + base.DELAY
        exit_i = entry_i + base.HOLD
        decisions.append(
            {
                "fold": fold_by_signal[signal_i],
                "signal_i": signal_i,
                "signal_date": frame.index[signal_i].isoformat(),
                "entry_date": frame.index[entry_i].isoformat(),
                "exit_date": frame.index[exit_i].isoformat(),
                "train_rows": train_rows,
                "model_predictions_bps": model_predictions,
                "worst_case_prediction_bps": worst_case,
                "selected": selected,
                "baseline_equal_external_net": baseline_net,
                "overlay_75core_25tilt_net": overlay_net,
                "incremental_overlay_bps": float((overlay_net - baseline_net) * 10000.0),
                "selected_peer_excess_after50_bps": peer_excess_bps,
            }
        )

    baseline_returns = [float(row["baseline_equal_external_net"]) for row in decisions]
    overlay_returns = [float(row["overlay_75core_25tilt_net"]) for row in decisions]
    incremental = [float(row["incremental_overlay_bps"]) for row in decisions]
    selected_excess = [
        float(row["selected_peer_excess_after50_bps"])
        for row in decisions
        if row["selected_peer_excess_after50_bps"] is not None
    ]
    tilt_decisions = sum(bool(row["selected"]) for row in decisions)

    folds = []
    for fold_no in range(1, FOLDS + 1):
        rows = [row for row in decisions if row["fold"] == fold_no]
        folds.append(
            {
                "fold": fold_no,
                "decisions": len(rows),
                "tilt_decisions": sum(bool(row["selected"]) for row in rows),
                "mean_incremental_overlay_bps": mean([float(row["incremental_overlay_bps"]) for row in rows]),
                "mean_selected_peer_excess_after50_bps": mean([
                    float(row["selected_peer_excess_after50_bps"])
                    for row in rows
                    if row["selected_peer_excess_after50_bps"] is not None
                ]),
            }
        )

    symbols = []
    symbol_passes = 0
    for symbol in EXTERNAL:
        values = per_symbol[symbol]
        avg = mean(values)
        passed = len(values) >= MIN_SYMBOL_EVENTS and avg is not None and avg > 0.0
        symbol_passes += int(passed)
        symbols.append(
            {
                "symbol": symbol,
                "selected_events": len(values),
                "mean_conservative_peer_excess_bps": avg,
                "pass": passed,
            }
        )

    baseline_ann = base.annualize_periodic(baseline_returns)
    overlay_ann = base.annualize_periodic(overlay_returns)
    annualized_increment = None if baseline_ann is None or overlay_ann is None else overlay_ann - baseline_ann
    positive_folds = sum(
        row["mean_incremental_overlay_bps"] is not None and row["mean_incremental_overlay_bps"] > 0.0
        for row in folds
    )
    selected_mean = mean(selected_excess)

    gate = (
        len(decisions) >= MIN_DECISIONS
        and tilt_decisions >= MIN_TILT_DECISIONS
        and annualized_increment is not None
        and annualized_increment > 0.0
        and positive_folds >= 4
        and selected_mean is not None
        and selected_mean > 0.0
        and symbol_passes == len(EXTERNAL)
    )
    decision = (
        "HOMEBUILDER_TEMPORAL_CONSENSUS_TILT_PASSES_FRESH_EXTERNAL_GATE"
        if gate
        else "HOMEBUILDER_TEMPORAL_CONSENSUS_TILT_REJECTED_AS_SPECIFIED"
    )

    payload = {
        "schema": "public_research.homebuilder_peer_relative_consensus_r3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "parent_evidence": {
            "r2_run": 34683662861,
            "r2_job": 103526723770,
            "r2_decision": "HOMEBUILDER_PEER_RELATIVE_MARGINAL_TILT_REJECTED_AS_SPECIFIED",
            "r2_reason_for_child": "positive aggregate increment but insufficient chronology and symbol robustness; child changes stability architecture, not thresholds",
        },
        "source_preflight": SOURCE_PREFLIGHT,
        "claim": "Only peer-relative Homebuilder signals that remain positive across expanding, 504-session, and 252-session causal training windows are stable enough to justify a marginal tilt over equal weight.",
        "contract": {
            "development_symbols": list(base.DEV),
            "fresh_external_symbols_target_excluded": list(EXTERNAL),
            "common_first": frame.index[0].isoformat(),
            "common_last": frame.index[-1].isoformat(),
            "common_sessions": int(len(frame)),
            "features": list(base.FEATURES),
            "model": "three StandardScaler + Ridge(alpha=10) causal estimators",
            "training_windows_sessions": WINDOWS,
            "training_target": "future +1/fixed20 component return minus equal-weight other-development Homebuilders minus 50 bps switching hurdle",
            "candidate_rule": "all three model predictions > 0; equivalent to worst-case prediction > 0",
            "ranking": "descending worst-case prediction",
            "max_tilt_names": MAX_TILT_NAMES,
            "portfolio": "75% equal-weight fresh external core + 25% single-name consensus tilt",
            "common_rebalance_cost_bps": base.COMMON_REBALANCE_BPS,
            "marginal_switch_hurdle_bps": base.SWITCH_HURDLE_BPS,
            "decision_step_sessions": DECISION_STEP,
            "delay_sessions": base.DELAY,
            "hold_sessions": base.HOLD,
            "hyperparameter_search": False,
            "threshold_search": False,
            "holdout_target_training": False,
        },
        "acceptance_gate": {
            "minimum_decisions": MIN_DECISIONS,
            "minimum_tilt_decisions": MIN_TILT_DECISIONS,
            "annualized_increment_over_equal_core_gt_zero": True,
            "positive_incremental_folds_required": 4,
            "aggregate_selected_peer_excess_after50_bps_gt_zero": True,
            "external_symbol_rule": "both 2/2 fresh symbols must pass with >=5 selected events and positive conservative peer excess",
        },
        "metrics": {
            "decisions": len(decisions),
            "tilt_decisions": tilt_decisions,
            "abstention_rate": float(1.0 - tilt_decisions / len(decisions)),
            "baseline_equal_external_annualized": baseline_ann,
            "overlay_75core_25tilt_annualized": overlay_ann,
            "annualized_increment": annualized_increment,
            "mean_incremental_overlay_bps_per_decision": mean(incremental),
            "mean_selected_peer_excess_after50_bps": selected_mean,
            "positive_incremental_folds": positive_folds,
            "external_symbol_passes": symbol_passes,
        },
        "folds": folds,
        "external_symbols": symbols,
        "decision": decision,
        "boundaries": {
            "research_only": True,
            "allocation_authority": False,
            "promotion_authority": False,
            "strategy_spec_mutation": False,
            "runtime_mutation": False,
            "broker_authority": False,
            "live_trading_change": False,
        },
        "decisions": decisions,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    receipt = {k: payload[k] for k in ("schema", "decision", "metrics", "folds", "external_symbols", "source_preflight")}
    print("HOMEBUILDER_TEMPORAL_CONSENSUS_RECEIPT=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
