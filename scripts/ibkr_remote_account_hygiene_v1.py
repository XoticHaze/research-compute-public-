from __future__ import annotations

"""Execute one operator-authorized paper-account hygiene flatten via canonical MM routes.

This module owns no broker client and no strategy authority. It validates the
private command against current broker truth, uses the existing
/strategy/ibkr-paper-flatten-submit-suite route, and refuses mutation unless the
current paper account exactly matches the ownership-authorized position snapshot.
"""

import math
from datetime import datetime
from typing import Any, Callable, Mapping

from scripts import ibkr_remote_selected_runtime_command_capsule_v2 as capsule_v2

SCHEMA = "mmibkr.remote_paper_account_hygiene_receipt.v1"
FLATTEN_ROUTE = "/strategy/ibkr-paper-flatten-submit-suite"
PREVIEW_ROUTE = "/strategy/ibkr-paper-flatten-preview-suite"
ROUTE_ACK = "IBKR_PAPER_FLATTEN_ACK_13Z39"
PREFLIGHT_ONLY_BLOCKERS = {
    "operator_approved_required_13z39",
    "ibkr_paper_flatten_ack_required_13z39",
}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _broker_position_index(rows: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    index: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    if not isinstance(rows, list):
        return {}, ["broker_position_rows_missing"]
    for raw in rows:
        if not isinstance(raw, Mapping):
            problems.append("broker_position_row_invalid")
            continue
        symbol = str(raw.get("symbol") or "").strip().upper()
        contract = _mapping(raw.get("contract"))
        con_id = int(raw.get("conId") or contract.get("conId") or 0)
        sec_type = str(contract.get("secType") or "").strip().upper()
        position = _finite(raw.get("position"))
        if not symbol or con_id <= 0 or sec_type not in {"STK", "ETF"} or position in {None, 0.0}:
            problems.append("broker_position_identity_invalid")
            continue
        if symbol in index:
            problems.append(f"duplicate_broker_symbol:{symbol}")
            continue
        index[symbol] = {
            "symbol": symbol,
            "conId": con_id,
            "secType": sec_type,
            "position": float(position),
        }
    return index, problems


def _expected_index(request: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["symbol"]).upper(): dict(row)
        for row in request.get("expected_positions") or []
        if isinstance(row, Mapping)
    }


