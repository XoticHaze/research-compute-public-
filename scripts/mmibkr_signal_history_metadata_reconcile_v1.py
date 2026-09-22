from __future__ import annotations

"""Reconcile validated signal-history metadata onto an existing canonical cache.

This helper is intentionally metadata-only. It is executed inside the exact private
MM-IBKR image so runtime bindings, warmup contracts, and contract-digest authority
come from private source. It never overwrites market-data bars.

Use case:
- a validated historical artifact is re-ingested on an isolated clean data root;
- an existing forward cache already contains later broker history;
- overlapping OHLCV differs, so the canonical ingest correctly refuses a merge;
- signal-history contract metadata is still needed for durable futures history.

The helper validates both sides independently, records the exact expected overlap
conflicts, preserves the existing canonical forward cache byte-for-byte, and writes
only the validated signal-history contract index into the real data root.
"""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "mmibkr.signal_history_metadata_reconciliation.v1"


def _load_json(path: Path) -> dict[str, Any]:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError(f"json_object_required:{path}")
    return node


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_number(value: Any) -> float | int | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out.is_integer():
        return int(out)
    return out


def _conflict_token(symbol: str, timestamp: str) -> str:
    return f"{str(symbol).strip().upper()}@{str(timestamp).strip()}"


def validate_expected_conflicts(
    conflicts: list[dict[str, Any]],
    expected_tokens: list[str],
) -> None:
    expected = {str(value).strip() for value in expected_tokens if str(value).strip()}
    if not expected:
        raise RuntimeError("signal_history_reconciliation_expected_conflicts_required")
    actual = {
        _conflict_token(row.get("symbol") or "", row.get("timestamp") or "")
        for row in conflicts
    }
    if actual != expected:
        raise RuntimeError(
            "signal_history_reconciliation_conflict_set_mismatch:"
            + ",".join(sorted(actual))
            + ":expected:"
            + ",".join(sorted(expected))
        )


def _index_identity(node: Mapping[str, Any]) -> dict[str, Any]:
    runtimes = node.get("runtimes") if isinstance(node.get("runtimes"), Mapping) else {}
    return {
        "schema": node.get("schema"),
        "ok": node.get("ok"),
        "public_run_id": str(node.get("public_run_id") or ""),
        "runtime_count": int(node.get("runtime_count") or 0),
        "runtimes": {
            str(key): {
                "runtime_id": row.get("runtime_id"),
                "symbol": row.get("symbol"),
                "instrument_class": row.get("instrument_class"),
                "target_timeframe": row.get("target_timeframe"),
                "source_timeframe": row.get("source_timeframe"),
                "signal_history_contract": row.get("signal_history_contract"),
                "selected_execution_contract_digest": row.get(
                    "selected_execution_contract_digest"
                ),
                "warmup_ready": row.get("warmup_ready"),
            }
            for key, row in runtimes.items()
            if isinstance(row, Mapping)
        },
    }


