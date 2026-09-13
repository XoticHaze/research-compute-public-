#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "commandcenter.p04_r3_prospective_causal_packet.v1"
PROSPECTIVE_START_UTC = "2026-09-13T08:41:24Z"
FEATURE_SOURCE_SHA256 = "c04a95debfde500aa245d187a1d30620a88703113013a63af0c3553b0509e44e"
R2_CONSUMER_COMMIT = "166525387f182f158e94af52e26ce191f7e07180"
R3_CONSUMER_COMMIT = "cf50874dadb1a00ba795c24919209dd4c996c5b1"
H24_ARTIFACT_ID = 9881533231
H24_MODEL_SHA256 = "56131a75c1142974212baeedd793561543de907e1cc624a26fbc88dc4f27832b"
H24_MODEL_RECEIPT_SHA256 = "8c4547f0d63e3ee337e7825a9b7883fef330db0ce707822716473ce005763d3b"
H24_SURFACE_SHA256 = "99cea075c8f1b5ff23cc78e9e61ab94e4d9787ee076f0e2416b6a45c1123d32c"
H24_CUTPOINTS = [0.7398862034, 0.9889799108, 1.3446557524, 1.7889773747]
CAUSAL_REAUDIT_DIGEST = "sha256:757ee3c1a2a7cc07e1a0145e5fa808bc0d4e812d6a37c9ae225e2905f943529c"
K = 8
MIN_POSITIVE = 5
MIN_CONTEXT = 5
FEATURE_COUNT = 6

TOP_KEYS = {"schema", "anchors", "candidate_pool_complete", "candidate_pool_digest", "query", "candidate_pool"}
QUERY_KEYS = {
    "event_id", "trade_id", "event_timestamp", "source_contract", "dca_step",
    "state_bar_timestamp", "state_features", "query_year_scale", "regime",
    "h24_score_timestamp", "h24_score", "h24_bucket", "h24_model_sha256",
}
POOL_KEYS = {
    "event_id", "trade_id", "event_timestamp", "source_contract", "dca_step", "regime",
    "state_features", "source_trade_exit_timestamp", "incremental_exit_points",
    "positive_extra", "h24_bucket",
}


def _parse_ts(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be non-empty string")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    dt = datetime.fromisoformat(candidate)
    if dt.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(obj)).hexdigest()


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite numeric")
    return float(value)


def _vector(value: Any, name: str, *, positive: bool = False) -> list[float]:
    if not isinstance(value, list) or len(value) != FEATURE_COUNT:
        raise ValueError(f"{name} must contain exactly six features")
    out = [_number(v, name) for v in value]
    if positive and any(v <= 0 for v in out):
        raise ValueError(f"{name} must be strictly positive")
    return out


def _anchors() -> dict[str, Any]:
    return {
        "prospective_start_utc": PROSPECTIVE_START_UTC,
        "feature_source_12min_sha256": FEATURE_SOURCE_SHA256,
        "r2_consumer_commit": R2_CONSUMER_COMMIT,
        "r3_consumer_commit": R3_CONSUMER_COMMIT,
        "h24_artifact_id": H24_ARTIFACT_ID,
        "h24_model_sha256": H24_MODEL_SHA256,
        "h24_model_receipt_sha256": H24_MODEL_RECEIPT_SHA256,
        "h24_surface_sha256": H24_SURFACE_SHA256,
        "h24_cutpoints": H24_CUTPOINTS,
        "h24_cutpoint_policy": "quintiles of all accepted 2022Q1-2025Q4 chronology-OOS long-MAE predictions; frozen before prospective start",
        "causal_reaudit_digest": CAUSAL_REAUDIT_DIGEST,
        "cc75_state_bar_rule": "last fully completed same-contract 12Min bar strictly before DCA fill",
        "h24_state_bar_rule": "score H24 on the same prior fully completed decision bar; never on the DCA fill bar",
        "neighbor_resolution_rule": "source_trade_exit_timestamp < query event_timestamp",
    }


def _bucket(score: float) -> int:
    return 1 + sum(score >= cut for cut in H24_CUTPOINTS)


def _regime(features: list[float]) -> int:
    return 0 if features[5] >= 0 and features[1] >= 0 else (1 if features[5] < 0 and features[1] < 0 else 2)


