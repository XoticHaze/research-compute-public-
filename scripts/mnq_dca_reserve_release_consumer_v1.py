from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext

EXPECTED_SCHEMA = "mnq-dca-reserve-release-envelope-v1"
EXPECTED_HARNESS = "mnq-dca-reserve-release-v1"
EXPECTED_PAYLOAD_SCHEMA = "mnq-dca-reserve-release-private-payload-v1"
EXPECTED_SOURCES = {
    "lifecycle": {"repo": "XoticHaze/mm-IBKR", "artifact_id": 9914932522, "archive_sha256": "9919084af1b6f0f2429f74acbc5972e719020189964cbecf374262e144a49e23"},
    "replay": {"repo": "XoticHaze/research-foundry", "artifact_id": 9881343496, "archive_sha256": "9cc2b62b864bab02fe7132eaae9b008aedd18e976152c3f2aa445c5bed6e4362"},
}
K = 8
MIN_POSITIVE = 5
FIXED_BUDGET_CONTRACTS = 4


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _fills(value):
    return value if isinstance(value, list) else json.loads(value)


def _mtm(trade: dict, bars: pd.DataFrame, extra: dict | None) -> tuple[float, float, int]:
    fills = list(_fills(trade["fills"]))
    if extra is not None:
        fills.append({"timestamp": extra["timestamp"], "price": extra["add_price"], "qty": 1})
    entry = pd.Timestamp(trade["entry_fill_timestamp"])
    exit_ = pd.Timestamp(trade["exit_fill_timestamp"])
    b = bars[(bars.source_contract == trade["source_contract"]) & (bars.timestamp >= entry) & (bars.timestamp <= exit_)]
    if b.empty:
        raise RuntimeError("trade has no replay bars")
    gross = sum(float(f["qty"]) * (float(trade["exit_price"]) - float(f["price"])) for f in fills)
    minimum = np.inf
    for row in b.itertuples(index=False):
        active = [f for f in fills if pd.Timestamp(f["timestamp"]) <= row.timestamp]
        if active:
            minimum = min(minimum, sum(float(f["qty"]) * (float(row.low) - float(f["price"])) for f in active))
    return float(gross), float(minimum), int(sum(int(f["qty"]) for f in fills))


