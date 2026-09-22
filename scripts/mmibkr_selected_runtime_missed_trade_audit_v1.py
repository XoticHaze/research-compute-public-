from __future__ import annotations

"""Read-only selected-runtime missed-trade audit.

Replays canonical selected-runtime strategy decisions over restored historical/
forward cache data. This module never opens an IB socket, never submits/cancels/
flattens orders, never mutates StrategySpec/runtime authority, and never enables
live trading.

The audit deliberately separates:
1. strategy-condition/actionable-candidate truth;
2. deterministic pre-quote paper eligibility; and
3. actual owner/trade evidence already present in the restored terminal ledger.

Account-wide broker holdings are never inferred to be bot-owned inventory.
Without explicit authoritative strategy inventory, path-dependent paper-order
eligibility fails closed while CRW condition candidates remain visible.
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "mmibkr.selected_runtime_missed_trade_audit.v1"
REQUEST_SCHEMA = "mmibkr.selected_runtime_missed_trade_audit_request.v1"
TERMINAL_LEDGER_SCHEMA = "mmibkr.selected_runtime_cloud_cycle_terminal_ledger.v1"
SOURCE_SHA_EXPECTED_LENGTH = 40


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: Any, *, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field}_required")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}_invalid:{raw}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field}_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _clean(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _clean(value.item())
        except Exception:
            pass
    return str(value)


def read_json(path: str | Path) -> dict[str, Any]:
    node = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise ValueError(f"json_object_required:{path}")
    return node


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(_clean(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_request(node: Mapping[str, Any]) -> dict[str, Any]:
    if node.get("schema") != REQUEST_SCHEMA:
        raise ValueError("audit_request_schema_mismatch")
    start = parse_utc(node.get("window_start_utc"), field="window_start_utc")
    end = parse_utc(node.get("window_end_utc"), field="window_end_utc")
    if end <= start:
        raise ValueError("audit_window_end_must_follow_start")
    source_sha = str(node.get("private_source_sha") or "").strip().lower()
    if len(source_sha) != SOURCE_SHA_EXPECTED_LENGTH or any(
        ch not in "0123456789abcdef" for ch in source_sha
    ):
        raise ValueError("private_source_sha_must_be_exact_40_hex")
    return {
        "schema": REQUEST_SCHEMA,
        "audit_id": str(node.get("audit_id") or "").strip() or "selected-runtime-missed-trade-audit",
        "private_source_sha": source_sha,
        "window_start_utc": _iso(start),
        "window_end_utc": _iso(end),
        "window_start_authority": str(node.get("window_start_authority") or "operator_supplied"),
        "window_end_authority": str(node.get("window_end_authority") or "operator_supplied"),
        "window_semantics": str(
            node.get("window_semantics")
            or "conservative_confirmed_offline_through_continuity_proof"
        ),
        "runtime_windows": (
            dict(node.get("runtime_windows") or {})
            if isinstance(node.get("runtime_windows"), Mapping)
            else {}
        ),
        "inventory_by_runtime": (
            dict(node.get("inventory_by_runtime") or {})
            if isinstance(node.get("inventory_by_runtime"), Mapping)
            else {}
        ),
        "data_paths": (
            dict(node.get("data_paths") or {})
            if isinstance(node.get("data_paths"), Mapping)
            else {}
        ),
        "historical_seed_run_id": str(node.get("historical_seed_run_id") or "").strip() or None,
        "historical_seed_bars_sha256": str(
            node.get("historical_seed_bars_sha256") or ""
        ).strip().lower() or None,
    }


def _inventory_state(request: Mapping[str, Any], runtime_id: str) -> dict[str, Any]:
    raw = (request.get("inventory_by_runtime") or {}).get(runtime_id)
    state = dict(raw) if isinstance(raw, Mapping) else {}
    authoritative = state.get("authoritative_position") is True
    if not authoritative:
        return {
            "schema": "mmibkr.missed_trade_inventory_input.v1",
            "authoritative_position": False,
            "position_qty": None,
            "fill_history_complete": False,
            "state_ready_for_dca": False,
            "dca_count": None,
            "entry_count": None,
            "avg_entry_price": None,
            "last_buy_fill_price": None,
            "source": state.get("source") or "not_provided",
            "bot_owned_inventory_inferred_from_account_positions": False,
        }
    qty = _finite(state.get("position_qty"))
    if qty is None:
        raise ValueError(f"authoritative_inventory_qty_required:{runtime_id}")
    out = dict(state)
    out.update(
        {
            "schema": str(
                state.get("schema") or "mmibkr.missed_trade_inventory_input.v1"
            ),
            "authoritative_position": True,
            "position_qty": qty,
            "qty": qty,
            "current_position_qty": qty,
            "bot_owned_inventory_inferred_from_account_positions": False,
        }
    )
    return out


def _runtime_window(
    request: Mapping[str, Any], runtime_id: str
) -> tuple[datetime, datetime]:
    start = parse_utc(request.get("window_start_utc"), field="window_start_utc")
    end = parse_utc(request.get("window_end_utc"), field="window_end_utc")
    raw = (request.get("runtime_windows") or {}).get(runtime_id)
    if isinstance(raw, Mapping):
        if raw.get("start_utc"):
            start = parse_utc(raw.get("start_utc"), field=f"{runtime_id}.start_utc")
        if raw.get("end_utc"):
            end = parse_utc(raw.get("end_utc"), field=f"{runtime_id}.end_utc")
    if end <= start:
        raise ValueError(f"runtime_window_invalid:{runtime_id}")
    return start, end


def _asset_folder(binding: Mapping[str, Any]) -> str:
    instrument = str(binding.get("instrument_class") or "").upper()
    if instrument == "STK":
        return "stocks"
    if instrument == "FUT":
        return "futures"
    return str(binding.get("asset_type") or instrument or "unknown").lower()


def _candidate_data_paths(
    data_root: Path,
    binding: Mapping[str, Any],
    explicit: str | None,
) -> list[Path]:
    symbol = str(binding.get("symbol") or "").upper()
    timeframe = str(binding.get("timeframe") or "")
    asset = _asset_folder(binding)
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(
        [
            data_root / asset / symbol / f"{timeframe}.features.csv",
            data_root / asset / symbol / f"{timeframe}.csv",
            data_root / asset / symbol.lower() / f"{timeframe}.features.csv",
            data_root / asset / symbol.lower() / f"{timeframe}.csv",
        ]
    )
    out: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def _source_cache_candidates(
    data_root: Path,
    binding: Mapping[str, Any],
    source_timeframe: str,
) -> list[Path]:
    symbol = str(binding.get("symbol") or "").upper()
    asset = _asset_folder(binding)
    instrument = str(binding.get("instrument_class") or "").upper()
    candidates: list[Path] = []
    if instrument == "FUT":
        contract = (
            binding.get("execution_contract")
            if isinstance(binding.get("execution_contract"), Mapping)
            else {}
        )
        month = str(contract.get("lastTradeDateOrContractMonth") or "").strip()[:6]
        if len(month) == 6 and month.isdigit():
            candidates.extend(
                [
                    data_root / asset / f"{symbol}-{month}" / f"{source_timeframe}.features.csv",
                    data_root / asset / f"{symbol}-{month}" / f"{source_timeframe}.csv",
                ]
            )
    candidates.extend(
        [
            data_root / asset / symbol / f"{source_timeframe}.features.csv",
            data_root / asset / symbol / f"{source_timeframe}.csv",
            data_root / asset / symbol.lower() / f"{source_timeframe}.features.csv",
            data_root / asset / symbol.lower() / f"{source_timeframe}.csv",
        ]
    )
    out: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def _normalize_frame(frame, *, source: Path):
    import pandas as pd

    timestamp_col = next(
        (
            name
            for name in (
                "timestamp",
                "date",
                "datetime",
                "time",
                "Date",
                "Timestamp",
            )
            if name in frame.columns
        ),
        None,
    )
    if timestamp_col is None:
        unnamed = [name for name in frame.columns if str(name).startswith("Unnamed:")]
        if unnamed:
            timestamp_col = unnamed[0]
    if timestamp_col is None:
        raise ValueError(f"timestamp_column_missing:{source}")

    parsed = pd.to_datetime(frame[timestamp_col], utc=True, errors="coerce")
    valid = parsed.notna()
    frame = frame.loc[valid].copy()
    parsed = parsed.loc[valid]
    frame["timestamp"] = parsed
    frame = frame.sort_values("timestamp").drop_duplicates(
        subset=["timestamp"], keep="last"
    )
    frame = frame.reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"target_frame_no_valid_timestamps:{source}")
    return frame


def _load_seed_rows(
    path: str | Path | None,
    *,
    expected_sha256: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path:
        if expected_sha256:
            raise ValueError("historical_seed_bars_path_required")
        return [], {"used": False, "row_count": 0}
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"historical_seed_bars_missing:{source}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise ValueError(
            f"historical_seed_bars_sha256_mismatch:{digest}:{expected_sha256}"
        )
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        node = json.loads(raw)
        if not isinstance(node, dict):
            raise ValueError(f"historical_seed_non_object_row:{line_no}")
        rows.append(node)
    return rows, {
        "used": True,
        "path": str(source),
        "sha256": digest,
        "row_count": len(rows),
    }


def _prepend_seed_history(
    frame,
    *,
    seed_rows: list[dict[str, Any]],
    symbol: str,
    source_timeframe: str,
    source: Path,
):
    import pandas as pd

    if frame is None or frame.empty or not seed_rows:
        return frame, 0
    bar_size_by_timeframe = {
        "1Min": "1 min",
        "2Min": "2 mins",
        "3Min": "3 mins",
        "5Min": "5 mins",
        "15Min": "15 mins",
        "30Min": "30 mins",
        "1Hour": "1 hour",
        "2Hour": "2 hours",
        "4Hour": "4 hours",
        "1Day": "1 day",
    }
    expected_bar_size = bar_size_by_timeframe.get(str(source_timeframe))
    if not expected_bar_size:
        raise ValueError(
            f"historical_seed_bar_size_mapping_missing:{source_timeframe}"
        )
    selected = [
        dict(row)
        for row in seed_rows
        if str(row.get("symbol") or "").strip().upper() == symbol
        and str(row.get("bar_size") or "").strip() == expected_bar_size
    ]
    if not selected:
        return frame, 0
    seed = pd.DataFrame(selected).rename(
        columns={"wap": "average", "bar_count": "barCount"}
    )
    keep = [
        column
        for column in (
            "timestamp", "open", "high", "low", "close", "volume",
            "average", "barCount",
        )
        if column in seed.columns
    ]
    seed = _normalize_frame(seed[keep], source=source)
    first_current = frame["timestamp"].iloc[0]
    missing_prefix = seed.loc[seed["timestamp"] < first_current].copy()
    if missing_prefix.empty:
        return frame, 0
    combined = pd.concat([missing_prefix, frame], ignore_index=True)
    combined = _normalize_frame(combined, source=source)
    return combined, int(len(missing_prefix))


def _load_frame(
    *,
    data_root: Path,
    binding: Mapping[str, Any],
    explicit_path: str | None,
    seed_rows: list[dict[str, Any]] | None = None,
):
    import pandas as pd
    from timeframe_adapters import resolve_timeframe_adapter, resample_ohlcv

    candidates = _candidate_data_paths(data_root, binding, explicit_path)
    source: Path | None = None
    frame = None
    direct_target = False
    for path in candidates:
        if not path.is_file():
            continue
        loaded = pd.read_csv(path)
        if loaded is None or loaded.empty:
            continue
        source = path
        frame = loaded
        direct_target = True
        break

    adapter_spec = None
    source_candidates: list[Path] = []
    source_rows = None
    seed_rows_prepended = 0
    if source is not None and frame is not None:
        frame = _normalize_frame(frame, source=source)
        frame, seed_rows_prepended = _prepend_seed_history(
            frame,
            seed_rows=list(seed_rows or []),
            symbol=str(binding.get("symbol") or "").upper(),
            source_timeframe=str(binding.get("timeframe") or ""),
            source=source,
        )
    if source is None or frame is None:
        target_timeframe = str(binding.get("timeframe") or "")
        native_timeframes = (
            "1Min", "2Min", "3Min", "5Min", "15Min", "30Min",
            "1Hour", "2Hour", "4Hour", "1Day", "1W", "1M",
        )
        adapter_spec = resolve_timeframe_adapter(
            target_timeframe,
            native_timeframes=native_timeframes,
            default_minute_source="1Min",
        )
        if not adapter_spec.is_custom:
            raise FileNotFoundError(
                "target_frame_missing:"
                + str(binding.get("runtime_id"))
                + ":"
                + ",".join(str(path) for path in candidates)
            )
        source_candidates = _source_cache_candidates(
            data_root,
            binding,
            adapter_spec.source_timeframe,
        )
        for path in source_candidates:
            if not path.is_file():
                continue
            loaded = pd.read_csv(path)
            if loaded is None or loaded.empty:
                continue
            source = path
            frame = _normalize_frame(loaded, source=path)
            frame, seed_rows_prepended = _prepend_seed_history(
                frame,
                seed_rows=list(seed_rows or []),
                symbol=str(binding.get("symbol") or "").upper(),
                source_timeframe=adapter_spec.source_timeframe,
                source=path,
            )
            source_rows = int(len(frame))
            frame = resample_ohlcv(frame, adapter_spec.target_timeframe)
            if frame is None or frame.empty:
                continue
            frame = _normalize_frame(frame, source=path)
            break

    if source is None or frame is None or frame.empty:
        all_candidates = [*candidates, *source_candidates]
        raise FileNotFoundError(
            "target_or_source_frame_missing:"
            + str(binding.get("runtime_id"))
            + ":"
            + ",".join(str(path) for path in all_candidates)
        )

    if direct_target:
        frame = _normalize_frame(frame, source=source)

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    authority = {
        "path": str(source),
        "sha256": digest,
        "rows": int(len(frame)),
        "first_timestamp_utc": str(frame.iloc[0]["timestamp"]),
        "last_timestamp_utc": str(frame.iloc[-1]["timestamp"]),
        "authority": "restored_canonical_checkpoint_cache",
        "target_materialization": (
            "direct_persisted_target"
            if direct_target
            else "canonical_timeframe_adapter_resample_ohlcv"
        ),
        "historical_seed_rows_prepended": int(seed_rows_prepended),
        "overlap_policy": "preserve_restored_checkpoint_overlap",
    }
    if adapter_spec is not None:
        authority.update(
            {
                "source_rows": int(source_rows or 0),
                "adapter": adapter_spec.to_dict(),
                "target_rows": int(len(frame)),
            }
        )
    return frame, authority


def _terminal_entries(data_root: Path) -> dict[str, dict[str, Any]]:
    path = (
        data_root
        / "strategy_runtime"
        / "selected_runtime_cloud_cycle_v1"
        / "terminal_boundaries.json"
    )
    if not path.is_file():
        return {}
    try:
        node = read_json(path)
    except Exception:
        return {}
    if node.get("schema") != TERMINAL_LEDGER_SCHEMA:
        return {}
    entries = node.get("entries")
    if not isinstance(entries, Mapping):
        return {}
    return {
        str(key): dict(value)
        for key, value in entries.items()
        if isinstance(value, Mapping) and value.get("terminal") is True
    }


def _terminal_match(
    terminal_entries: Mapping[str, Mapping[str, Any]],
    *,
    runtime_id: str,
    timestamp_utc: datetime,
) -> dict[str, Any] | None:
    matches: list[tuple[float, str, Mapping[str, Any]]] = []
    for key, entry in terminal_entries.items():
        runtime_ids = [str(item) for item in (entry.get("runtime_ids") or [])]
        if runtime_id not in runtime_ids:
            continue
        raw = entry.get("bar_close_at_utc")
        try:
            boundary_ts = parse_utc(raw, field="terminal_bar_close_at_utc")
        except Exception:
            continue
        delta = abs((boundary_ts - timestamp_utc).total_seconds())
        if delta <= 90:
            matches.append((delta, str(key), entry))
    if not matches:
        return None
    delta, key, entry = min(matches, key=lambda item: item[0])
    return {
        "boundary_key": key,
        "status": entry.get("status"),
        "bar_close_at_utc": entry.get("bar_close_at_utc"),
        "recorded_at_utc": entry.get("recorded_at_utc"),
        "match_delta_sec": delta,
        "owner_present": True,
        "actually_observed_by_cloud": True,
        "actual_trade_for_this_runtime": None,
        "boundary_had_execution": entry.get("status") == "executed_ok",
        "duplicate_idempotency_blocked": False,
    }


def _condition_projection(evaluation: Mapping[str, Any] | None) -> dict[str, Any]:
    evaluation = evaluation if isinstance(evaluation, Mapping) else {}
    meta = evaluation.get("meta") if isinstance(evaluation.get("meta"), Mapping) else {}
    conditions = (
        meta.get("conditions") if isinstance(meta.get("conditions"), Mapping) else {}
    )
    current = (
        conditions.get("current_values")
        if isinstance(conditions.get("current_values"), Mapping)
        else {}
    )
    params = (
        conditions.get("parameters")
        if isinstance(conditions.get("parameters"), Mapping)
        else {}
    )

    def block(name: str) -> dict[str, Any]:
        raw = conditions.get(name)
        return dict(raw) if isinstance(raw, Mapping) else {}

    entry = block("entry_long")
    exit_ = block("exit_long")
    scale = block("scale_long")
    filters = (
        conditions.get("filters")
        if isinstance(conditions.get("filters"), Mapping)
        else {}
    )
    return {
        "crw_score": _finite(meta.get("crw_score", current.get("CRW_SCORE"))),
        "close": _finite(meta.get("price", current.get("close"))),
        "entry_threshold": _finite(meta.get("entry_level", params.get("entryLevel"))),
        "exit_threshold": _finite(meta.get("exit_level", params.get("exitLevel"))),
        "entry_passed": entry.get("passed") is True,
        "exit_passed": exit_.get("passed") is True,
        "dca_passed": scale.get("passed") is True,
        "entry_conditions": entry,
        "exit_conditions": exit_,
        "dca_conditions": scale,
        "filters": dict(filters),
        "reason": meta.get("reason"),
        "signal_kind": meta.get("signal_kind") or evaluation.get("signal_kind"),
    }


def classify_decision(
    *,
    evaluation: Mapping[str, Any] | None,
    diagnostic_evaluation: Mapping[str, Any] | None,
    generic_filter_blocked: bool,
    warmup_ready: bool,
) -> str:
    if not warmup_ready:
        return "WARMUP_INCOMPLETE"
    diag = _condition_projection(diagnostic_evaluation)
    diagnostic_actionable = bool(
        isinstance(diagnostic_evaluation, Mapping)
        and diagnostic_evaluation.get("actionable_signal")
    )
    if generic_filter_blocked:
        if (
            diagnostic_actionable
            or diag["entry_passed"]
            or diag["exit_passed"]
            or diag["dca_passed"]
        ):
            return "SIGNAL_FILTER_BLOCKED"
        return "NO_SIGNAL"

    if not isinstance(evaluation, Mapping) or not evaluation.get("actionable_signal"):
        entry_items = diag.get("entry_conditions", {}).get("items") or []
        exit_items = diag.get("exit_conditions", {}).get("items") or []
        score_side_true = any(
            isinstance(item, Mapping)
            and item.get("id") in {"score_below_entry", "score_above_exit"}
            and item.get("passed") is True
            for item in [*entry_items, *exit_items]
        )
        if score_side_true and not (diag["entry_passed"] or diag["exit_passed"]):
            return "SIGNAL_FILTER_BLOCKED"
        return "NO_SIGNAL"

    projection = _condition_projection(evaluation)
    signal_kind = str(projection.get("signal_kind") or "").lower()
    if signal_kind == "entry_long":
        return "ENTRY_CANDIDATE"
    if signal_kind == "exit_long":
        return "EXIT_CANDIDATE"
    if signal_kind == "dca_add":
        return "DCA_CANDIDATE"
    return "ACTIONABLE_CANDIDATE"


def deterministic_paper_eligibility(
    *,
    binding: Mapping[str, Any],
    evaluation: Mapping[str, Any] | None,
    inventory: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(evaluation, Mapping) or not evaluation.get("actionable_signal"):
        return {
            "eligible": False,
            "state": "NO_ACTIONABLE_SIGNAL",
            "quantity": None,
            "action": None,
            "position_effect": None,
            "prequote_only": True,
        }
    policy = (
        binding.get("execution_policy")
        if isinstance(binding.get("execution_policy"), Mapping)
        else {}
    )
    if not bool(policy.get("paper_submit_enabled")):
        return {
            "eligible": False,
            "state": "PAPER_SUBMIT_DISABLED",
            "quantity": None,
            "action": evaluation.get("side"),
            "position_effect": None,
            "prequote_only": True,
        }
    if inventory.get("authoritative_position") is not True:
        return {
            "eligible": False,
            "state": "BOT_INVENTORY_AUTHORITY_REQUIRED",
            "quantity": None,
            "action": evaluation.get("side"),
            "position_effect": None,
            "prequote_only": True,
        }

    from selected_runtime_position_policy_14th31ju import (
        selected_position_cap_ok_14th31ju,
        selected_runtime_execution_sizing_14th31ju,
    )

    action = str(evaluation.get("side") or "").upper()
    sizing = selected_runtime_execution_sizing_14th31ju(
        selected_runtime=binding,
        evaluation=evaluation,
        action=action,
        default_qty=1.0,
    )
    current_qty = _finite(inventory.get("position_qty"))
    signal_kind = str(sizing.get("signal_kind") or "").lower()

    if signal_kind == "entry_long" and current_qty is not None and current_qty > 0:
        return {
            "eligible": False,
            "state": "ENTRY_BLOCKED_POSITION_ALREADY_OPEN",
            "quantity": None,
            "action": action,
            "position_effect": sizing.get("position_effect"),
            "prequote_only": True,
        }
    if signal_kind == "exit_long" and (current_qty is None or current_qty <= 0):
        return {
            "eligible": False,
            "state": "EXIT_BLOCKED_NO_BOT_POSITION",
            "quantity": None,
            "action": action,
            "position_effect": sizing.get("position_effect"),
            "prequote_only": True,
        }
    if signal_kind == "dca_add":
        if not bool(sizing.get("dca_enabled")):
            return {
                "eligible": False,
                "state": "DCA_DISABLED",
                "quantity": None,
                "action": action,
                "position_effect": sizing.get("position_effect"),
                "prequote_only": True,
            }
        if not bool(sizing.get("fill_history_complete")):
            return {
                "eligible": False,
                "state": "DCA_FILL_HISTORY_INCOMPLETE",
                "quantity": None,
                "action": action,
                "position_effect": sizing.get("position_effect"),
                "prequote_only": True,
            }
        if not bool(sizing.get("state_ready_for_dca")):
            return {
                "eligible": False,
                "state": "DCA_STATE_NOT_READY",
                "quantity": None,
                "action": action,
                "position_effect": sizing.get("position_effect"),
                "prequote_only": True,
            }

    cap = selected_position_cap_ok_14th31ju(
        sizing.get("current_position_qty"),
        action,
        sizing.get("qty"),
        sizing.get("max_position_qty"),
    )
    if not bool(cap.get("ok")):
        return {
            "eligible": False,
            "state": str(cap.get("blocker") or "POSITION_CAP_BLOCKED"),
            "quantity": None,
            "action": action,
            "position_effect": sizing.get("position_effect"),
            "prequote_only": True,
        }
    quantity = _finite(sizing.get("qty"))
    if quantity is None or quantity <= 0:
        return {
            "eligible": False,
            "state": "DETERMINISTIC_QUANTITY_UNAVAILABLE",
            "quantity": None,
            "action": action,
            "position_effect": sizing.get("position_effect"),
            "prequote_only": True,
        }
    return {
        "eligible": True,
        "state": "DETERMINISTIC_PREQUOTE_PAPER_CANDIDATE",
        "quantity": quantity,
        "action": action,
        "position_effect": sizing.get("position_effect"),
        "prequote_only": True,
        "quote_replay_performed": False,
        "broker_submit_replay_performed": False,
    }


def _summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_runtime: dict[str, dict[str, int]] = {}
    for row in rows:
        runtime = str(row.get("runtime_id") or "")
        node = by_runtime.setdefault(
            runtime,
            {
                "boundaries": 0,
                "no_signal": 0,
                "signal_filter_blocked": 0,
                "entry_candidates": 0,
                "exit_candidates": 0,
                "dca_candidates": 0,
                "prequote_paper_eligible": 0,
                "cloud_observed": 0,
                "no_cloud_owner_evidence": 0,
                "runtime_filtered_latest_stale": 0,
                "latest_bar_signal_filter_blocked": 0,
                "latest_bar_entry_candidates": 0,
                "latest_bar_exit_candidates": 0,
                "latest_bar_dca_candidates": 0,
                "latest_bar_prequote_paper_eligible": 0,
            },
        )
        node["boundaries"] += 1
        decision = str(row.get("decision") or "")
        mapping = {
            "NO_SIGNAL": "no_signal",
            "SIGNAL_FILTER_BLOCKED": "signal_filter_blocked",
            "ENTRY_CANDIDATE": "entry_candidates",
            "EXIT_CANDIDATE": "exit_candidates",
            "DCA_CANDIDATE": "dca_candidates",
        }
        if decision in mapping:
            node[mapping[decision]] += 1
        if row.get("would_have_reached_paper_quote_stage") is True:
            node["prequote_paper_eligible"] += 1
        if row.get("actual_owner_present") is True:
            node["cloud_observed"] += 1
        elif row.get("actual_owner_present") is False:
            node["no_cloud_owner_evidence"] += 1
        if (row.get("filter_latest_bar_truth") or {}).get(
            "runtime_filtered_latest_is_stale"
        ) is True:
            node["runtime_filtered_latest_stale"] += 1
        latest_decision = str(row.get("latest_bar_decision") or "")
        latest_mapping = {
            "SIGNAL_FILTER_BLOCKED": "latest_bar_signal_filter_blocked",
            "ENTRY_CANDIDATE": "latest_bar_entry_candidates",
            "EXIT_CANDIDATE": "latest_bar_exit_candidates",
            "DCA_CANDIDATE": "latest_bar_dca_candidates",
        }
        if latest_decision in latest_mapping:
            node[latest_mapping[latest_decision]] += 1
        if row.get("latest_bar_would_have_reached_paper_quote_stage") is True:
            node["latest_bar_prequote_paper_eligible"] += 1
    return by_runtime


async def run_audit(
    *,
    repo_root: str | Path,
    data_root: str | Path,
    request: Mapping[str, Any],
    historical_seed_bars: str | Path | None = None,
) -> dict[str, Any]:
    req = validate_request(request)
    root = Path(repo_root).resolve()
    data = Path(data_root)
    if not data.is_absolute():
        data = (root / data).resolve()

    source_head = str(
        os.environ.get("MMIBKR_PRIVATE_HEAD") or req["private_source_sha"]
    ).lower()
    if source_head != req["private_source_sha"]:
        raise RuntimeError(
            f"private_source_identity_mismatch:{source_head}:{req['private_source_sha']}"
        )

    seed_rows, seed_evidence = _load_seed_rows(
        historical_seed_bars,
        expected_sha256=req.get("historical_seed_bars_sha256"),
    )
    seed_evidence["public_run_id"] = req.get("historical_seed_run_id")
    seed_evidence["overlap_policy"] = "preserve_restored_checkpoint_overlap"

    sys.path.insert(0, str(root))
    from filters import Filters
    from runtime_selected_universe_14tu import build_active_runtime_bindings
    from scripts.operator.selected_runtime_history_warmup_contract_v1 import (
        build_runtime_warmup_contract,
    )
    from scripts.operator.selected_runtime_legacy_compat_config_v1 import (
        build_legacy_compatible_runtime_config,
    )
    from strategy import Strategy

    active = build_active_runtime_bindings(root)
    if active.get("ok") is not True:
        raise RuntimeError("active_selected_runtime_bindings_unavailable")
    bindings = [
        dict(row)
        for row in (active.get("selected_runtimes") or [])
        if isinstance(row, Mapping)
        and str(row.get("symbol") or "").upper() in {"AMAT", "APH", "MNQ"}
    ]
    if len(bindings) != 3:
        raise RuntimeError(
            "expected_exact_three_selected_runtimes:"
            + ",".join(str(row.get("runtime_id")) for row in bindings)
        )

    compat = build_legacy_compatible_runtime_config(root)
    config = dict(compat["config"])
    config["DATA_OUTPUT_DIR"] = str(data)
    config["ENABLE_LIVE_TRADING"] = False
    config["STRATEGY_AUTO_START_LOOPS_ENABLED"] = False
    config["SR_ENABLED"] = False
    config["SR_LOOP_UPDATES"] = False
    config["ORDERBOOK_ENABLED"] = False

    filters = Filters(config)
    strategy = Strategy(config, None, filters, futures_registry=None)
    terminal = _terminal_entries(data)
    rows: list[dict[str, Any]] = []
    data_authorities: dict[str, Any] = {}

    for binding in bindings:
        runtime_id = str(binding.get("runtime_id") or "")
        symbol = str(binding.get("symbol") or "").upper()
        timeframe = str(binding.get("timeframe") or "")
        instrument = str(binding.get("instrument_class") or "").upper()
        asset_type = "stocks" if instrument == "STK" else "futures"
        explicit = (
            str((req.get("data_paths") or {}).get(runtime_id) or "").strip() or None
        )
        frame, authority = _load_frame(
            data_root=data,
            binding=binding,
            explicit_path=explicit,
            seed_rows=seed_rows,
        )
        data_authorities[runtime_id] = authority
        inventory = _inventory_state(req, runtime_id)
        start, end = _runtime_window(req, runtime_id)
        warmup = build_runtime_warmup_contract(binding)
        required_rows = int(warmup.get("required_completed_target_bars") or 0)

        for index in range(len(frame)):
            raw_ts = frame.iloc[index]["timestamp"]
            ts = (
                raw_ts.to_pydatetime()
                if hasattr(raw_ts, "to_pydatetime")
                else raw_ts
            )
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            from timeframe_adapters import timeframe_minutes

            target_minutes = timeframe_minutes(timeframe)
            if target_minutes is None:
                raise RuntimeError(
                    f"audit_target_timeframe_minutes_unavailable:{runtime_id}:{timeframe}"
                )
            boundary_ts = ts + timedelta(minutes=int(target_minutes))
            if boundary_ts < start or boundary_ts > end:
                continue

            upto = frame.iloc[: index + 1].copy()
            warmup_ready = bool(required_rows > 0 and len(upto) >= required_rows)
            diagnostic = strategy.evaluate_registry_once(
                upto,
                str(binding.get("strategy_id") or ""),
                symbol,
                asset_type,
                timeframe,
                position_state=inventory,
            )
            evaluation: Mapping[str, Any] | None = None
            generic_filter_blocked = False
            generic_filter_error = None
            filtered_rows = None
            latest_gate_passed: bool | None = None
            latest_gate_error = None

            if warmup_ready:
                if instrument == "STK":
                    try:
                        latest_filtered = await filters.apply_filters_async(
                            upto.tail(1).copy(),
                            timeframe=timeframe,
                            asset_type="stocks",
                            symbol=symbol,
                        )
                        latest_gate_passed = bool(
                            latest_filtered is not None
                            and not getattr(latest_filtered, "empty", True)
                        )
                    except Exception as exc:
                        latest_gate_passed = None
                        latest_gate_error = repr(exc)
                    try:
                        filtered = await filters.apply_filters_async(
                            upto,
                            timeframe=timeframe,
                            asset_type="stocks",
                            symbol=symbol,
                        )
                    except Exception as exc:
                        filtered = None
                        generic_filter_error = repr(exc)
                    if filtered is None or getattr(filtered, "empty", True):
                        generic_filter_blocked = True
                        filtered_rows = 0
                    else:
                        filtered_rows = int(len(filtered))
                        evaluation = strategy.evaluate_registry_once(
                            filtered,
                            str(binding.get("strategy_id") or ""),
                            symbol,
                            asset_type,
                            timeframe,
                            position_state=inventory,
                        )
                else:
                    evaluation = diagnostic

            decision = classify_decision(
                evaluation=evaluation,
                diagnostic_evaluation=diagnostic,
                generic_filter_blocked=generic_filter_blocked,
                warmup_ready=warmup_ready,
            )
            condition_source = (
                evaluation if isinstance(evaluation, Mapping) else diagnostic
            )
            condition_projection = _condition_projection(condition_source)
            diagnostic_projection = _condition_projection(diagnostic)
            runtime_filtered_timestamp = (
                str(evaluation.get("last_bar_timestamp") or "")
                if isinstance(evaluation, Mapping)
                else None
            )
            raw_latest_timestamp = (
                str(diagnostic.get("last_bar_timestamp") or "")
                if isinstance(diagnostic, Mapping)
                else None
            )
            stale_filtered_latest = bool(
                runtime_filtered_timestamp
                and raw_latest_timestamp
                and runtime_filtered_timestamp != raw_latest_timestamp
            )
            latest_evaluation = (
                diagnostic
                if instrument != "STK" or latest_gate_passed is True
                else None
            )
            latest_bar_decision = classify_decision(
                evaluation=latest_evaluation,
                diagnostic_evaluation=diagnostic,
                generic_filter_blocked=bool(
                    instrument == "STK" and latest_gate_passed is False
                ),
                warmup_ready=warmup_ready,
            )
            eligibility = deterministic_paper_eligibility(
                binding=binding,
                evaluation=evaluation,
                inventory=inventory,
            )
            latest_eligibility = deterministic_paper_eligibility(
                binding=binding,
                evaluation=latest_evaluation,
                inventory=inventory,
            )
            terminal_match = _terminal_match(
                terminal,
                runtime_id=runtime_id,
                timestamp_utc=boundary_ts,
            )
            owner_present = True if terminal_match else False

            rows.append(
                {
                    "timestamp_utc": _iso(boundary_ts),
                    "bar_timestamp_utc": _iso(ts),
                    "runtime_id": runtime_id,
                    "strategy_id": binding.get("strategy_id"),
                    "strategy_spec_digest": binding.get("strategy_spec_digest"),
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "instrument_class": instrument,
                    "input_data_authority": authority,
                    "crw": condition_projection,
                    "raw_latest_crw": diagnostic_projection,
                    "filter_latest_bar_truth": {
                        "latest_gate_passed": latest_gate_passed,
                        "latest_gate_error": latest_gate_error,
                        "raw_latest_timestamp": raw_latest_timestamp,
                        "raw_latest_close": diagnostic_projection.get("close"),
                        "runtime_filtered_latest_timestamp": runtime_filtered_timestamp,
                        "runtime_filtered_latest_close": condition_projection.get("close"),
                        "runtime_filtered_latest_is_stale": stale_filtered_latest,
                    },
                    "signal": (
                        evaluation.get("signal")
                        if isinstance(evaluation, Mapping)
                        else diagnostic.get("signal")
                        if isinstance(diagnostic, Mapping)
                        else None
                    ),
                    "decision": decision,
                    "latest_bar_decision": latest_bar_decision,
                    "generic_filter_blocked": generic_filter_blocked,
                    "generic_filter_error": generic_filter_error,
                    "filtered_row_count": filtered_rows,
                    "warmup_ready": warmup_ready,
                    "required_target_rows": required_rows,
                    "available_target_rows_at_boundary": int(len(upto)),
                    "bot_inventory": inventory,
                    "paper_eligibility": eligibility,
                    "latest_bar_paper_eligibility": latest_eligibility,
                    "would_have_reached_paper_quote_stage": (
                        eligibility.get("eligible") is True
                    ),
                    "latest_bar_would_have_reached_paper_quote_stage": (
                        latest_eligibility.get("eligible") is True
                    ),
                    "would_have_generated_paper_order": None,
                    "would_have_traded": None,
                    "paper_quantity_if_deterministically_known": eligibility.get(
                        "quantity"
                    ),
                    "paper_order_reason": eligibility.get("state"),
                    "actual_owner_present": owner_present,
                    "actually_observed_by_cloud": bool(terminal_match),
                    "actual_trade": (
                        terminal_match.get("actual_trade_for_this_runtime")
                        if terminal_match
                        else False
                    ),
                    "cloud_terminal_evidence": terminal_match,
                    "duplicate_idempotency_blocked": (
                        terminal_match.get("duplicate_idempotency_blocked")
                        if terminal_match
                        else False
                    ),
                }
            )

    rows.sort(
        key=lambda row: (
            str(row.get("timestamp_utc") or ""),
            str(row.get("runtime_id") or ""),
        )
    )
    summary = _summary(rows)
    candidate_rows = [
        row
        for row in rows
        if row.get("decision")
        in {
            "SIGNAL_FILTER_BLOCKED",
            "ENTRY_CANDIDATE",
            "EXIT_CANDIDATE",
            "DCA_CANDIDATE",
            "ACTIONABLE_CANDIDATE",
        }
    ]
    owner_gap_candidates = [
        row for row in candidate_rows if row.get("actual_owner_present") is False
    ]
    latest_candidate_rows = [
        row
        for row in rows
        if row.get("latest_bar_decision")
        in {
            "SIGNAL_FILTER_BLOCKED",
            "ENTRY_CANDIDATE",
            "EXIT_CANDIDATE",
            "DCA_CANDIDATE",
            "ACTIONABLE_CANDIDATE",
        }
    ]
    latest_owner_gap_candidates = [
        row
        for row in latest_candidate_rows
        if row.get("actual_owner_present") is False
    ]

    return {
        "schema": SCHEMA,
        "ok": True,
        "audit_id": req["audit_id"],
        "generated_at_utc": _iso(datetime.now(timezone.utc)),
        "private_source_sha": req["private_source_sha"],
        "window": {
            "start_utc": req["window_start_utc"],
            "end_utc": req["window_end_utc"],
            "start_authority": req["window_start_authority"],
            "end_authority": req["window_end_authority"],
            "semantics": req["window_semantics"],
            "actual_dot4_shutdown_time_known": False,
            "interpretation": (
                "This is a conservative confirmed-offline window. It begins at "
                "the first durable observation proving .4 was already gone, not "
                "at an inferred shutdown timestamp."
            ),
        },
        "runtime_count": len(bindings),
        "row_count": len(rows),
        "candidate_row_count": len(candidate_rows),
        "owner_gap_candidate_count": len(owner_gap_candidates),
        "latest_bar_candidate_row_count": len(latest_candidate_rows),
        "latest_bar_owner_gap_candidate_count": len(latest_owner_gap_candidates),
        "summary": summary,
        "data_authorities": data_authorities,
        "historical_seed": seed_evidence,
        "rows": rows,
        "safety": {
            "read_only": True,
            "broker_action": False,
            "broker_request_made": False,
            "paper_submit_invoked": False,
            "cancel_invoked": False,
            "flatten_invoked": False,
            "strategy_spec_mutation": False,
            "runtime_authority_mutation": False,
            "account_positions_promoted_to_bot_inventory": False,
            "live_execution_allowed": False,
        },
        "semantics": {
            "would_have_reached_paper_quote_stage": (
                "True only when exact strategy evaluation is actionable and "
                "deterministic pre-quote position/sizing gates can be proven."
            ),
            "would_have_generated_paper_order": (
                "Intentionally null because historical quote acquisition and "
                "broker-submit acceptance are not replayed by this read-only audit."
            ),
            "would_have_traded": (
                "Intentionally null for counterfactual rows. Actual trades require "
                "explicit execution evidence and are never inferred from signals."
            ),
            "actual_owner_present": (
                "Derived only from exact restored terminal-boundary continuity."
            ),
        },
    }


def render_public_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "mmibkr.selected_runtime_missed_trade_audit_public_summary.v1",
        "ok": payload.get("ok") is True,
        "audit_id": payload.get("audit_id"),
        "private_source_sha": payload.get("private_source_sha"),
        "window": payload.get("window"),
        "runtime_count": payload.get("runtime_count"),
        "row_count": payload.get("row_count"),
        "candidate_row_count": payload.get("candidate_row_count"),
        "owner_gap_candidate_count": payload.get("owner_gap_candidate_count"),
        "latest_bar_candidate_row_count": payload.get("latest_bar_candidate_row_count"),
        "latest_bar_owner_gap_candidate_count": payload.get(
            "latest_bar_owner_gap_candidate_count"
        ),
        "summary": payload.get("summary"),
        "historical_seed": payload.get("historical_seed"),
        "safety": payload.get("safety"),
        "detailed_rows_published": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--historical-seed-bars", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--public-summary-output", required=True)
    args = parser.parse_args()

    request = read_json(args.request)
    payload = asyncio.run(
        run_audit(
            repo_root=args.repo_root,
            data_root=args.data_root,
            request=request,
            historical_seed_bars=args.historical_seed_bars or None,
        )
    )
    write_json(args.output, payload)
    write_json(args.public_summary_output, render_public_summary(payload))
    print(
        json.dumps(
            render_public_summary(payload),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
