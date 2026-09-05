from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from strategies.python.crw_score_multi_mode import CrwScoreMultiModeStrategy

RUNTIME_ID = "crw_mnq_12m_proven_exec"
EXPECTED_STRATEGY_SPEC_DIGEST = "3680e21e3bdbc38a1729cc38fd0c9d42d66242d970cce1617bbdd71c761a1ac6"
EXPECTED_STRATEGY_ID = "crw_score_multi_mode"
EXPECTED_TIMEFRAME = "12Min"


def load_runtime_authority(path: Path, *, runtime_id: str = RUNTIME_ID, expected_digest: str = EXPECTED_STRATEGY_SPEC_DIGEST) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("runtime_ids") or []
    runtime = next((row for row in rows if row.get("runtime_id") == runtime_id), None)
    if runtime is None:
        raise ValueError(f"runtime_id not found: {runtime_id}")
    if runtime.get("strategy_id") != EXPECTED_STRATEGY_ID:
        raise ValueError(f"unexpected strategy_id: {runtime.get('strategy_id')}")
    if runtime.get("timeframe") != EXPECTED_TIMEFRAME:
        raise ValueError(f"unexpected timeframe: {runtime.get('timeframe')}")
    actual_digest = str(runtime.get("strategy_spec_digest") or "")
    if actual_digest != expected_digest:
        raise ValueError(f"StrategySpec digest mismatch: expected {expected_digest}, got {actual_digest}")
    spec = runtime.get("strategy_spec") or {}
    params = spec.get("parameters")
    if not isinstance(params, dict) or not params:
        raise ValueError("canonical StrategySpec parameters missing")
    return runtime


def _candidate_timestamps(frame: pd.DataFrame) -> pd.DatetimeIndex:
    if "timestamp" not in frame.columns:
        raise ValueError("candidate input requires timestamp")
    ts = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if ts.duplicated().any():
        raise ValueError("candidate timestamps must be unique")
    return pd.DatetimeIndex(ts)


def replay_flat_entry_candidates(bars: pd.DataFrame, candidates: pd.DataFrame, *, strategy_params: dict[str, Any]) -> pd.DataFrame:
    work = bars.copy()
    if "timestamp" not in work.columns:
        raise ValueError("bars require timestamp")
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="raise")
    if work["timestamp"].duplicated().any() or not work["timestamp"].is_monotonic_increasing:
        raise ValueError("bars must have unique increasing timestamps")
    needed = _candidate_timestamps(candidates)
    positions = pd.Series(work.index.to_numpy(), index=work["timestamp"])
    missing = needed[~needed.isin(positions.index)]
    if len(missing):
        raise ValueError(f"{len(missing)} candidate timestamps absent from bars")
    strategy = CrwScoreMultiModeStrategy(config=dict(strategy_params))
    candidate_meta = candidates.copy()
    candidate_meta["timestamp"] = needed
    candidate_meta = candidate_meta.set_index("timestamp", drop=False)
    rows: list[dict[str, Any]] = []
    for timestamp in needed:
        pos = int(positions.loc[timestamp])
        prefix = work.iloc[: pos + 1]
        conditions = strategy.evaluate_conditions(prefix)
        entry = conditions.get("entry_long") or {}
        filters = conditions.get("filters") or {}
        values = conditions.get("current_values") or {}
        row: dict[str, Any] = {
            "timestamp": timestamp.isoformat(),
            "canonical_entry_ready": bool(entry.get("passed")),
            "canonical_crw_score": values.get("CRW_SCORE"),
            "canonical_entry_filter_ok": filters.get("entry_filter_ok"),
            "canonical_score_entry": filters.get("score_entry"),
            "canonical_position_state_authoritative": bool((conditions.get("position") or {}).get("authoritative")),
            "history_rows": int(len(prefix)),
        }
        source = candidate_meta.loc[timestamp]
        for key in ("projected_state", "projected_entry_ready", "projected_crw_score", "source_contract"):
            if key in source.index:
                value = source[key]
                if pd.notna(value):
                    row[key] = value.item() if hasattr(value, "item") else value
        if "projected_entry_ready" in row:
            row["projected_entry_match"] = bool(row["canonical_entry_ready"] == bool(row["projected_entry_ready"]))
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only canonical MM CRW research replay")
    ap.add_argument("--bars", type=Path, required=True)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--runtime-config", type=Path, default=Path("config/selected_runtime_universe_14tu.json"))
    ap.add_argument("--runtime-id", default=RUNTIME_ID)
    ap.add_argument("--expected-strategy-spec-digest", default=EXPECTED_STRATEGY_SPEC_DIGEST)
    args = ap.parse_args()
    runtime = load_runtime_authority(args.runtime_config, runtime_id=args.runtime_id, expected_digest=args.expected_strategy_spec_digest)
    bars = pd.read_csv(args.bars)
    candidates = pd.read_csv(args.candidates)
    replay = replay_flat_entry_candidates(bars, candidates, strategy_params=dict(runtime["strategy_spec"]["parameters"]))
    mismatch_count = int((~replay["projected_entry_match"]).sum()) if "projected_entry_match" in replay.columns else None
    receipt = {"schema":"mm.mnq_crw_canonical_replay.v1","research_only":True,"runtime_id":args.runtime_id,"strategy_id":EXPECTED_STRATEGY_ID,"timeframe":EXPECTED_TIMEFRAME,"strategy_spec_digest":runtime["strategy_spec_digest"],"candidate_rows":int(len(replay)),"projection_match_checked":mismatch_count is not None,"projection_mismatch_count":mismatch_count,"flat_state_only":True,"dca_exit_replay":False,"runtime_mutation":False,"broker_action":False,"live_trading_change":False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    replay.to_csv(args.output, index=False)
    args.output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if mismatch_count:
        raise SystemExit(f"canonical replay disagreed with projection on {mismatch_count} candidate rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