def evaluate(payload: dict) -> dict:
    if set(payload) != {"schema", "source_artifacts", "trades", "bars"}:
        raise RuntimeError("private payload field set mismatch")
    if payload["schema"] != EXPECTED_PAYLOAD_SCHEMA or payload["source_artifacts"] != EXPECTED_SOURCES:
        raise RuntimeError("private payload provenance mismatch")
    trades = payload["trades"]
    if not isinstance(trades, list) or len(trades) != 56:
        raise RuntimeError("expected exact 56-trade canonical lifecycle")
    bars = pd.DataFrame(payload["bars"])
    if not {"timestamp", "source_contract", "low", "high"}.issubset(bars.columns):
        raise RuntimeError("replay bar schema mismatch")
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    if bars.duplicated(["source_contract", "timestamp"]).any():
        raise RuntimeError("duplicate replay bar identity")

    events = []
    exact_gross = 0
    exact_min = 0
    for ti, trade in enumerate(trades):
        fills = _fills(trade["fills"])
        dcas = [f for f in fills if f.get("kind") == "dca"]
        if int(trade["dca_count"]) != len(dcas):
            raise RuntimeError("DCA count parity failed")
        gross, minimum, qty = _mtm(trade, bars, None)
        if abs(gross - float(trade["baseline_gross_contract_points"])) <= 1e-9:
            exact_gross += 1
        if abs(minimum - float(trade["baseline_min_mtm_contract_points"])) <= 0.25:
            exact_min += 1
        if qty != int(trade["final_qty"]):
            raise RuntimeError("final quantity parity failed")
        for step, fill in enumerate(dcas, start=1):
            ts = pd.Timestamp(fill["timestamp"])
            add = float(fill["price"])
            entry = float(trade["first_entry_price"])
            events.append({
                "trade_idx": ti,
                "timestamp": ts,
                "step": step,
                "improvement_bps": (entry - add) / entry * 10000.0,
                "add_price": add,
                "incremental_exit_points": float(trade["exit_price"]) - add,
                "positive_extra": float(trade["exit_price"]) > add,
            })
    if exact_gross != 56 or exact_min < 55 or len(events) != 42:
        raise RuntimeError(f"canonical path parity failed gross={exact_gross} min={exact_min} dca={len(events)}")

    ev = pd.DataFrame(events).sort_values("timestamp").reset_index(drop=True)
    releases: dict[int, dict] = {}
    first_dca: dict[int, dict] = {}
    first_eligible = None
    for row in ev.itertuples(index=False):
        if row.step == 1:
            first_dca[int(row.trade_idx)] = row._asdict()
        prior = ev[(ev.timestamp < row.timestamp) & (ev.step == row.step)]
        if len(prior) < K:
            continue
        if first_eligible is None:
            first_eligible = row.timestamp
        nearest = prior.assign(dist=(prior.improvement_bps - row.improvement_bps).abs()).nsmallest(K, "dist")
        if int(row.trade_idx) in releases:
            continue
        if float(nearest.incremental_exit_points.mean()) > 0 and int(nearest.positive_extra.sum()) >= MIN_POSITIVE:
            releases[int(row.trade_idx)] = row._asdict()
    if first_eligible is None:
        raise RuntimeError("no causal evaluation boundary")

    sim = []
    for ti, trade in enumerate(trades):
        base_gross, base_min, base_qty = _mtm(trade, bars, None)
        cand_extra = releases.get(ti)
        cand_gross, cand_min, cand_qty = _mtm(trade, bars, cand_extra)
        always_extra = first_dca.get(ti)
        always_gross, always_min, always_qty = _mtm(trade, bars, always_extra)
        if max(base_qty, cand_qty, always_qty) > FIXED_BUDGET_CONTRACTS:
            raise RuntimeError("fixed contract budget exceeded")
        sim.append({
            "trade_idx": ti,
            "entry": pd.Timestamp(trade["entry_fill_timestamp"]),
            "base_gross": base_gross, "cand_gross": cand_gross, "always_gross": always_gross,
            "base_min": base_min, "cand_min": cand_min, "always_min": always_min,
            "base_qty": base_qty, "cand_qty": cand_qty, "always_qty": always_qty,
            "released": cand_extra is not None,
        })
    sim = pd.DataFrame(sim)
    evaluation = sim[sim.entry >= first_eligible].sort_values("entry").reset_index(drop=True)
    if len(evaluation) < 30:
        raise RuntimeError("insufficient evaluation trades")

    cand_increment = float((evaluation.cand_gross - evaluation.base_gross).sum())
    always_increment = float((evaluation.always_gross - evaluation.base_gross).sum())
    cand_dd_penalty = float((evaluation.base_min - evaluation.cand_min).mean())
    always_dd_penalty = float((evaluation.base_min - evaluation.always_min).mean())
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
    capture = cand_increment / always_increment if always_increment > 0 else None
    dd_ratio = cand_dd_penalty / always_dd_penalty if always_dd_penalty > 0 else None
    positive_folds = sum(f["candidate_incremental_contract_points"] > 0 for f in folds)
    supported = bool(cand_increment > 0 and capture is not None and capture >= 0.50 and dd_ratio is not None and dd_ratio <= 0.70 and positive_folds >= 2)
    return {
        "schema": "public_research.mnq_dca_reserve_release_receipt.v1",
        "research_only": True,
        "scientific_parent": "MNQ DCA fixed-budget reserve release",
        "private_payload_sha256": payload["private_payload_sha256"] if "private_payload_sha256" in payload else None,
        "rule": {"same_step_nearest_prior_states": K, "minimum_profitable_comparables": MIN_POSITIVE, "release_contracts": 1, "fixed_budget_contracts": FIXED_BUDGET_CONTRACTS},
        "parity": {"canonical_trades": 56, "canonical_dca_events": 42, "exact_gross_trades": exact_gross, "mtm_within_0_25_points_trades": exact_min},
        "evaluation": {
            "start": first_eligible.isoformat(),
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
            "candidate_mean_added_drawdown_contract_points": cand_dd_penalty,
            "always_release_mean_added_drawdown_contract_points": always_dd_penalty,
            "candidate_added_drawdown_ratio_vs_always": dd_ratio,
            "baseline_average_peak_budget_utilization": float(evaluation.base_qty.mean() / FIXED_BUDGET_CONTRACTS),
            "candidate_average_peak_budget_utilization": float(evaluation.cand_qty.mean() / FIXED_BUDGET_CONTRACTS),
            "always_release_average_peak_budget_utilization": float(evaluation.always_qty.mean() / FIXED_BUDGET_CONTRACTS),
            "positive_candidate_increment_folds": positive_folds,
            "folds": folds,
        },
        "decision": "COMPARABLE_STATE_RESERVE_RELEASE_SUPPORTED" if supported else "COMPARABLE_STATE_RESERVE_RELEASE_NOT_SUPPORTED",
        "consequence": "Support requires retaining at least half of naive reserve-release incremental contract points while using no more than 70% of its added drawdown and staying positive in at least two of three chronological blocks. Failure rejects this minimal price-path comparable-state rule without implying DCA itself is invalid; a future reserve-release child must add genuinely new state/regime information rather than tune K or thresholds.",
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
    plaintext = decrypt_assembled_ciphertext(envelope=envelope, ciphertext=args.ciphertext.read_bytes(), private_key_path=args.private_key, expected_schema=EXPECTED_SCHEMA, expected_run_id=args.run_id, expected_harness=EXPECTED_HARNESS, response_root=args.response_root)
    payload = json.loads(plaintext.decode("utf-8"))
    # Bind receipt to decrypted bytes without exposing payload.
    payload["private_payload_sha256"] = _sha(plaintext)
    result = evaluate(payload)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("MNQ_DCA_RESERVE_RELEASE_RECEIPT=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
