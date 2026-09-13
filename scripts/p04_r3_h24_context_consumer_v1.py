from __future__ import annotations

"""Frozen P04 R3 risk-context concordance evaluator.

This evaluator intentionally does not assign direction to H24 buckets. It first
replays the unchanged R2 CC75 opportunity-state rule and requires the known R2
checksum, then applies exactly one additional condition: at least 5 of the same
8 R2 neighbors must share the query event's already-frozen H24 bucket.

Research evidence only. No StrategySpec/runtime/allocation/broker/live authority.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

PAYLOAD_SCHEMA = "p04-r3-h24-context-compact-private-payload-v1"
RESULT_SCHEMA = "public_research.p04_r3_h24_context_concordance_receipt.v1"
K = 8
MIN_PROFITABLE = 5
MIN_CONTEXT = 5
FIXED_BUDGET = 4
FEATURES = [
    "return_5",
    "return_20",
    "return_60",
    "volatility_20",
    "distance_ma20",
    "distance_ma60",
]
EXPECTED_PARITY = {
    "canonical_trades": 56,
    "canonical_dca_events": 42,
    "exact_gross_trades": 56,
    "mtm_within_0_25_points_trades": 55,
    "h24_exact_joins": 41,
    "h24_bucketed_events": 38,
}
EXPECTED_R2 = {
    "causal_start": "2023-01-19T11:24:00+00:00",
    "evaluation_trades": 45,
    "eligible_dca_events": 26,
    "candidate_release_trades": 18,
    "candidate_incremental_contract_points": 4985.25,
    "always_release_incremental_contract_points": 6133.25,
    "candidate_capture_of_always_release_increment": 0.8128235437981495,
    "candidate_mean_added_drawdown_contract_points": 253.98888888888888,
    "always_release_mean_added_drawdown_contract_points": 278.6388888888889,
    "candidate_added_drawdown_ratio_vs_always": 0.9115342438440832,
    "positive_candidate_increment_folds": 3,
}


def _same_bucket_count(nearest: pd.DataFrame, bucket: object) -> int:
    if bucket is None or pd.isna(bucket):
        return 0
    return int((nearest["h24_bucket"] == bucket).sum())


def _simulate(trades: pd.DataFrame, events: pd.DataFrame, require_context: bool) -> dict:
    events = events.sort_values("timestamp").reset_index(drop=True)
    releases: dict[int, dict] = {}
    first_dca: dict[int, dict] = {}
    first_eligible = None
    eligible_events = 0
    r2_candidate_events = 0
    context_supported_events = 0

    for row in events.itertuples(index=False):
        if int(row.step) == 1:
            first_dca[int(row.trade_idx)] = row._asdict()
        prior = events[
            (events.timestamp < row.timestamp)
            & (events.step == row.step)
            & (events.regime == row.regime)
        ]
        if len(prior) < K:
            continue
        eligible_events += 1
        if first_eligible is None:
            first_eligible = row.timestamp

        q = np.asarray(row.state_features, dtype=float)
        scale = np.asarray(row.query_year_scale, dtype=float)
        distances = []
        for prior_row in prior.itertuples(index=False):
            p = np.asarray(prior_row.state_features, dtype=float)
            distances.append(float(np.sqrt(np.mean(((p - q) / scale) ** 2))))
        nearest = prior.assign(_distance=distances).nsmallest(K, "_distance")

        r2_gate = bool(
            float(nearest.incremental_exit_points.mean()) > 0
            and int(nearest.positive_extra.sum()) >= MIN_PROFITABLE
        )
        if r2_gate:
            r2_candidate_events += 1
        same_bucket = _same_bucket_count(nearest, row.h24_bucket)
        context_gate = bool(row.h24_bucket is not None and not pd.isna(row.h24_bucket) and same_bucket >= MIN_CONTEXT)
        if context_gate:
            context_supported_events += 1

        ti = int(row.trade_idx)
        if ti in releases:
            continue
        if r2_gate and (context_gate if require_context else True):
            releases[ti] = row._asdict()

    if first_eligible is None:
        raise RuntimeError("no causal evaluation boundary")

    sim = []
    for row in trades.itertuples(index=False):
        ti = int(row.trade_idx)
        candidate = releases.get(ti)
        always = first_dca.get(ti)
        sim.append({
            "trade_idx": ti,
            "entry": row.entry,
            "base_gross": float(row.baseline_gross_contract_points),
            "base_min": float(row.baseline_min_mtm_contract_points),
            "base_qty": int(row.baseline_final_qty),
            "cand_gross": float(candidate["extra_gross_contract_points"]) if candidate else float(row.baseline_gross_contract_points),
            "cand_min": float(candidate["extra_min_mtm_contract_points"]) if candidate else float(row.baseline_min_mtm_contract_points),
            "cand_qty": int(candidate["extra_final_qty"]) if candidate else int(row.baseline_final_qty),
            "always_gross": float(always["extra_gross_contract_points"]) if always else float(row.baseline_gross_contract_points),
            "always_min": float(always["extra_min_mtm_contract_points"]) if always else float(row.baseline_min_mtm_contract_points),
            "always_qty": int(always["extra_final_qty"]) if always else int(row.baseline_final_qty),
            "released": candidate is not None,
        })
    sim = pd.DataFrame(sim)
    evaluation = sim[sim.entry >= first_eligible].sort_values("entry").reset_index(drop=True)
    if len(evaluation) != 45:
        raise RuntimeError("causal evaluation population drift")

    cand_increment = float((evaluation.cand_gross - evaluation.base_gross).sum())
    always_increment = float((evaluation.always_gross - evaluation.base_gross).sum())
    cand_dd = float((evaluation.base_min - evaluation.cand_min).mean())
    always_dd = float((evaluation.base_min - evaluation.always_min).mean())
    capture = cand_increment / always_increment
    dd_ratio = cand_dd / always_dd

    folds = []
    for fold, indices in enumerate(np.array_split(np.arange(len(evaluation)), 3), start=1):
        part = evaluation.iloc[indices]
        folds.append({
            "fold": fold,
            "trades": int(len(part)),
            "candidate_incremental_contract_points": float((part.cand_gross - part.base_gross).sum()),
            "always_release_incremental_contract_points": float((part.always_gross - part.base_gross).sum()),
            "candidate_mean_added_drawdown_contract_points": float((part.base_min - part.cand_min).mean()),
            "always_release_mean_added_drawdown_contract_points": float((part.base_min - part.always_min).mean()),
        })
    return {
        "causal_start": first_eligible.isoformat(),
        "evaluation_trades": int(len(evaluation)),
        "eligible_dca_events": int(eligible_events),
        "r2_candidate_events": int(r2_candidate_events),
        "context_supported_events": int(context_supported_events),
        "candidate_release_trades": int(evaluation.released.sum()),
        "released_trade_indices": [int(x) for x in evaluation.loc[evaluation.released, "trade_idx"].tolist()],
        "candidate_incremental_contract_points": cand_increment,
        "always_release_incremental_contract_points": always_increment,
        "candidate_capture_of_always_release_increment": capture,
        "candidate_mean_added_drawdown_contract_points": cand_dd,
        "always_release_mean_added_drawdown_contract_points": always_dd,
        "candidate_added_drawdown_ratio_vs_always": dd_ratio,
        "positive_candidate_increment_folds": int(sum(f["candidate_incremental_contract_points"] > 0 for f in folds)),
        "folds": folds,
    }


def _require_close(actual: float, expected: float, name: str, tol: float = 1e-9) -> None:
    if abs(float(actual) - float(expected)) > tol:
        raise RuntimeError(f"R2 checksum mismatch for {name}: {actual} != {expected}")


def evaluate(payload: dict) -> dict:
    if payload.get("schema") != PAYLOAD_SCHEMA:
        raise RuntimeError("payload schema mismatch")
    if payload.get("authority") != "research_only":
        raise RuntimeError("payload authority mismatch")
    if payload.get("parity") != EXPECTED_PARITY:
        raise RuntimeError("frozen parity mismatch")

    trades = pd.DataFrame(payload["trades"])
    events = pd.DataFrame(payload["events"])
    if len(trades) != 56 or len(events) != 42:
        raise RuntimeError("canonical population mismatch")
    trades["entry"] = pd.to_datetime(trades.entry_fill_timestamp, utc=True)
    events["timestamp"] = pd.to_datetime(events.timestamp, utc=True)
    events["state_bar_timestamp"] = pd.to_datetime(events.state_bar_timestamp, utc=True)

    if events.duplicated(["trade_idx", "step"]).any():
        raise RuntimeError("duplicate DCA identity")
    for row in events.itertuples(index=False):
        state = np.asarray(row.state_features, dtype=float)
        scale = np.asarray(row.query_year_scale, dtype=float)
        if state.shape != (6,) or scale.shape != (6,):
            raise RuntimeError("invalid state vector shape")
        if not np.isfinite(state).all() or not np.isfinite(scale).all() or not (scale > 0).all():
            raise RuntimeError("invalid state/scale values")
        if int(row.regime) not in (0, 1, 2):
            raise RuntimeError("invalid regime")
        if not row.state_bar_timestamp < row.timestamp:
            raise RuntimeError("state bar is not strictly prior")
        if row.h24_bucket is not None and not pd.isna(row.h24_bucket):
            if int(row.h24_bucket) not in (1, 2, 3, 4, 5):
                raise RuntimeError("invalid frozen H24 bucket")

    r2 = _simulate(trades, events, require_context=False)
    for name, expected in EXPECTED_R2.items():
        actual = r2[name]
        if isinstance(expected, str):
            if actual != expected:
                raise RuntimeError(f"R2 checksum mismatch for {name}: {actual} != {expected}")
        elif isinstance(expected, int):
            if int(actual) != expected:
                raise RuntimeError(f"R2 checksum mismatch for {name}: {actual} != {expected}")
        else:
            _require_close(actual, expected, name)

    r3 = _simulate(trades, events, require_context=True)
    supported = bool(
        r3["candidate_incremental_contract_points"] > 0
        and r3["candidate_capture_of_always_release_increment"] >= 0.50
        and r3["candidate_added_drawdown_ratio_vs_always"] <= 0.70
        and r3["positive_candidate_increment_folds"] >= 2
    )
    return {
        "schema": RESULT_SCHEMA,
        "scientific_id": "P04_MNQ_RESERVE_RELEASE_R3_RISK_CONTEXT_MATCH_20260912",
        "research_only": True,
        "parity": EXPECTED_PARITY,
        "r2_checksum": r2,
        "r3_evaluation": r3,
        "rule": {
            "same_r2_neighbors": K,
            "minimum_profitable_neighbors": MIN_PROFITABLE,
            "minimum_same_h24_bucket_neighbors": MIN_CONTEXT,
            "fixed_budget_contracts": FIXED_BUDGET,
            "directional_h24_rule": False,
            "missing_h24": "fail_closed",
        },
        "decision": "R3_H24_RISK_CONTEXT_CONCORDANCE_SUPPORTED_FOR_FURTHER_RESERVE_RELEASE_RESEARCH" if supported else "R3_H24_RISK_CONTEXT_CONCORDANCE_REJECTED",
        "promotion_authority": False,
        "allocation_authority": False,
        "strategy_spec_write": False,
        "runtime_activation": False,
        "broker_submit": False,
        "live_trading_change": False,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--payload", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    result = evaluate(json.loads(args.payload.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("P04_R3_H24_CONTEXT_RECEIPT=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
