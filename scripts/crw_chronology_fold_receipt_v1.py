from __future__ import annotations

"""Deterministic bounded chronology-fold aggregation for sanitized CRW receipts.

Consumes canonical backtest rows inside the trusted dispatcher boundary and emits
aggregate-only fold metrics. Raw timestamped rows never cross the public receipt.
"""

from datetime import datetime, timezone
from typing import Any

SCHEMA = "crw.chronology_fold_receipt.v1"
_TIMESTAMP_KEYS = ("exit_timestamp", "exit_time", "timestamp", "date", "entry_timestamp", "entry_time")
_PNL_KEYS = ("net_pnl", "pnl", "realized_pnl", "profit")


def _timestamp(row: dict[str, Any]) -> tuple[float, str] | None:
    for key in _TIMESTAMP_KEYS:
        raw = row.get(key)
        if raw in (None, ""):
            continue
        text = str(raw).strip()
        try:
            normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp(), key
        except ValueError:
            continue
    return None


def _pnl(row: dict[str, Any]) -> tuple[float, str] | None:
    for key in _PNL_KEYS:
        raw = row.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw), key
        except (TypeError, ValueError):
            continue
    return None


def chronology_fold_receipt(rows: Any, *, fold_count: int = 4) -> dict[str, Any]:
    if not isinstance(rows, list):
        rows = []
    if fold_count < 2 or fold_count > 12:
        raise ValueError("fold_count must be within 2..12")

    parsed: list[tuple[float, float, str, str]] = []
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected += 1
            continue
        ts = _timestamp(row)
        pnl = _pnl(row)
        if ts is None or pnl is None:
            rejected += 1
            continue
        parsed.append((ts[0], pnl[0], ts[1], pnl[1]))
    parsed.sort(key=lambda item: item[0])

    folds = []
    n = len(parsed)
    for idx in range(fold_count):
        lo = (n * idx) // fold_count
        hi = (n * (idx + 1)) // fold_count
        part = parsed[lo:hi]
        pnls = [item[1] for item in part]
        folds.append({
            "fold": idx + 1,
            "trade_count": len(part),
            "net_pnl": sum(pnls),
            "win_count": sum(1 for value in pnls if value > 0),
            "loss_count": sum(1 for value in pnls if value < 0),
            "flat_count": sum(1 for value in pnls if value == 0),
        })

    return {
        "schema": SCHEMA,
        "fold_count": fold_count,
        "source_row_count": len(rows),
        "parsed_trade_count": n,
        "rejected_row_count": rejected,
        "timestamp_keys_consumed": sorted({item[2] for item in parsed}),
        "pnl_keys_consumed": sorted({item[3] for item in parsed}),
        "folds": folds,
        "raw_rows_emitted": False,
    }