def reconcile(
    *,
    repo_root: str | Path,
    real_data_root: str | Path,
    seed_data_root: str | Path,
    bars_path: str | Path,
    seed_ingest_path: str | Path,
    seed_index_path: str | Path,
    expected_public_run_id: str,
    expected_conflicts: list[str],
    output_path: str | Path,
) -> dict[str, Any]:
    # Private imports are lazy by design so public CI can compile/test this helper
    # without carrying private runtime modules.
    import pandas as pd

    from data_manager import DataManager
    from futures_manager import FuturesManager
    from runtime_selected_universe_14tu import build_active_runtime_bindings
    from scripts.operator.selected_runtime_history_warmup_contract_v1 import (
        build_repo_warmup_contract,
        coverage_status,
    )
    from scripts.operator.selected_runtime_initial_backfill_ingest_v1 import (
        OHLCV,
        _NoBrokerIB,
        _base_config,
        _load_rows,
        _raw_ohlcv,
    )
    from scripts.operator.selected_runtime_signal_history_contract_v1 import (
        RELATIVE_PATH,
        SCHEMA as SIGNAL_INDEX_SCHEMA,
        cache_month,
        contract_digest,
        resolve_signal_history_contract,
    )
    from timeframe_adapters import resample_ohlcv

    root = Path(repo_root).resolve()
    real_data = Path(real_data_root).resolve()
    seed_data = Path(seed_data_root).resolve()
    bars_file = Path(bars_path).resolve()
    seed_ingest_file = Path(seed_ingest_path).resolve()
    seed_index_file = Path(seed_index_path).resolve()
    out_file = Path(output_path).resolve()

    for required in (bars_file, seed_ingest_file, seed_index_file):
        if not required.is_file():
            raise RuntimeError(f"signal_history_reconciliation_input_missing:{required}")

    seed_ingest = _load_json(seed_ingest_file)
    if seed_ingest.get("schema") != "mmibkr.selected_runtime_initial_backfill_ingest.v1":
        raise RuntimeError("signal_history_reconciliation_seed_ingest_schema_invalid")
    if seed_ingest.get("ok") is not True or seed_ingest.get("all_warmups_ready") is not True:
        raise RuntimeError("signal_history_reconciliation_seed_ingest_not_ready")
    if seed_ingest.get("broker_action") is not False:
        raise RuntimeError("signal_history_reconciliation_seed_broker_boundary_violated")
    if seed_ingest.get("runtime_execution_contract_mutated") is not False:
        raise RuntimeError("signal_history_reconciliation_seed_execution_mutation")
    if seed_ingest.get("live_execution_allowed") is not False:
        raise RuntimeError("signal_history_reconciliation_seed_live_boundary_violated")
    artifact = seed_ingest.get("artifact") if isinstance(seed_ingest.get("artifact"), Mapping) else {}
    if str(artifact.get("public_run_id") or "") != str(expected_public_run_id):
        raise RuntimeError("signal_history_reconciliation_seed_public_run_mismatch")
    if str(artifact.get("bars_sha256") or "") != _sha256(bars_file):
        raise RuntimeError("signal_history_reconciliation_seed_bars_digest_mismatch")

    seed_index = _load_json(seed_index_file)
    if seed_index.get("schema") != SIGNAL_INDEX_SCHEMA or seed_index.get("ok") is not True:
        raise RuntimeError("signal_history_reconciliation_seed_index_invalid")
    if str(seed_index.get("public_run_id") or "") != str(expected_public_run_id):
        raise RuntimeError("signal_history_reconciliation_seed_index_public_run_mismatch")
    for key in (
        "execution_authority_included",
        "execution_contract_values_included",
        "account_state_included",
        "positions_included",
        "orders_included",
        "credentials_included",
        "broker_action",
    ):
        if seed_index.get(key) is not False:
            raise RuntimeError(
                "signal_history_reconciliation_seed_index_safety_boundary:" + key
            )

    packet = build_active_runtime_bindings(root)
    if packet.get("ok") is not True:
        raise RuntimeError("signal_history_reconciliation_active_bindings_unavailable")
    bindings = [
        dict(row)
        for row in (packet.get("selected_runtimes") or [])
        if isinstance(row, Mapping)
    ]
    if not bindings:
        raise RuntimeError("signal_history_reconciliation_active_bindings_empty")

    seed_rows = (
        seed_index.get("runtimes")
        if isinstance(seed_index.get("runtimes"), Mapping)
        else {}
    )
    runtime_ids = {str(row.get("runtime_id") or "") for row in bindings}
    if set(seed_rows) != runtime_ids or int(seed_index.get("runtime_count") or 0) != len(bindings):
        raise RuntimeError("signal_history_reconciliation_runtime_identity_mismatch")

    warmup_packet = build_repo_warmup_contract(root)
    warmup_rows = {
        str(row.get("runtime_id") or ""): row
        for row in (warmup_packet.get("runtimes") or [])
        if isinstance(row, Mapping)
    }
    if set(warmup_rows) != runtime_ids:
        raise RuntimeError("signal_history_reconciliation_warmup_contract_mismatch")

    config = _base_config(real_data)
    dm = DataManager(config, _NoBrokerIB(), sr_engine=None)
    fm = FuturesManager(config, _NoBrokerIB())
    artifact_frame = _load_rows(bars_file)

    projected = copy.deepcopy(seed_index)
    projected_rows = projected["runtimes"]
    runtime_evidence: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    overlap_total = 0

    for binding in bindings:
        runtime_id = str(binding.get("runtime_id") or "")
        symbol = str(binding.get("symbol") or "").strip().upper()
        instrument = str(binding.get("instrument_class") or "").strip().upper()
        target_tf = str(binding.get("timeframe") or "").strip()
        seed_row = seed_rows.get(runtime_id)
        if not isinstance(seed_row, Mapping):
            raise RuntimeError(f"signal_history_reconciliation_seed_runtime_missing:{runtime_id}")
        if str(seed_row.get("symbol") or "").strip().upper() != symbol:
            raise RuntimeError(f"signal_history_reconciliation_seed_symbol_mismatch:{runtime_id}")
        if str(seed_row.get("instrument_class") or "").strip().upper() != instrument:
            raise RuntimeError(f"signal_history_reconciliation_seed_instrument_mismatch:{runtime_id}")
        expected_digest = contract_digest(
            binding.get("execution_contract")
            if isinstance(binding.get("execution_contract"), Mapping)
            else {}
        )
        if str(seed_row.get("selected_execution_contract_digest") or "") != expected_digest:
            raise RuntimeError(
                f"signal_history_reconciliation_execution_digest_mismatch:{runtime_id}"
            )
        if seed_row.get("warmup_ready") is not True:
            raise RuntimeError(
                f"signal_history_reconciliation_seed_runtime_not_ready:{runtime_id}"
            )

        resolution = resolve_signal_history_contract(binding, index=seed_index)
        if resolution.get("source") != "validated_initial_backfill_index":
            raise RuntimeError(
                f"signal_history_reconciliation_signal_resolution_not_seed:{runtime_id}"
            )
        if str(resolution.get("public_run_id") or "") != str(expected_public_run_id):
            raise RuntimeError(
                f"signal_history_reconciliation_signal_public_run_mismatch:{runtime_id}"
            )
        source_tf = str(seed_row.get("source_timeframe") or "").strip()
        if not source_tf or not target_tf:
            raise RuntimeError(
                f"signal_history_reconciliation_timeframe_missing:{runtime_id}"
            )

        artifact_rows = artifact_frame.loc[
            artifact_frame["symbol"].astype(str).str.upper() == symbol
        ].copy()
        if artifact_rows.empty:
            raise RuntimeError(
                f"signal_history_reconciliation_artifact_symbol_missing:{symbol}"
            )

        if instrument == "STK":
            existing = dm._load_disk_raw("stocks", symbol, source_tf)
            fresh = dm._normalize_ohlcv(_raw_ohlcv(artifact_rows))
            cache_path = dm._path_for("stocks", symbol, source_tf, features=False)
            source_count = int(len(existing)) if existing is not None else 0
            target_count = source_count
        elif instrument == "FUT":
            history_contract = resolution.get("history_contract")
            if not isinstance(history_contract, Mapping):
                raise RuntimeError(
                    f"signal_history_reconciliation_history_contract_missing:{runtime_id}"
                )
            month = cache_month(history_contract)
            existing = fm._read_local_tf_csv_14th3(
                symbol, month, source_tf, quiet=True
            )
            fresh = fm._normalize_ohlcv(_raw_ohlcv(artifact_rows))
            cache_path = fm._local_tf_path_14th3(symbol, month, source_tf)
            source_count = int(len(existing)) if existing is not None else 0
            target = resample_ohlcv(existing, target_tf) if existing is not None else None
            target_count = int(len(target)) if target is not None else 0
        else:
            raise RuntimeError(
                f"signal_history_reconciliation_instrument_unsupported:{runtime_id}"
            )

        if existing is None or existing.empty or not Path(cache_path).is_file():
            raise RuntimeError(
                f"signal_history_reconciliation_real_cache_missing:{runtime_id}"
            )

        coverage = coverage_status(
            warmup_rows[runtime_id],
            completed_target_bars=target_count,
            completed_source_bars=source_count,
        )
        if coverage.get("ready") is not True:
            raise RuntimeError(
                f"signal_history_reconciliation_real_cache_warmup_incomplete:{runtime_id}"
            )

        old = existing.copy()
        new = fresh.copy()
        old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True, errors="coerce")
        new["timestamp"] = pd.to_datetime(new["timestamp"], utc=True, errors="coerce")
        old = old[old["timestamp"].notna()].drop_duplicates("timestamp", keep="last")
        new = new[new["timestamp"].notna()].drop_duplicates("timestamp", keep="last")
        overlap = old.merge(new, on="timestamp", suffixes=("_real", "_seed"), how="inner")
        overlap_total += int(len(overlap))

        runtime_conflicts: list[dict[str, Any]] = []
        for _, overlap_row in overlap.iterrows():
            fields: dict[str, Any] = {}
            for col in OHLCV:
                real_value = overlap_row.get(f"{col}_real")
                seed_value = overlap_row.get(f"{col}_seed")
                both_nan = pd.isna(real_value) and pd.isna(seed_value)
                if both_nan:
                    continue
                differs = (
                    pd.isna(real_value) != pd.isna(seed_value)
                    or float(real_value) != float(seed_value)
                )
                if not differs:
                    continue
                real_num = _safe_number(real_value)
                seed_num = _safe_number(seed_value)
                fields[col] = {
                    "canonical_forward": real_num,
                    "validated_seed": seed_num,
                    "seed_minus_canonical": (
                        None
                        if real_num is None or seed_num is None
                        else float(seed_num) - float(real_num)
                    ),
                }
            if fields:
                item = {
                    "runtime_id": runtime_id,
                    "symbol": symbol,
                    "timestamp": pd.Timestamp(overlap_row["timestamp"]).isoformat(),
                    "fields": fields,
                }
                conflicts.append(item)
                runtime_conflicts.append(item)

        projected_rows[runtime_id]["source_cache_path"] = str(Path(cache_path).resolve())
        # Re-run the private resolver against the projected index before any write.
        projected_resolution = resolve_signal_history_contract(
            binding,
            index=projected,
        )
        if projected_resolution.get("execution_contract_digest_match") is not True:
            raise RuntimeError(
                f"signal_history_reconciliation_projected_digest_mismatch:{runtime_id}"
            )

        runtime_evidence[runtime_id] = {
            "runtime_id": runtime_id,
            "symbol": symbol,
            "instrument_class": instrument,
            "source_timeframe": source_tf,
            "target_timeframe": target_tf,
            "source_rows": source_count,
            "target_rows": target_count,
            "warmup": coverage,
            "real_cache_path": str(Path(cache_path).resolve()),
            "overlap_rows": int(len(overlap)),
            "conflicting_overlap_rows": int(len(runtime_conflicts)),
            "selected_execution_contract_digest_match": True,
            "signal_history_contract_public_run_id": str(expected_public_run_id),
        }

    validate_expected_conflicts(conflicts, expected_conflicts)

    target_index = real_data / RELATIVE_PATH
    target_index.parent.mkdir(parents=True, exist_ok=True)
    metadata_written = True
    existing_index_identity = None
    if target_index.is_file():
        existing_index = _load_json(target_index)
        existing_index_identity = _index_identity(existing_index)
        if existing_index_identity != _index_identity(projected):
            raise RuntimeError(
                "signal_history_reconciliation_existing_index_conflicts"
            )
        metadata_written = False
    else:
        temp = target_index.with_suffix(target_index.suffix + ".reconcile.tmp")
        temp.write_text(
            json.dumps(projected, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, target_index)

    written_index = _load_json(target_index)
    if _index_identity(written_index) != _index_identity(projected):
        raise RuntimeError("signal_history_reconciliation_written_index_mismatch")

    result = {
        "schema": SCHEMA,
        "ok": True,
        "status": "signal_history_metadata_reconciled_without_market_data_mutation",
        "source_public_run_id": str(expected_public_run_id),
        "bars_sha256": _sha256(bars_file),
        "seed_ingest_sha256": _sha256(seed_ingest_file),
        "seed_index_sha256": _sha256(seed_index_file),
        "signal_history_index_path": str(target_index),
        "signal_history_index_written": metadata_written,
        "active_runtime_count": len(bindings),
        "runtime_evidence": runtime_evidence,
        "overlap_rows": overlap_total,
        "conflicting_overlap_rows": len(conflicts),
        "conflicts": conflicts,
        "conflict_policy": "preserve_existing_canonical_forward_cache",
        "market_data_cache_mutated": False,
        "artifact_bars_written_to_real_cache": False,
        "signal_history_metadata_written": metadata_written,
        "execution_authority_mutated": False,
        "broker_action": False,
        "paper_owner_started": False,
        "live_execution_allowed": False,
        "credentials_included": False,
        "account_state_included": False,
        "positions_included": False,
        "orders_included": False,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--real-data-root", required=True)
    parser.add_argument("--seed-data-root", required=True)
    parser.add_argument("--bars", required=True)
    parser.add_argument("--seed-ingest", required=True)
    parser.add_argument("--seed-index", required=True)
    parser.add_argument("--expected-public-run-id", required=True)
    parser.add_argument(
        "--expected-conflict",
        action="append",
        default=[],
        help="Exact SYMBOL@ISO_TIMESTAMP conflict token; repeat for every expected conflict.",
    )
    parser.add_argument(
        "--expected-conflicts-json",
        default="",
        help="Optional JSON file containing the exact conflict-token list.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    expected_conflicts = list(args.expected_conflict or [])
    if args.expected_conflicts_json:
        node = json.loads(Path(args.expected_conflicts_json).read_text(encoding="utf-8"))
        if not isinstance(node, list) or not all(isinstance(value, str) for value in node):
            raise SystemExit("expected conflicts JSON must be a list of strings")
        expected_conflicts.extend(node)

    result = reconcile(
        repo_root=args.repo_root,
        real_data_root=args.real_data_root,
        seed_data_root=args.seed_data_root,
        bars_path=args.bars,
        seed_ingest_path=args.seed_ingest,
        seed_index_path=args.seed_index,
        expected_public_run_id=args.expected_public_run_id,
        expected_conflicts=expected_conflicts,
        output_path=args.output,
    )
    print("MMIBKR_SIGNAL_HISTORY_RECONCILIATION=" + json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
