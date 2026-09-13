from __future__ import annotations

"""Frozen P04 R3: R2 CC75 opportunity selection plus H24 risk-context concordance.

Scientific authority is frozen outside this execution-only consumer. The R2
same-step/same-regime six-feature nearest-neighbor selection is unchanged.
H24 is used only as a non-directional context-concordance requirement over the
same eight R2 neighbors. No threshold, K, feature, budget, chronology, sizing,
or directional high/low interpretation is owned here.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

EXPECTED_SCHEMA = "mnq-dca-reserve-release-r3-h24-concordance-envelope-v1"
EXPECTED_HARNESS = "mnq-dca-reserve-release-r3-h24-concordance-v1"
EXPECTED_PAYLOAD_SCHEMA = "mnq-dca-reserve-release-r3-h24-concordance-private-payload-v1"

EXPECTED_SOURCES = {
    "lifecycle": {
        "repo": "XoticHaze/mm-IBKR",
        "artifact_id": 9914932522,
        "archive_sha256": "9919084af1b6f0f2429f74acbc5972e719020189964cbecf374262e144a49e23",
    },
    "replay": {
        "repo": "XoticHaze/research-foundry",
        "artifact_id": 9881343496,
        "archive_sha256": "9cc2b62b864bab02fe7132eaae9b008aedd18e976152c3f2aa445c5bed6e4362",
    },
}
EXPECTED_PARITY = {
    "canonical_trades": 56,
    "canonical_dca_events": 42,
    "exact_gross_trades": 56,
    "mtm_within_0_25_points_trades": 55,
}
EXPECTED_FEATURE_CONTRACT = {
    "source_sha256": "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e",
    "features": ["return_5", "return_20", "return_60", "volatility_20", "distance_ma20", "distance_ma60"],
    "state_bar_rule": "last_fully_completed_12min_bar_strictly_before_dca_fill",
    "scale_rule": "per_query_year_std_from_all_12min_bars_in_strictly_prior_calendar_years",
    "regime_rule": "0_if_close_ge_ma60_and_return20_ge_0__1_if_close_lt_ma60_and_return20_lt_0__else_2",
    "distance_rule": "same_step_same_regime_then_rms_normalized_six_feature_distance",
}
EXPECTED_H24_CONTRACT = {
    "repo": "XoticHaze/research-foundry",
    "artifact_id": 9886127289,
    "surface_sha256": "99cea075c8f1b5ff23cc78e9e61ab94e4d9787ee076f0e2416b6a45c1123d32c",
    "bucket_rule": "prior_period_only_quintiles_of_pred_long_mae_z_h24",
    "join_rule": "exact_timestamp_and_source_contract",
    "exact_joins": 41,
    "bucketed_events": 38,
    "missing_exact_join": 1,
    "missing_prior_cutpoints": 3,
    "directional_interpretation": "NONE",
}

K = 8
MIN_POSITIVE = 5
MIN_H24_CONCORDANT = 5
FIXED_BUDGET_CONTRACTS = 4
CAPTURE_MIN = 0.50
ADDED_DRAWDOWN_RATIO_MAX = 0.70
POSITIVE_FOLDS_MIN = 2
VALID_H24_STATUSES = {
    "EXACT_PRIOR_PERIOD_QUINTILE",
    "MISSING_JOIN",
    "MISSING_PRIOR_CUTPOINTS",
}


def _validate_payload(payload: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {
        "schema",
        "source_artifacts",
        "packager_parity",
        "feature_contract",
        "h24_contract",
        "trades",
        "events",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise RuntimeError("R3 payload field set mismatch")
    if payload["schema"] != EXPECTED_PAYLOAD_SCHEMA:
        raise RuntimeError("R3 payload schema mismatch")
    if payload["source_artifacts"] != EXPECTED_SOURCES:
        raise RuntimeError("R3 R2-source provenance mismatch")
    if payload["packager_parity"] != EXPECTED_PARITY:
        raise RuntimeError("R3 packager parity mismatch")
    if payload["feature_contract"] != EXPECTED_FEATURE_CONTRACT:
        raise RuntimeError("R3 R2 feature contract mismatch")
    if payload["h24_contract"] != EXPECTED_H24_CONTRACT:
        raise RuntimeError("R3 H24 contract mismatch")

    trades = pd.DataFrame(payload["trades"])
    events = pd.DataFrame(payload["events"])
    if len(trades) != 56 or len(events) != 42:
        raise RuntimeError("R3 canonical population mismatch")
    if sorted(trades.trade_idx.astype(int).tolist()) != list(range(56)):
        raise RuntimeError("R3 trade identity mismatch")
    if events.duplicated(["trade_idx", "step"]).any():
        raise RuntimeError("R3 duplicate DCA identity")

    trades["entry"] = pd.to_datetime(trades.entry_fill_timestamp, utc=True)
    events["timestamp"] = pd.to_datetime(events.timestamp, utc=True)
    events["state_bar_timestamp"] = pd.to_datetime(events.state_bar_timestamp, utc=True)

    counts = events.groupby("trade_idx").size().to_dict()
    for row in trades.itertuples(index=False):
        if int(counts.get(int(row.trade_idx), 0)) != int(row.dca_count):
            raise RuntimeError("R3 DCA count mismatch")
        if int(row.baseline_final_qty) > FIXED_BUDGET_CONTRACTS:
            raise RuntimeError("R3 baseline exceeds fixed budget")
    if int(events.extra_final_qty.max()) > FIXED_BUDGET_CONTRACTS:
        raise RuntimeError("R3 counterfactual exceeds fixed budget")

    for row in events.itertuples(index=False):
        state = np.asarray(row.state_features, dtype=float)
        scale = np.asarray(row.query_year_scale, dtype=float)
        if (
            state.shape != (6,)
            or scale.shape != (6,)
            or not np.isfinite(state).all()
            or not np.isfinite(scale).all()
            or not (scale > 0).all()
        ):
            raise RuntimeError("R3 invalid state/scale vector")
        if int(row.regime) not in (0, 1, 2):
            raise RuntimeError("R3 invalid causal regime")
        if not row.state_bar_timestamp < row.timestamp:
            raise RuntimeError("R3 state bar is not strictly prior to DCA fill")
        if row.h24_status not in VALID_H24_STATUSES:
            raise RuntimeError("R3 invalid H24 status")
        if row.h24_status == "EXACT_PRIOR_PERIOD_QUINTILE":
            if pd.isna(row.h24_bucket) or int(row.h24_bucket) not in (1, 2, 3, 4, 5):
                raise RuntimeError("R3 exact H24 row missing valid bucket")
        elif not pd.isna(row.h24_bucket):
            raise RuntimeError("R3 missing-H24 row carries bucket")

    status_counts = Counter(events.h24_status.tolist())
    if status_counts != Counter({
        "EXACT_PRIOR_PERIOD_QUINTILE": 38,
        "MISSING_PRIOR_CUTPOINTS": 3,
        "MISSING_JOIN": 1,
    }):
        raise RuntimeError("R3 H24 status-count mismatch")
    buckets = Counter(int(x) for x in events.loc[events.h24_status == "EXACT_PRIOR_PERIOD_QUINTILE", "h24_bucket"])
    if buckets != Counter({5: 27, 4: 10, 3: 1}):
        raise RuntimeError("R3 H24 bucket-distribution mismatch")
    return trades, events


def _simulate(trades: pd.DataFrame, releases: dict[int, dict], first_dca: dict[int, dict]) -> pd.DataFrame:
    rows = []
    for tr in trades.itertuples(index=False):
        ti = int(tr.trade_idx)
        candidate = releases.get(ti)
        always = first_dca.get(ti)
        rows.append({
            "trade_idx": ti,
            "entry": tr.entry,
            "base_gross": float(tr.baseline_gross_contract_points),
            "base_min": float(tr.baseline_min_mtm_contract_points),
            "base_qty": int(tr.baseline_final_qty),
            "cand_gross": float(candidate["extra_gross_contract_points"]) if candidate else float(tr.baseline_gross_contract_points),
            "cand_min": float(candidate["extra_min_mtm_contract_points"]) if candidate else float(tr.baseline_min_mtm_contract_points),
            "cand_qty": int(candidate["extra_final_qty"]) if candidate else int(tr.baseline_final_qty),
            "always_gross": float(always["extra_gross_contract_points"]) if always else float(tr.baseline_gross_contract_points),
            "always_min": float(always["extra_min_mtm_contract_points"]) if always else float(tr.baseline_min_mtm_contract_points),
            "always_qty": int(always["extra_final_qty"]) if always else int(tr.baseline_final_qty),
            "released": candidate is not None,
        })
    return pd.DataFrame(rows)


def _metrics(evaluation: pd.DataFrame) -> dict:
    cand_increment = float((evaluation.cand_gross - evaluation.base_gross).sum())
    always_increment = float((evaluation.always_gross - evaluation.base_gross).sum())
    cand_dd = float((evaluation.base_min - evaluation.cand_min).mean())
    always_dd = float((evaluation.base_min - evaluation.always_min).mean())
    capture = cand_increment / always_increment if always_increment > 0 else None
    dd_ratio = cand_dd / always_dd if always_dd > 0 else None
    folds = []
    for fold, idx in enumerate(np.array_split(np.arange(len(evaluation)), 3), start=1):
        part = evaluation.iloc[idx]
        folds.append({
            "fold": fold,
            "trades": int(len(part)),
            "candidate_incremental_contract_points": float((part.cand_gross - part.base_gross).sum()),
            "always_release_incremental_contract_points": float((part.always_gross - part.base_gross).sum()),
            "candidate_mean_added_drawdown_contract_points": float((part.base_min - part.cand_min).mean()),
            "always_release_mean_added_drawdown_contract_points": float((part.base_min - part.always_min).mean()),
        })
    positive_folds = sum(x["candidate_incremental_contract_points"] > 0 for x in folds)
    return {
        "trades": int(len(evaluation)),
        "candidate_release_trades": int(evaluation.released.sum()),
        "baseline_total_contract_points": float(evaluation.base_gross.sum()),
        "candidate_total_contract_points": float(evaluation.cand_gross.sum()),
        "always_release_total_contract_points": float(evaluation.always_gross.sum()),
        "candidate_incremental_contract_points": cand_increment,
        "always_release_incremental_contract_points": always_increment,
        "candidate_capture_of_always_release_increment": capture,
        "baseline_mean_min_mtm_contract_points": float(evaluation.base_min.mean()),
        "candidate_mean_min_mtm_contract_points": float(evaluation.cand_min.mean()),
        "always_release_mean_min_mtm_contract_points": float(evaluation.always_min.mean()),
        "candidate_mean_added_drawdown_contract_points": cand_dd,
        "always_release_mean_added_drawdown_contract_points": always_dd,
        "candidate_added_drawdown_ratio_vs_always": dd_ratio,
        "baseline_average_peak_budget_utilization": float(evaluation.base_qty.mean() / FIXED_BUDGET_CONTRACTS),
        "candidate_average_peak_budget_utilization": float(evaluation.cand_qty.mean() / FIXED_BUDGET_CONTRACTS),
        "always_release_average_peak_budget_utilization": float(evaluation.always_qty.mean() / FIXED_BUDGET_CONTRACTS),
        "positive_candidate_increment_folds": int(positive_folds),
        "folds": folds,
    }


def evaluate(payload: dict) -> dict:
    trades, events = _validate_payload(payload)
    events = events.sort_values("timestamp").reset_index(drop=True)

    first_dca: dict[int, dict] = {}
    releases_r2: dict[int, dict] = {}
    releases_r3: dict[int, dict] = {}
    first_eligible = None
    eligible_events = 0
    r2_qualified_candidates = []

    for row in events.itertuples(index=False):
        ti = int(row.trade_idx)
        if int(row.step) == 1:
            first_dca[ti] = row._asdict()

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

        if ti in releases_r2:
            continue
        profitable_support = (
            float(nearest.incremental_exit_points.mean()) > 0
            and int(nearest.positive_extra.sum()) >= MIN_POSITIVE
        )
        if not profitable_support:
            continue

        candidate = row._asdict()
        releases_r2[ti] = candidate
        query_bucket = None if pd.isna(row.h24_bucket) else int(row.h24_bucket)
        same_bucket = 0
        if query_bucket is not None:
            same_bucket = int(
                sum(
                    (not pd.isna(x)) and int(x) == query_bucket
                    for x in nearest.h24_bucket.tolist()
                )
            )
        admitted = query_bucket is not None and same_bucket >= MIN_H24_CONCORDANT
        r2_qualified_candidates.append({
            "trade_idx": ti,
            "step": int(row.step),
            "timestamp": row.timestamp.isoformat(),
            "h24_status": row.h24_status,
            "h24_bucket": query_bucket,
            "same_h24_bucket_neighbors": same_bucket,
            "r3_admitted": bool(admitted),
        })
        if admitted:
            releases_r3[ti] = candidate

    if first_eligible is None:
        raise RuntimeError("R3 has no causal evaluation boundary")

    r2_eval = _simulate(trades, releases_r2, first_dca)
    r3_eval = _simulate(trades, releases_r3, first_dca)
    r2_eval = r2_eval[r2_eval.entry >= first_eligible].sort_values("entry").reset_index(drop=True)
    r3_eval = r3_eval[r3_eval.entry >= first_eligible].sort_values("entry").reset_index(drop=True)
    if len(r3_eval) < 30 or len(r2_eval) != len(r3_eval):
        raise RuntimeError("R3 insufficient/misaligned causal evaluation trades")

    r2m = _metrics(r2_eval)
    r3m = _metrics(r3_eval)
    supported = bool(
        r3m["candidate_incremental_contract_points"] > 0
        and r3m["candidate_capture_of_always_release_increment"] is not None
        and r3m["candidate_capture_of_always_release_increment"] >= CAPTURE_MIN
        and r3m["candidate_added_drawdown_ratio_vs_always"] is not None
        and r3m["candidate_added_drawdown_ratio_vs_always"] <= ADDED_DRAWDOWN_RATIO_MAX
        and r3m["positive_candidate_increment_folds"] >= POSITIVE_FOLDS_MIN
    )

    return {
        "schema": "public_research.mnq_dca_reserve_release_r3_h24_concordance_receipt.v1",
        "research_only": True,
        "scientific_id": "P04_MNQ_RESERVE_RELEASE_R3_RISK_CONTEXT_MATCH_20260912",
        "scientific_change": "retain unchanged R2 CC75 opportunity selector and require >=5 of the same 8 R2 neighbors to share the query event's frozen H24 risk bucket",
        "directional_h24_rule": "NONE",
        "rule": {
            "same_step_same_regime_nearest_prior_states": K,
            "minimum_profitable_comparables": MIN_POSITIVE,
            "minimum_same_h24_bucket_comparables": MIN_H24_CONCORDANT,
            "release_contracts": 1,
            "fixed_budget_contracts": FIXED_BUDGET_CONTRACTS,
            "missing_h24": "FAIL_CLOSED",
        },
        "h24_contract": EXPECTED_H24_CONTRACT,
        "parity": EXPECTED_PARITY,
        "evaluation_start": first_eligible.isoformat(),
        "eligible_dca_events": int(eligible_events),
        "r2_reference": r2m,
        "r3_evaluation": r3m,
        "r2_qualified_candidate_context": r2_qualified_candidates,
        "gates": {
            "candidate_incremental_contract_points_gt": 0,
            "capture_min": CAPTURE_MIN,
            "added_drawdown_ratio_max": ADDED_DRAWDOWN_RATIO_MAX,
            "positive_folds_min": POSITIVE_FOLDS_MIN,
        },
        "decision": "R3_H24_CONTEXT_CONCORDANCE_SUPPORTED" if supported else "R3_H24_CONTEXT_CONCORDANCE_NOT_SUPPORTED",
        "consequence": "Support is research-only evidence for the frozen conditional H24 context-concordance rule. Failure is terminal for this exact R3 without threshold, bucket, K, profitability, budget, chronology, feature, or directional rescue.",
        "promotion_authority": False,
        "allocation_authority": False,
        "runtime_authority": False,
        "broker_authority": False,
        "live_trading_change": False,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--envelope", required=True, type=Path)
    p.add_argument("--ciphertext", required=True, type=Path)
    p.add_argument("--private-key", required=True, type=Path)
    p.add_argument("--run-id", required=True)
    p.add_argument("--response-root", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    envelope = json.loads(args.envelope.read_text(encoding="utf-8"))
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=args.ciphertext.read_bytes(),
        private_key_path=args.private_key,
        expected_schema=EXPECTED_SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=EXPECTED_HARNESS,
        response_root=args.response_root,
    )
    payload = json.loads(plaintext.decode("utf-8"))
    result = evaluate(payload)
    result["private_payload_sha256"] = hashlib.sha256(plaintext).hexdigest()
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("MNQ_DCA_RESERVE_RELEASE_R3_H24_CONCORDANCE_RECEIPT=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