def _position_truth_compare(
    expected: Mapping[str, Mapping[str, Any]],
    actual: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    problems: list[str] = []
    expected_symbols = set(expected)
    actual_symbols = set(actual)
    for symbol in sorted(expected_symbols - actual_symbols):
        problems.append(f"expected_position_missing:{symbol}")
    for symbol in sorted(actual_symbols - expected_symbols):
        problems.append(f"unexpected_broker_position:{symbol}")
    for symbol in sorted(expected_symbols & actual_symbols):
        left = expected[symbol]
        right = actual[symbol]
        if int(left.get("conId") or 0) != int(right.get("conId") or 0):
            problems.append(f"position_conid_mismatch:{symbol}")
        if str(left.get("secType") or "").upper() != str(right.get("secType") or "").upper():
            problems.append(f"position_sectype_mismatch:{symbol}")
        a = _finite(left.get("position"))
        b = _finite(right.get("position"))
        if a is None or b is None or abs(a - b) > 1e-9:
            problems.append(f"position_quantity_mismatch:{symbol}")
    return problems


def _chunks(symbols: list[str], size: int) -> list[list[str]]:
    return [symbols[index:index + size] for index in range(0, len(symbols), size)]


def _guard_payload(symbols: list[str], *, approved: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "symbols": list(symbols),
        "max_symbols": len(symbols),
        "order_type": "AUTO",
        "tif": "DAY",
        "session_policy": "auto",
        "outside_rth": "auto",
        "fallback_policy": "none",
        "operator_approved": bool(approved),
    }
    if approved:
        payload["ibkr_paper_flatten_ack_13z39"] = ROUTE_ACK
    return payload


def _session_gate(preflight: Mapping[str, Any], symbols: list[str]) -> list[str]:
    problems: list[str] = []
    items = [
        row for row in preflight.get("preview_items") or []
        if isinstance(row, Mapping)
    ]
    by_symbol = {str(row.get("symbol") or "").strip().upper(): row for row in items}
    for symbol in symbols:
        row = by_symbol.get(symbol)
        if row is None:
            problems.append(f"flatten_preview_item_missing:{symbol}")
            continue
        session = _mapping(row.get("execution_session"))
        resolved = _mapping(row.get("resolved_order"))
        if str(session.get("market_state") or "").lower() != "regular":
            problems.append(f"regular_session_required:{symbol}")
        if session.get("submit_allowed") is not True:
            problems.append(f"session_submit_not_allowed:{symbol}")
        if str(resolved.get("order_type") or "").upper() != "MKT":
            problems.append(f"regular_session_market_order_required:{symbol}")
        route_blockers = list(row.get("blockers") or []) + list(row.get("session_policy_blockers") or [])
        for blocker in route_blockers:
            problems.append(f"{symbol}:{blocker}")
    return problems


def validate_runtime(
    runtime: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    now_utc: datetime | None = None,
) -> None:
    if str(runtime.get("mode") or "") != capsule_v2.HYGIENE_MODE:
        raise RuntimeError("account hygiene runtime mode mismatch")
    if runtime.get("paper_only") is not True:
        raise RuntimeError("account hygiene runtime must be paper only")
    if runtime.get("live_trading_change") is not False:
        raise RuntimeError("account hygiene live trading change rejected")
    authority = _mapping(request.get("ownership_authority"))
    capsule_v2.validate_hygiene_snapshot_age(authority, now_utc=now_utc)
    if str(runtime.get("mmibkr_head") or "").lower() != str(authority.get("runtime_source_sha") or "").lower():
        raise RuntimeError("account hygiene source must match ownership snapshot runtime source")
    if authority.get("strategy_owned_positions") != []:
        raise RuntimeError("account hygiene selected-runtime inventory must be flat")
    if authority.get("operator_approved") is not True:
        raise RuntimeError("account hygiene operator approval missing")
    if str(authority.get("operator_ack") or "") != capsule_v2.HYGIENE_OPERATOR_ACK:
        raise RuntimeError("account hygiene operator ack mismatch")


def execute_account_hygiene(
    *,
    runtime: Mapping[str, Any],
    request: Mapping[str, Any],
    send: Callable[..., tuple[int, dict[str, Any]]],
    run_id: str,
    public_head: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    validate_runtime(runtime, request, now_utc=now_utc)
    expected = _expected_index(request)
    symbols = [str(row["symbol"]).upper() for row in request["expected_positions"]]
    batch_size = int(request["batch_size"])
    batches = _chunks(symbols, batch_size)
    authority = _mapping(request.get("ownership_authority"))

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": False,
        "status": "PREFLIGHT_PENDING",
        "github": {"run_id": str(run_id), "public_head": str(public_head)},
        "mmibkr": {
            "head": runtime.get("mmibkr_head"),
            "source_archive_sha256": runtime.get("source_archive_sha256"),
        },
        "command": {
            "command_id": request.get("command_id"),
            "source_ref": request.get("source_ref"),
            "execute_requested": request.get("execute") is True,
            "expected_position_count": len(expected),
            "batch_size": batch_size,
            "batch_count": len(batches),
        },
        "ownership_authority": {
            "schema": authority.get("schema"),
            "operator_snapshot_sha256": authority.get("operator_snapshot_sha256"),
            "snapshot_generated_at_utc": authority.get("snapshot_generated_at_utc"),
            "runtime_source_sha": authority.get("runtime_source_sha"),
            "ownership_source": authority.get("ownership_source"),
            "strategy_owned_position_count": len(authority.get("strategy_owned_positions") or []),
            "account_position_count": authority.get("account_position_count"),
            "operator_approved": authority.get("operator_approved") is True,
            "operator_ack_match": authority.get("operator_ack") == capsule_v2.HYGIENE_OPERATOR_ACK,
        },
        "preflight": {
            "broker_truth_match": False,
            "open_orders_clean": False,
            "regular_session_ready": False,
            "problems": [],
            "batches": [],
        },
        "execution": {
            "called": False,
            "batches": [],
            "broker_order_placed": False,
        },
        "final_reconciliation": {},
        "cleanup": {
            "automatic_cleanup": False,
            "exact_cancel_called": False,
            "flatten_called": False,
            "global_cancel_called": False,
        },
        "authority": {
            "canonical_flatten_route": FLATTEN_ROUTE,
            "paper_only": True,
            "account_hygiene_only": True,
            "cloud_strategy_authority": False,
            "cloud_execution_policy_authority": False,
            "direct_broker_client_used": False,
            "runtime_activation_authority": False,
            "global_cancel_allowed": False,
            "live_execution_allowed": False,
        },
    }

    preview_status, preview = send(
        "POST",
        PREVIEW_ROUTE,
        payload={
            "candidate_limit": 50,
            "preview_limit": 25,
            "batch_limit": 25,
            "order_type": "AUTO",
            "tif": "DAY",
        },
        timeout=120.0,
    )
    candidates = preview.get("flatten_candidates") or []
    actual, actual_problems = _broker_position_index(candidates)
    truth_problems = [
        *actual_problems,
        *_position_truth_compare(expected, actual),
    ]
    if preview_status != 200 or preview.get("ok") is not True:
        truth_problems.append("canonical_flatten_preview_unavailable")
    if int(preview.get("position_count") or -1) != len(expected):
        truth_problems.append("broker_position_count_mismatch")
    if int(preview.get("open_order_count") or 0) != 0:
        truth_problems.append("open_orders_present_before_hygiene")

    receipt["preflight"]["broker_truth_match"] = not any(
        problem.startswith(("expected_position_", "unexpected_broker_", "position_", "broker_position_"))
        for problem in truth_problems
    )
    receipt["preflight"]["open_orders_clean"] = int(preview.get("open_order_count") or 0) == 0

    guard_problems: list[str] = []
    for batch_index, batch in enumerate(batches, start=1):
        status, guarded = send(
            "POST",
            FLATTEN_ROUTE,
            payload=_guard_payload(batch, approved=False),
            timeout=180.0,
        )
        blockers = set(str(value) for value in guarded.get("blockers") or [])
        unexpected = sorted(blockers - PREFLIGHT_ONLY_BLOCKERS)
        missing = sorted(PREFLIGHT_ONLY_BLOCKERS - blockers)
        session_problems = _session_gate(guarded, batch)
        row = {
            "batch_index": batch_index,
            "symbols": batch,
            "http_status": status,
            "place_order_called": bool(guarded.get("place_order_called")),
            "broker_order_placed": bool(guarded.get("broker_order_placed")),
            "route_blockers": sorted(blockers),
            "unexpected_route_blockers": unexpected,
            "required_guard_blockers_missing": missing,
            "session_problems": session_problems,
        }
        receipt["preflight"]["batches"].append(row)
        if status not in {200, 409}:
            guard_problems.append(f"guard_preview_http_status:{batch_index}:{status}")
        if row["place_order_called"] or row["broker_order_placed"]:
            guard_problems.append(f"guard_preview_mutation_detected:{batch_index}")
        guard_problems.extend(f"batch_{batch_index}:{value}" for value in unexpected)
        guard_problems.extend(f"batch_{batch_index}:missing_{value}" for value in missing)
        guard_problems.extend(f"batch_{batch_index}:{value}" for value in session_problems)

    problems = [*truth_problems, *guard_problems]
    receipt["preflight"]["problems"] = problems
    receipt["preflight"]["regular_session_ready"] = not any(
        "regular_session" in problem or "session_" in problem
        for problem in guard_problems
    )
    if problems:
        receipt["status"] = "PREFLIGHT_BLOCKED"
        receipt["ok"] = request.get("execute") is not True
        return receipt

    receipt["status"] = "PREFLIGHT_READY"
    receipt["ok"] = True
    if request.get("execute") is not True:
        return receipt

    receipt["execution"]["called"] = True
    for batch_index, batch in enumerate(batches, start=1):
        status, result = send(
            "POST",
            FLATTEN_ROUTE,
            payload=_guard_payload(batch, approved=True),
            timeout=300.0,
        )
        batch_receipt = {
            "batch_index": batch_index,
            "symbols": batch,
            "http_status": status,
            "ok": result.get("ok") is True,
            "status": result.get("status"),
            "place_order_called": bool(result.get("place_order_called")),
            "broker_order_placed": bool(result.get("broker_order_placed")),
            "blockers": list(result.get("blockers") or []),
            "remaining_symbols": list((_mapping(result.get("reconcile"))).get("remaining_symbols") or []),
            "open_order_count_after": (_mapping(result.get("reconcile"))).get("open_order_count_after"),
        }
        receipt["execution"]["batches"].append(batch_receipt)
        receipt["cleanup"]["flatten_called"] = bool(
            receipt["cleanup"]["flatten_called"] or batch_receipt["place_order_called"]
        )
        receipt["execution"]["broker_order_placed"] = bool(
            receipt["execution"]["broker_order_placed"]
            or batch_receipt["broker_order_placed"]
        )
        if (
            status != 200
            or result.get("ok") is not True
            or result.get("status") != "flatten_reconciled"
            or batch_receipt["remaining_symbols"]
            or int(batch_receipt["open_order_count_after"] or 0) != 0
        ):
            receipt["ok"] = False
            receipt["status"] = "HYGIENE_BATCH_FAILED_CLOSED"
            return receipt

    final_status, final_preview = send(
        "POST",
        PREVIEW_ROUTE,
        payload={
            "candidate_limit": 50,
            "preview_limit": 25,
            "batch_limit": 25,
            "order_type": "AUTO",
            "tif": "DAY",
        },
        timeout=120.0,
    )
    final_position_count = int(final_preview.get("position_count") or 0)
    final_open_order_count = int(final_preview.get("open_order_count") or 0)
    receipt["final_reconciliation"] = {
        "http_status": final_status,
        "ok": final_preview.get("ok") is True,
        "position_count": final_position_count,
        "open_order_count": final_open_order_count,
        "account_flat": final_position_count == 0,
        "open_orders_clean": final_open_order_count == 0,
    }
    receipt["ok"] = bool(
        final_status == 200
        and final_preview.get("ok") is True
        and final_position_count == 0
        and final_open_order_count == 0
    )
    receipt["status"] = (
        "PAPER_ACCOUNT_HYGIENE_RECONCILED"
        if receipt["ok"]
        else "PAPER_ACCOUNT_HYGIENE_RECONCILIATION_INCOMPLETE"
    )
    return receipt
