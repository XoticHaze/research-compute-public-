"""Bounded historical Shared Ridge replay using the *unchanged* pinned frozen modules.

This helper executes inside the existing decrypted ephemeral source capsule. It cannot
reclassify reconstructed decisions as prospectively first-seen, publish source, or trade.
It does not compute model features or refit rules itself. Each as-of call reuses the
exact frozen standalone observer, including its monthly fit and 21-session purge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

SCHEMA = "foundry.forward_native_bounded_replay_request.v1"
COLLECTION_SCHEMA = "foundry.forward_native_bounded_replay_collection.v1"
PROGRAM = "SEMICONDUCTOR_SHARED_RIDGE"
SOURCE_REF = "e73ec9b15180e208de541ce5d5304888e5550433"
START = "2026-09-10"
MAX_DATES = 4
FROZEN_PURGE_SESSIONS = 21
FROZEN_TRAIN = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")


def _day(x: Any) -> str:
    if not isinstance(x, str) or len(x) != 10 or date.fromisoformat(x).isoformat() != x:
        raise ValueError("replay decision date invalid")
    return x


def _completed_et(now_utc: datetime) -> str:
    if now_utc.tzinfo is None:
        raise ValueError("replay clock must be offset aware")
    ny = now_utc.astimezone(ZoneInfo("America/New_York"))
    return (ny.date() if ny.time() >= time(18, 30) else date.fromordinal(ny.date().toordinal() - 1)).isoformat()


def validate_request(request: Any, now_utc: datetime | None = None) -> list[str]:
    if not isinstance(request, dict) or set(request) != {"schema", "program_id", "source_ref", "evidence_class", "decision_dates"}:
        raise ValueError("replay request field-set invalid")
    if (request["schema"] != SCHEMA or request["program_id"] != PROGRAM
            or request["source_ref"] != SOURCE_REF or request["evidence_class"] != "HISTORICAL_REPLAY_NO_PROSPECTIVE_CREDIT"):
        raise ValueError("replay request authority invalid")
    dates = request["decision_dates"]
    if not isinstance(dates, list) or not 1 <= len(dates) <= MAX_DATES:
        raise ValueError("replay request exceeds fixed date bound")
    checked = [_day(d) for d in dates]
    if checked != sorted(set(checked)):
        raise ValueError("replay dates must be distinct ascending")
    cutoff = _completed_et(now_utc or datetime.now(timezone.utc))
    if checked[0] < START or checked[-1] > cutoff:
        raise ValueError("replay date outside settled frozen window")
    return checked


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise RuntimeError("replay native file shape invalid")
    return obj


def _execute_fixed(cmd: list[str], root: Path, timeout: int = 900) -> None:
    # Do not expose native stderr/stdout: paths, model source and feature values are private.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("frozen replay component failed")


def _validate_native(native: dict[str, Any], expected: str) -> None:
    if (native.get("schema") != "foundry.research.semiconductor_external_forward.v1"
            or native.get("generation_bar_date") != expected
            or native.get("research_only") is not True):
        raise RuntimeError("frozen observer asof identity mismatch")
    fit = native.get("monthly_fit") or {}
    if (fit.get("month") != expected[:7] or fit.get("resolved_session_purge") != FROZEN_PURGE_SESSIONS
            or tuple(fit.get("train_universe") or []) != FROZEN_TRAIN
            or fit.get("external_target_rows") != 0
            or not fit.get("fit_anchor_date") or fit["fit_anchor_date"] >= expected
            or not fit.get("safe_last_training_signal_date")
            or fit["safe_last_training_signal_date"] > fit["fit_anchor_date"]):
        raise RuntimeError("monthly fit or frozen purge identity mismatch")
    last = native.get("source_last_dates") or {}
    if not isinstance(last, dict) or len(last) != 15 or any(day != expected for day in last.values()):
        raise RuntimeError("source session not complete across model inputs")
    rows = native.get("observations") or []
    expected_symbols = set((*FROZEN_TRAIN, "NVDA", "AMD", "MU", "AVGO", "MRVL", "MCHP"))
    if len(rows) != 13 or {row.get("symbol") for row in rows} != expected_symbols:
        raise RuntimeError("frozen prediction universe mismatch")
    if any(row.get("bar_date") != expected or type(row.get("positive_value_opportunity")) is not bool
           or row.get("positive_value_opportunity") != (float(row["predicted_fixed20_net_value_bps"]) > 0)
           for row in rows):
        raise RuntimeError("prediction date or positive-value rule mismatch")
    if any(row.get("external_target_history_used_in_fit") is not False for row in rows if row["symbol"] not in FROZEN_TRAIN):
        raise RuntimeError("external target exclusion violated")
    if any(v is not False for v in (native.get("boundaries") or {}).values()):
        raise RuntimeError("unsafe native authority")


def _validate_book(book: dict[str, Any], expected: str, contract: dict[str, Any]) -> None:
    if (book.get("schema") != "foundry.research.semiconductor_three_book_forward_snapshot.v1"
            or book.get("signal_date") != expected or book.get("authority") != "research_only_no_broker_no_promotion"):
        raise RuntimeError("frozen three-book identity mismatch")
    execution = book.get("execution") or {}
    if (execution.get("delay_sessions") != 1 or execution.get("hold_sessions") != 20
            or execution.get("max_concurrent_cohorts") != 20):
        raise RuntimeError("frozen three-book horizon changed")
    for name in ("broker_orders", "live_trading_authority", "promotion_authority", "historical_rule_tuning"):
        if (book.get("boundaries") or {}).get(name) is not False:
            raise RuntimeError("frozen paper book escalated authority")
    if contract.get("source_prediction_schema") != "foundry.research.semiconductor_external_forward.v1":
        raise RuntimeError("frozen contract source identity changed")


def _validate_adapter(adapter: dict[str, Any], native: dict[str, Any], expected: str) -> None:
    if (adapter.get("schema") != "foundry.forward_program_adapter.v1"
            or adapter.get("program_id") != PROGRAM or adapter.get("signal_date") != expected):
        raise RuntimeError("dated adapter identity invalid")
    vals = (adapter.get("signal") or {}).get("predicted_fixed20_net_value_bps") or {}
    native_vals = {row["symbol"]: float(row["predicted_fixed20_net_value_bps"]) for row in native["observations"]}
    if set(vals) != set(native_vals) or any(abs(float(vals[k])-native_vals[k]) > 1e-8 for k in native_vals):
        raise RuntimeError("adapter changed frozen model predictions")
    bounds = adapter.get("boundaries") or {}
    if any(bounds.get(name) is not False for name in ("broker_action", "live_trading_change", "promotion_authority", "runtime_mutation")):
        raise RuntimeError("unsafe dated adapter")


def _record(day: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"signal_date": day, "content": data, "content_sha256": _digest(data)}


def execute_bounded(root: Path, adapter_script: Path, request: dict[str, Any], *, now_utc: datetime | None = None) -> tuple[Path, Path, Path]:
    dates = validate_request(request, now_utc)
    if not adapter_script.is_file() or not (root / "research/semiconductor_external_forward_standalone_20260910.py").is_file():
        raise RuntimeError("replay pinned module missing")
    contract_path = root / "research/semiconductor_three_book_forward_contract_20260910.json"
    contract = _read(contract_path)
    if (contract.get("prospective_start_signal_date") != START
            or (contract.get("scientific_boundaries") or {}).get("execution_delay_sessions") != 1
            or (contract.get("scientific_boundaries") or {}).get("hold_sessions") != 20
            or (contract.get("scientific_boundaries") or {}).get("stock_round_trip_cost_bps") != 25):
        raise RuntimeError("frozen contract changed")
    root = root.resolve()
    outdir = root / "artifacts/bounded-replay-r1"
    outdir.mkdir(parents=True, exist_ok=True)
    collection = {"native": [], "paper_book": [], "adapter": []}
    for day in dates:
        native_path = outdir / f"{day}.native.json"
        book_path = outdir / f"{day}.book.json"
        adapter_path = outdir / f"{day}.adapter.json"
        _execute_fixed([sys.executable, "-m", "research.semiconductor_external_forward_standalone_20260910", "--asof", day, "--output", str(native_path.relative_to(root))], root)
        native = _read(native_path)
        _validate_native(native, day)
        _execute_fixed([sys.executable, "-m", "research.semiconductor_three_book_forward_20260910", "--prediction", str(native_path.relative_to(root)), "--contract", str(contract_path.relative_to(root)), "--output", str(book_path.relative_to(root))], root)
        book = _read(book_path)
        _validate_book(book, day, contract)
        _execute_fixed([sys.executable, str(adapter_script), "--program", PROGRAM, "--input", str(native_path), "--book", str(book_path), "--output", str(adapter_path)], root)
        adapter = _read(adapter_path)
        _validate_adapter(adapter, native, day)
        collection["native"].append(_record(day, native))
        collection["paper_book"].append(_record(day, book))
        collection["adapter"].append(_record(day, adapter))
    paths = []
    for kind, name in (("native", "native.json"), ("paper_book", "paper-book.json"), ("adapter", "adapter.json")):
        data = {"schema": COLLECTION_SCHEMA, "program_id": PROGRAM, "source_ref": SOURCE_REF,
                "evidence_class": "HISTORICAL_REPLAY_NO_PROSPECTIVE_CREDIT", "kind": kind,
                "decision_dates": dates, "records": collection[kind],
                "generated_at": datetime.now(timezone.utc).isoformat()}
        target = outdir / name
        target.write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        paths.append(target)
    return tuple(paths)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--adapter-script", type=Path, required=True)
    p.add_argument("--request", type=Path, required=True)
    args = p.parse_args()
    try:
        request = _read(args.request)
        output = execute_bounded(args.root, args.adapter_script, request)
    except Exception:
        # Private native output must not escape through console/logs.
        print("BOUNDED_REPLAY_REJECTED")
        return 1
    print(json.dumps({"status": "PASS", "encrypted_return_required": True,
                      "decision_count": len(request["decision_dates"]), "outputs": [p.name for p in output]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())