def validate_and_evaluate(packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(packet, dict) or set(packet) != TOP_KEYS:
        raise ValueError("packet field set mismatch")
    if packet["schema"] != SCHEMA:
        raise ValueError("packet schema mismatch")
    if packet["anchors"] != _anchors():
        raise ValueError("anchor drift")
    if packet["candidate_pool_complete"] is not True:
        raise ValueError("candidate pool must be explicitly complete")
    pool = packet["candidate_pool"]
    if not isinstance(pool, list):
        raise ValueError("candidate_pool must be list")
    if packet["candidate_pool_digest"] != _digest(pool):
        raise ValueError("candidate pool digest mismatch")

    query = packet["query"]
    if not isinstance(query, dict) or set(query) != QUERY_KEYS:
        raise ValueError("query field set mismatch")
    query_ts = _parse_ts(query["event_timestamp"])
    state_ts = _parse_ts(query["state_bar_timestamp"])
    score_ts = _parse_ts(query["h24_score_timestamp"])
    if query_ts <= _parse_ts(PROSPECTIVE_START_UTC):
        raise ValueError("query is not prospective")
    if not state_ts < query_ts:
        raise ValueError("state bar must precede query")
    if (query_ts - state_ts).total_seconds() != 12 * 60:
        raise ValueError("query must be exactly next 12Min bar after decision state")
    if score_ts != state_ts:
        raise ValueError("H24 score must be bound to prior decision bar, not fill bar")
    if query["h24_model_sha256"] != H24_MODEL_SHA256:
        raise ValueError("H24 model identity drift")
    q = _vector(query["state_features"], "query state_features")
    scale = _vector(query["query_year_scale"], "query_year_scale", positive=True)
    if isinstance(query["dca_step"], bool) or not isinstance(query["dca_step"], int) or query["dca_step"] < 1:
        raise ValueError("invalid dca_step")
    if query["regime"] != _regime(q):
        raise ValueError("query regime mismatch")
    score = _number(query["h24_score"], "h24_score")
    if isinstance(query["h24_bucket"], bool) or query["h24_bucket"] != _bucket(score):
        raise ValueError("H24 bucket mismatch")

    clean = []
    seen = set()
    for row in pool:
        if not isinstance(row, dict) or set(row) != POOL_KEYS:
            raise ValueError("candidate row field set mismatch")
        if not isinstance(row["event_id"], str) or not row["event_id"] or row["event_id"] in seen:
            raise ValueError("candidate event identity invalid or duplicate")
        seen.add(row["event_id"])
        event_ts = _parse_ts(row["event_timestamp"])
        exit_ts = _parse_ts(row["source_trade_exit_timestamp"])
        if not event_ts < query_ts:
            raise ValueError("candidate event is not strictly prior to query")
        if not exit_ts < query_ts:
            raise ValueError("candidate outcome was unresolved at query time")
        if row["dca_step"] != query["dca_step"] or row["regime"] != query["regime"]:
            raise ValueError("candidate pool contains wrong step/regime")
        state = _vector(row["state_features"], "candidate state_features")
        increment = _number(row["incremental_exit_points"], "incremental_exit_points")
        if row["positive_extra"] is not (increment > 0):
            raise ValueError("positive_extra inconsistent with outcome")
        bucket = row["h24_bucket"]
        if bucket is not None and (isinstance(bucket, bool) or not isinstance(bucket, int) or bucket not in range(1, 6)):
            raise ValueError("candidate H24 bucket invalid")
        distance = math.sqrt(sum(((state[i] - q[i]) / scale[i]) ** 2 for i in range(FEATURE_COUNT)) / FEATURE_COUNT)
        clean.append((distance, event_ts, row["event_id"], row))
    if len(clean) < K:
        raise ValueError("fewer than eight resolved same-step same-regime candidates")

    clean.sort(key=lambda x: (x[0], x[1], x[2]))
    nearest = [x[3] for x in clean[:K]]
    mean_increment = sum(float(x["incremental_exit_points"]) for x in nearest) / K
    positives = sum(bool(x["positive_extra"]) for x in nearest)
    same_context = sum(x["h24_bucket"] == query["h24_bucket"] for x in nearest)
    r2_gate = mean_increment > 0 and positives >= MIN_POSITIVE
    r3_gate = same_context >= MIN_CONTEXT
    return {
        "schema": "commandcenter.p04_r3_prospective_causal_decision.v1",
        "query_event_id": query["event_id"],
        "candidate_pool_digest": packet["candidate_pool_digest"],
        "selected_neighbor_event_ids": [x["event_id"] for x in nearest],
        "selected_neighbor_digest": _digest([x["event_id"] for x in nearest]),
        "mean_incremental_exit_points": mean_increment,
        "positive_neighbors": positives,
        "same_h24_bucket_neighbors": same_context,
        "r2_candidate_gate": r2_gate,
        "r3_context_gate": r3_gate,
        "shadow_decision": "RELEASE" if r2_gate and r3_gate else "HOLD",
        "authority": {
            "research_shadow_only": True, "promotion_authority": False, "allocation_authority": False,
            "strategy_spec_write": False, "runtime_activation": False, "broker_submit": False,
            "live_trading_change": False,
        },
    }


def _self_test() -> None:
    query_ts = "2026-09-14T14:00:00+00:00"
    state_ts = "2026-09-14T13:48:00+00:00"
    query = {
        "event_id": "q1", "trade_id": "future-1", "event_timestamp": query_ts,
        "source_contract": "MNQ FUTURE", "dca_step": 1, "state_bar_timestamp": state_ts,
        "state_features": [0.01, 0.02, 0.03, 0.01, 0.02, 0.03],
        "query_year_scale": [1, 1, 1, 1, 1, 1], "regime": 0,
        "h24_score_timestamp": state_ts, "h24_score": 1.5, "h24_bucket": 4,
        "h24_model_sha256": H24_MODEL_SHA256,
    }
    pool = []
    for i in range(8):
        inc = 10.0 if i < 6 else -2.0
        pool.append({
            "event_id": f"n{i}", "trade_id": f"hist-{i}",
            "event_timestamp": f"2026-09-{i+1:02d}T12:00:00+00:00",
            "source_contract": "MNQ HIST", "dca_step": 1, "regime": 0,
            "state_features": [0.01 + i / 1000, 0.02, 0.03, 0.01, 0.02, 0.03],
            "source_trade_exit_timestamp": f"2026-09-{i+1:02d}T13:00:00+00:00",
            "incremental_exit_points": inc, "positive_extra": inc > 0,
            "h24_bucket": 4 if i < 5 else 3,
        })
    packet = {
        "schema": SCHEMA, "anchors": _anchors(), "candidate_pool_complete": True,
        "candidate_pool_digest": _digest(pool), "query": query, "candidate_pool": pool,
    }
    result = validate_and_evaluate(packet)
    assert result["shadow_decision"] == "RELEASE"
    assert result["positive_neighbors"] == 6
    assert result["same_h24_bucket_neighbors"] == 5

    bad = json.loads(json.dumps(packet))
    bad["candidate_pool"][0]["source_trade_exit_timestamp"] = query_ts
    bad["candidate_pool_digest"] = _digest(bad["candidate_pool"])
    try:
        validate_and_evaluate(bad)
    except ValueError as exc:
        assert "unresolved" in str(exc)
    else:
        raise AssertionError("unresolved neighbor was accepted")

    bad = json.loads(json.dumps(packet))
    bad["query"]["h24_score_timestamp"] = query_ts
    try:
        validate_and_evaluate(bad)
    except ValueError as exc:
        assert "prior decision bar" in str(exc)
    else:
        raise AssertionError("fill-bar H24 score was accepted")

    bad = json.loads(json.dumps(packet))
    bad["query"]["h24_bucket"] = 5
    try:
        validate_and_evaluate(bad)
    except ValueError as exc:
        assert "bucket mismatch" in str(exc)
    else:
        raise AssertionError("wrong H24 bucket was accepted")

    print("P04_R3_PROSPECTIVE_CAUSAL_GUARD=PASS")
    print(json.dumps(result, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["self-test", "evaluate"])
    ap.add_argument("--packet", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if args.command == "self-test":
        _self_test()
        return 0
    if args.packet is None:
        raise SystemExit("--packet is required")
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    result = validate_and_evaluate(packet)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
