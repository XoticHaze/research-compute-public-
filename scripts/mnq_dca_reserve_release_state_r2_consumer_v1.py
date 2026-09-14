from __future__ import annotations

"""State-aware R2 child of the terminal MNQ DCA reserve-release discriminator.

Scientific change versus R1 is intentionally narrow: same-step prior comparables are
restricted to the frozen CC75 causal regime and ranked with the frozen six-feature
CC75 normalized distance. Budget, K, profitability gate, chronology and economic
support gates are unchanged. This script owns research evidence only.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

EXPECTED_SCHEMA = "mnq-dca-reserve-release-state-r2-envelope-v1"
EXPECTED_HARNESS = "mnq-dca-reserve-release-state-r2-v1"
EXPECTED_PAYLOAD_SCHEMA = "mnq-dca-reserve-release-state-r2-compact-private-payload-v1"
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
K = 8
MIN_POSITIVE = 5
FIXED_BUDGET_CONTRACTS = 4


def evaluate(payload: dict) -> dict:
    required = {"schema", "source_artifacts", "packager_parity", "feature_contract", "trades", "events"}
    if set(payload) != required:
        raise RuntimeError("R2 compact payload field set mismatch")
    if payload["schema"] != EXPECTED_PAYLOAD_SCHEMA:
        raise RuntimeError("R2 compact payload schema mismatch")
    if payload["source_artifacts"] != EXPECTED_SOURCES:
        raise RuntimeError("R2 compact payload provenance mismatch")
    if payload["packager_parity"] != EXPECTED_PARITY:
        raise RuntimeError("R2 packager parity mismatch")
    if payload["feature_contract"] != EXPECTED_FEATURE_CONTRACT:
        raise RuntimeError("R2 feature contract mismatch")

    trades = pd.DataFrame(payload["trades"])
    events = pd.DataFrame(payload["events"])
    if len(trades) != 56 or len(events) != 42:
        raise RuntimeError("R2 canonical population mismatch")
    if sorted(trades.trade_idx.astype(int).tolist()) != list(range(56)):
        raise RuntimeError("R2 trade identity mismatch")
    trades["entry"] = pd.to_datetime(trades.entry_fill_timestamp, utc=True)
    events["timestamp"] = pd.to_datetime(events.timestamp, utc=True)
    events["state_bar_timestamp"] = pd.to_datetime(events.state_bar_timestamp, utc=True)
    if events.duplicated(["trade_idx", "step"]).any():
        raise RuntimeError("R2 duplicate DCA identity")
    counts = events.groupby("trade_idx").size().to_dict()
    for row in trades.itertuples(index=False):
        if int(counts.get(int(row.trade_idx), 0)) != int(row.dca_count):
            raise RuntimeError("R2 DCA count mismatch")
        if int(row.baseline_final_qty) > FIXED_BUDGET_CONTRACTS:
            raise RuntimeError("R2 baseline exceeds fixed budget")
    if int(events.extra_final_qty.max()) > FIXED_BUDGET_CONTRACTS:
        raise RuntimeError("R2 counterfactual exceeds fixed budget")

    for row in events.itertuples(index=False):
        state = np.asarray(row.state_features, dtype=float)
        scale = np.asarray(row.query_year_scale, dtype=float)
        if state.shape != (6,) or scale.shape != (6,) or not np.isfinite(state).all() or not np.isfinite(scale).all() or not (scale > 0).all():
            raise RuntimeError("R2 invalid state/scale vector")
        if int(row.regime) not in (0, 1, 2):
            raise RuntimeError("R2 invalid causal regime")
        if not row.state_bar_timestamp < row.timestamp:
            raise RuntimeError("R2 state bar is not strictly prior to DCA fill")

    events = events.sort_values("timestamp").reset_index(drop=True)
    releases: dict[int, dict] = {}
    first_dca: dict[int, dict] = {}
    first_eligible = None
    eligible_events = 0
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
            distance = float(np.sqrt(np.mean(((p - q) / scale) ** 2)))
            distances.append(distance)
        nearest = prior.assign(_distance=distances).nsmallest(K, "_distance")
        if int(row.trade_idx) in releases:
            continue
        if float(nearest.incremental_exit_points.mean()) > 0 and int(nearest.positive_extra.sum()) >= MIN_POSITIVE:
            releases[int(row.trade_idx)] = row._asdict()
    if first_eligible is None:
        raise RuntimeError("R2 has no causal evaluation boundary")

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
    if len(evaluation) < 30:
        raise RuntimeError("R2 insufficient causal evaluation trades")

    cand_increment = float((evaluation.cand_gross - evaluation.base_gross).sum())
    always_increment = float((evaluation.always_gross - evaluation.base_gross).sum())
    cand_dd_penalty = float((evaluation.base_min - evaluation.cand_min).mean())
    always_dd_penalty = float((evaluation.base_min - evaluation.always_min).mean())
    capture = cand_increment / always_increment if always_increment > 0 else None
    dd_ratio = cand_dd_penalty / always_dd_penalty if always_dd_penalty > 0 else None
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
    positive_folds = sum(f["candidate_incremental_contract_points"] > 0 for f in folds)
    supported = bool(
        cand_increment > 0
        and capture is not None and capture >= 0.50
        and dd_ratio is not None and dd_ratio <= 0.70
        and positive_folds >= 2
    )
    return {
        "schema": "public_research.mnq_dca_reserve_release_state_r2_receipt.v1",
        "research_only": True,
        "scientific_parent": "MNQ DCA fixed-budget reserve release R1 terminal rejection + CC75 state mechanism",
        "scientific_change": "replace improvement_bps_only nearest-neighbor distance with frozen CC75 same-regime normalized six-feature state distance",
        "rule": {
            "same_step_same_regime_nearest_prior_states": K,
            "minimum_profitable_comparables": MIN_POSITIVE,
            "release_contracts": 1,
            "fixed_budget_contracts": FIXED_BUDGET_CONTRACTS,
        },
        "feature_contract": EXPECTED_FEATURE_CONTRACT,
        "parity": EXPECTED_PARITY,
        "evaluation": {
            "start": first_eligible.isoformat(),
            "trades": int(len(evaluation)),
            "eligible_dca_events": int(eligible_events),
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
            "candidate_mean_added_drawdown_contract_points": cand_dd_penalty,
            "always_release_mean_added_drawdown_contract_points": always_dd_penalty,
            "candidate_added_drawdown_ratio_vs_always": dd_ratio,
            "baseline_average_peak_budget_utilization": float(evaluation.base_qty.mean() / FIXED_BUDGET_CONTRACTS),
            "candidate_average_peak_budget_utilization": float(evaluation.cand_qty.mean() / FIXED_BUDGET_CONTRACTS),
            "always_release_average_peak_budget_utilization": float(evaluation.always_qty.mean() / FIXED_BUDGET_CONTRACTS),
            "positive_candidate_increment_folds": int(positive_folds),
            "folds": folds,
        },
        "decision": "STATE_AWARE_RESERVE_RELEASE_SUPPORTED" if supported else "STATE_AWARE_RESERVE_RELEASE_NOT_SUPPORTED",
        "consequence": "Support requires the unchanged R1 economic gates: >=50% of naive incremental value, <=70% of naive added drawdown, and positive incremental value in >=2/3 chronology blocks. Failure may not be rescued by K/profitability-threshold tuning; interpret return-capture and drawdown gates separately to identify whether opportunity state or downside state remains deficient.",
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
    print("MNQ_DCA_RESERVE_RELEASE_STATE_R2_RECEIPT=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
