from __future__ import annotations

"""Ephemeral public executor for one MM-IBKR selected-runtime paper proof.

This driver contains no broker client and no order-policy implementation. Every
broker mutation is delegated to canonical MM-IBKR control routes from the exact
private source head materialized by the encrypted rendezvous. The public side
only enforces the proof envelope, zero-baseline precondition, exact cleanup, and
final reconciliation. Global cancel and live trading are prohibited.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHEMA = "mmibkr.remote_selected_runtime_paper_proof_receipt.v1"
MODE = "paper_submit_proof"
SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")

JsonSender = Callable[..., tuple[int, dict[str, Any]]]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "live"}


def _reject_live(value: Any, path: str = "request") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower()
            child_path = f"{path}.{raw_key}"
            if key in {
                "enable_live_trading",
                "live_submit_enabled",
                "live_allowed",
                "live_mode_enabled",
                "live_execution_allowed",
            } and _truthy(child):
                raise RuntimeError(f"live_authority_rejected:{child_path}")
            if key in {"trading_mode", "account_mode"} and str(child or "").strip().lower() == "live":
                raise RuntimeError(f"live_mode_rejected:{child_path}")
            _reject_live(child, child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_live(child, f"{path}[{index}]")


def _http_json(
    base_url: str,
    method: str,
    route: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, Any]]:
    query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = base_url.rstrip("/") + route + (("?" + query) if query else "")
    data = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as response:
            status = int(response.getcode())
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except Exception:
        parsed = {"ok": False, "error": "non_json_response"}
    return status, parsed if isinstance(parsed, dict) else {"ok": False, "raw_type": type(parsed).__name__}


def _request_sender(base_url: str) -> JsonSender:
    def send(method: str, route: str, *, payload=None, params=None, timeout=60.0):
        return _http_json(base_url, method, route, payload=payload, params=params, timeout=timeout)
    return send


def _walk(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first(node: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in node and node.get(name) not in (None, ""):
            return node.get(name)
    return None


def _extract_order_identity(body: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    wanted = symbol.upper()
    best: dict[str, Any] = {}
    for node in _walk(body):
        node_symbol = str(node.get("symbol") or node.get("ticker") or "").strip().upper()
        if node_symbol and node_symbol != wanted:
            continue
        candidate = {
            "order_id": _first(node, ("order_id", "orderId", "orderID")),
            "perm_id": _first(node, ("perm_id", "permId", "permID")),
            "client_id": _first(node, ("client_id", "clientId")),
            "order_ref": _first(node, ("order_ref", "orderRef", "order_reference")),
            "status": _first(node, ("status", "orderStatus")),
            "filled": _first(node, ("filled", "filledQuantity")),
            "remaining": _first(node, ("remaining", "remainingQuantity")),
            "avg_fill_price": _first(node, ("avg_fill_price", "avgFillPrice")),
            "symbol": wanted,
        }
        if any(candidate.get(key) not in (None, "") for key in ("order_id", "perm_id", "order_ref")):
            best = candidate
            if candidate.get("status"):
                break
    return {k: v for k, v in best.items() if v not in (None, "")}


def _open_order_rows(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = body.get("orders")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    for node in _walk(body):
        rows = node.get("orders")
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, Mapping)]
    return []


def _open_counts(body: Mapping[str, Any], symbol: str) -> tuple[int, int]:
    rows = _open_order_rows(body)
    if rows:
        unresolved = [row for row in rows if row.get("unresolved") is not False]
        target = [row for row in unresolved if str(row.get("symbol") or "").strip().upper() == symbol.upper()]
        return len(unresolved), len(target)
    global_count = int(body.get("unresolved_open_order_count") or body.get("open_order_count") or 0)
    # No row-level target identity means we cannot prove a nonzero count belongs
    # elsewhere, so fail closed by treating it as target scope too.
    return global_count, global_count


def _position_for_symbol(flatten_preview: Mapping[str, Any], symbol: str) -> float:
    wanted = symbol.upper()
    for row in flatten_preview.get("flatten_candidates") or []:
        if isinstance(row, Mapping) and str(row.get("symbol") or "").strip().upper() == wanted:
            try:
                return float(row.get("position") or 0.0)
            except (TypeError, ValueError):
                return 0.0
    for item in flatten_preview.get("single_previews") or []:
        if not isinstance(item, Mapping) or str(item.get("symbol") or "").strip().upper() != wanted:
            continue
        position = item.get("position") if isinstance(item.get("position"), Mapping) else {}
        try:
            return float(position.get("position") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _validate_authorized_request(runtime: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    if runtime.get("mode") != MODE:
        raise RuntimeError("paper_submit_proof_runtime_required")
    if runtime.get("read_only_api") != "no":
        raise RuntimeError("paper_submit_proof_requires_read_only_api_no")
    if runtime.get("paper_only") is not True or runtime.get("live_trading_change") is not False:
        raise RuntimeError("paper_only_runtime_boundary_required")
    cleanup = runtime.get("cleanup") if isinstance(runtime.get("cleanup"), Mapping) else {}
    expected_cleanup = {
        "cancel_open_order": True,
        "flatten_filled_position": True,
        "require_zero_baseline": True,
        "allow_global_cancel": False,
    }
    if dict(cleanup) != expected_cleanup:
        raise RuntimeError("paper_proof_cleanup_contract_mismatch")

    _reject_live(request)
    command_id = str(request.get("command_id") or "").strip().lower()
    source_ref = str(request.get("source_ref") or "").strip()
    payload = request.get("canonical_submit_payload") if isinstance(request.get("canonical_submit_payload"), Mapping) else {}
    authority = request.get("selected_runtime_authority") if isinstance(request.get("selected_runtime_authority"), Mapping) else {}
    if not SHA256_ID.fullmatch(command_id):
        raise RuntimeError("command_id_invalid")
    if not source_ref:
        raise RuntimeError("source_ref_required")
    if not payload:
        raise RuntimeError("canonical_submit_payload_required")
    if not authority:
        raise RuntimeError("selected_runtime_authority_required")
    if authority.get("authority_source") != "MM-IBKR selected_runtime.execution_policy":
        raise RuntimeError("selected_runtime_authority_source_mismatch")
    if authority.get("paper_submit_enabled") is not True or authority.get("live_submit_enabled") is not False:
        raise RuntimeError("selected_runtime_paper_only_authority_required")

    runtime_id = str(authority.get("runtime_id") or "").strip()
    symbol = str(authority.get("symbol") or "").strip().upper()
    spec = str(authority.get("strategy_spec_digest") or "").strip()
    if not runtime_id or not symbol or not spec:
        raise RuntimeError("selected_runtime_identity_incomplete")
    if str(payload.get("runtime_id") or "").strip() != runtime_id:
        raise RuntimeError("canonical_payload_runtime_id_mismatch")
    if str(payload.get("symbol") or "").strip().upper() != symbol:
        raise RuntimeError("canonical_payload_symbol_mismatch")
    if not str(payload.get("idempotency_key") or "").strip():
        raise RuntimeError("canonical_payload_idempotency_key_required")
    return {
        "command_id": command_id,
        "source_ref": source_ref,
        "payload": dict(payload),
        "authority": dict(authority),
        "runtime_id": runtime_id,
        "symbol": symbol,
        "strategy_spec_digest": spec,
        "cleanup": expected_cleanup,
    }


def _flatten_snapshot(send: JsonSender, symbol: str) -> tuple[int, dict[str, Any]]:
    return send(
        "POST",
        "/strategy/ibkr-paper-flatten-preview-suite",
        payload={"preview_symbols": [symbol], "batch_symbols": [symbol], "candidate_limit": 50, "preview_limit": 1, "batch_limit": 1},
        timeout=60.0,
    )


def _positive_price(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _canonical_quote_final_limit(body: Mapping[str, Any]) -> float | None:
    if not isinstance(body, Mapping):
        return None
    limit_policy = body.get("limit_price_policy") if isinstance(body.get("limit_price_policy"), Mapping) else {}
    lmt_chase = body.get("lmt_chase_policy") if isinstance(body.get("lmt_chase_policy"), Mapping) else {}
    for value in (
        body.get("final_limit_price"),
        body.get("limit_price"),
        body.get("lmtPrice"),
        limit_policy.get("final_limit_price"),
        lmt_chase.get("base_limit_price"),
        lmt_chase.get("limit_price"),
    ):
        price = _positive_price(value)
        if price is not None:
            return price
    return None


def _jit_refresh_authorized_lmt_payload(
    *,
    send: JsonSender,
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    submit_payload = dict(payload)
    requested = submit_payload.get("remote_proof_refresh_limit_price") is True
    if not requested:
        return submit_payload, {"requested": False, "performed": False, "ok": None}

    order_type = str(submit_payload.get("order_type") or submit_payload.get("orderType") or "").strip().upper()
    if order_type != "LMT":
        return None, {
            "requested": True,
            "performed": False,
            "ok": False,
            "blockers": ["jit_quote_refresh_requires_lmt_order"],
        }

    quote_payload = dict(submit_payload)
    quote_payload["require_executable_quote"] = True
    # The command owns whether refresh is authorized; the canonical MM route owns
    # market-data/contract/session/limit policy. Cloud code only consumes its
    # returned final limit and never changes action, quantity, runtime, or contract.
    status, quote = send(
        "POST",
        "/strategy/ibkr-paper-quote-snapshot",
        payload=quote_payload,
        timeout=90.0,
    )
    final_limit = _canonical_quote_final_limit(quote)
    blockers = list(quote.get("blockers") or []) if isinstance(quote, Mapping) else []
    ok = bool(status == 200 and isinstance(quote, Mapping) and quote.get("ok") is True and final_limit is not None)
    evidence = {
        "requested": True,
        "performed": True,
        "ok": ok,
        "http_status": status,
        "status": quote.get("status") if isinstance(quote, Mapping) else None,
        "final_limit_price": final_limit,
        "executable_quote_available": quote.get("executable_quote_available") if isinstance(quote, Mapping) else None,
        "blockers": blockers,
        "canonical_route": "/strategy/ibkr-paper-quote-snapshot",
        "price_fields_only": True,
    }
    if not ok:
        if final_limit is None:
            evidence["blockers"] = sorted(set(blockers + ["canonical_quote_final_limit_required"]))
        return None, evidence

    for key in (
        "remote_proof_refresh_limit_price",
        "remote_proof_candidate_quote_received_at_utc",
        "remote_proof_candidate_quote_max_age_sec",
    ):
        submit_payload.pop(key, None)
    submit_payload.update({
        "limit_price": final_limit,
        "lmtPrice": final_limit,
        "reference_price": final_limit,
        "marketPrice": final_limit,
        "limit_price_source": "remote_proof_jit_canonical_quote_snapshot",
        "requested_price_source": "remote_proof_jit_canonical_quote_snapshot",
        "quote_materialized_limit_price_14th27b": final_limit,
    })
    return submit_payload, evidence


def execute_paper_proof(
    *,
    runtime: Mapping[str, Any],
    request: Mapping[str, Any],
    send: JsonSender,
    run_id: str,
    public_head: str,
) -> dict[str, Any]:
    auth = _validate_authorized_request(runtime, request)
    symbol = auth["symbol"]

    health_status, health = send("GET", "/healthz", timeout=15.0)
    open_status, open_before = send("GET", "/strategy/ibkr-paper-open-orders", params={"symbol": symbol}, timeout=45.0)
    pos_status, position_before = _flatten_snapshot(send, symbol)
    global_open_before, target_open_before = _open_counts(open_before, symbol)
    target_position_before = _position_for_symbol(position_before, symbol)

    preflight_blockers: list[str] = []
    if health_status != 200 or health.get("ok") is False:
        preflight_blockers.append("canonical_runtime_not_healthy")
    if open_status != 200 or open_before.get("ok") is not True:
        preflight_blockers.append("open_order_truth_unavailable")
    if pos_status != 200 or position_before.get("ok") is not True:
        preflight_blockers.append("position_truth_unavailable")
    if global_open_before != 0:
        preflight_blockers.append("zero_baseline_open_orders_required")
    if abs(target_position_before) > 1e-12:
        preflight_blockers.append("zero_baseline_target_position_required")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": False,
        "status": "BLOCKED_PRE_SUBMIT" if preflight_blockers else "SUBMIT_PENDING",
        "github": {"run_id": str(run_id), "public_head": str(public_head)},
        "mmibkr": {
            "head": runtime.get("mmibkr_head"),
            "source_archive_sha256": runtime.get("source_archive_sha256"),
        },
        "command": {
            "command_id": auth["command_id"],
            "source_ref": auth["source_ref"],
            "runtime_id": auth["runtime_id"],
            "strategy_id": auth["authority"].get("strategy_id"),
            "strategy_spec_digest": auth["strategy_spec_digest"],
            "symbol": symbol,
            "timeframe": auth["authority"].get("timeframe"),
        },
        "preflight": {
            "health_http_status": health_status,
            "open_orders_http_status": open_status,
            "positions_http_status": pos_status,
            "global_open_order_count": global_open_before,
            "target_open_order_count": target_open_before,
            "target_position": target_position_before,
            "blockers": preflight_blockers,
        },
        "quote_refresh": {"requested": False, "performed": False, "ok": None},
        "submit": {"called": False, "http_status": None, "ok": False, "broker_order_placed": False, "order_identity": {}},
        "cleanup": {"exact_cancel_called": False, "exact_cancel_ok": None, "flatten_called": False, "flatten_ok": None, "global_cancel_called": False},
        "final_reconciliation": {},
        "authority": {
            "canonical_submit_route": "/strategy/ibkr-paper-order-submit",
            "canonical_cancel_route": "/strategy/ibkr-paper-order-cancel-submit",
            "canonical_flatten_route": "/strategy/ibkr-paper-flatten-submit-suite",
            "cloud_strategy_authority": False,
            "cloud_execution_policy_authority": False,
            "direct_broker_client_used": False,
            "global_cancel_allowed": False,
            "live_execution_allowed": False,
        },
    }
    if preflight_blockers:
        return receipt

    submit_payload, quote_refresh = _jit_refresh_authorized_lmt_payload(send=send, payload=auth["payload"])
    receipt["quote_refresh"] = quote_refresh
    if submit_payload is None:
        receipt["status"] = "JIT_QUOTE_REFRESH_BLOCKED"
        return receipt

    submit_status, submit = send("POST", "/strategy/ibkr-paper-order-submit", payload=submit_payload, timeout=120.0)
    identity = _extract_order_identity(submit, symbol)
    guards = submit.get("guards") if isinstance(submit.get("guards"), Mapping) else {}
    canonical_runtime_id = str(guards.get("selected_runtime_id") or "").strip()
    authority_mismatch = bool(canonical_runtime_id and canonical_runtime_id != auth["runtime_id"])
    receipt["submit"] = {
        "called": True,
        "http_status": submit_status,
        "ok": submit.get("ok") is True,
        "status": submit.get("status"),
        "place_order_called": bool(submit.get("place_order_called")),
        "broker_order_placed": bool(submit.get("broker_order_placed")),
        "order_identity": identity,
        "canonical_selected_runtime_id": canonical_runtime_id or None,
        "authority_match": not authority_mismatch,
        "blockers": list(submit.get("blockers") or []),
    }
    if authority_mismatch:
        receipt["status"] = "CANONICAL_AUTHORITY_MISMATCH"
        return receipt

    # A canonical block before placeOrder is a valid fail-closed execution result.
    if not bool(submit.get("place_order_called") or submit.get("broker_order_placed")):
        receipt["status"] = "CANONICAL_SUBMIT_BLOCKED"
        receipt["ok"] = submit_status in {200, 409} and not authority_mismatch
        return receipt

    open_status, open_after_submit = send("GET", "/strategy/ibkr-paper-open-orders", params={"symbol": symbol}, timeout=45.0)
    pos_status, pos_after_submit = _flatten_snapshot(send, symbol)
    _, target_open_after_submit = _open_counts(open_after_submit, symbol)
    target_position_after_submit = _position_for_symbol(pos_after_submit, symbol)

    if target_open_after_submit > 0:
        if not identity.get("order_id"):
            receipt["status"] = "OPEN_ORDER_IDENTITY_MISSING"
            return receipt
        cancel_payload = {
            "source": "remote_selected_runtime_paper_proof_v1",
            "operator_approved": True,
            "operator_approval": True,
            "ibkr_paper_order_cancel_ack_13z60": "IBKR_PAPER_ORDER_CANCEL_ACK_13Z60",
            "exact_cancel_only": True,
            "global_cancel_allowed": False,
            "symbol": symbol,
            "expected_symbol": symbol,
            "order_id": identity.get("order_id"),
            "expected_order_id": identity.get("order_id"),
            "order_identity": identity,
            "expected_order": identity,
            "reason": "remote-selected-runtime-paper-proof-exact-cleanup",
        }
        if identity.get("perm_id") is not None:
            cancel_payload["perm_id"] = identity["perm_id"]
            cancel_payload["expected_perm_id"] = identity["perm_id"]
        if identity.get("order_ref"):
            cancel_payload["order_ref"] = identity["order_ref"]
            cancel_payload["expected_order_ref"] = identity["order_ref"]
        preview_status, cancel_preview = send("POST", "/strategy/ibkr-paper-order-cancel-preview", payload=cancel_payload, timeout=60.0)
        cancel_status, cancel = send("POST", "/strategy/ibkr-paper-order-cancel-submit", payload=cancel_payload, timeout=90.0)
        receipt["cleanup"].update({
            "exact_cancel_called": True,
            "exact_cancel_preview_http_status": preview_status,
            "exact_cancel_preview_ok": cancel_preview.get("ok") is True,
            "exact_cancel_http_status": cancel_status,
            "exact_cancel_ok": cancel.get("ok") is True,
            "exact_cancel_status": cancel.get("status"),
        })

    open_status, open_after_cancel = send("GET", "/strategy/ibkr-paper-open-orders", params={"symbol": symbol}, timeout=45.0)
    pos_status, pos_after_cancel = _flatten_snapshot(send, symbol)
    _, target_open_after_cancel = _open_counts(open_after_cancel, symbol)
    target_position_after_cancel = _position_for_symbol(pos_after_cancel, symbol)
    if target_open_after_cancel > 0:
        receipt["status"] = "EXACT_CANCEL_RECONCILIATION_FAILED"
        return receipt

    if abs(target_position_after_cancel) > 1e-12:
        flatten_payload = {
            "symbol": symbol,
            "symbols": [symbol],
            "operator_approved": True,
            "operator_approval": True,
            "ibkr_paper_flatten_ack_13z39": "IBKR_PAPER_FLATTEN_ACK_13Z39",
            "max_symbols": 1,
            "order_type": "AUTO",
            "tif": "DAY",
            "fallback_policy": "none",
            "reason": "remote-selected-runtime-paper-proof-residual-position-cleanup",
        }
        flatten_status, flatten = send("POST", "/strategy/ibkr-paper-flatten-submit-suite", payload=flatten_payload, timeout=120.0)
        receipt["cleanup"].update({
            "flatten_called": True,
            "flatten_http_status": flatten_status,
            "flatten_ok": flatten.get("ok") is True,
            "flatten_status": flatten.get("status"),
        })

    final_open_status, final_open = send("GET", "/strategy/ibkr-paper-open-orders", params={"symbol": symbol}, timeout=45.0)
    final_pos_status, final_pos = _flatten_snapshot(send, symbol)
    global_open_final, target_open_final = _open_counts(final_open, symbol)
    target_position_final = _position_for_symbol(final_pos, symbol)
    final_ok = bool(
        final_open_status == 200
        and final_open.get("ok") is True
        and final_pos_status == 200
        and final_pos.get("ok") is True
        and global_open_final == 0
        and target_open_final == 0
        and abs(target_position_final) <= 1e-12
    )
    receipt["final_reconciliation"] = {
        "open_orders_http_status": final_open_status,
        "positions_http_status": final_pos_status,
        "global_open_order_count": global_open_final,
        "target_open_order_count": target_open_final,
        "target_position": target_position_final,
        "zero_baseline_restored": final_ok,
    }
    receipt["ok"] = final_ok
    receipt["status"] = "PAPER_PROOF_RECONCILED" if final_ok else "PAPER_PROOF_CLEANUP_INCOMPLETE"
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--public-head", required=True)
    args = parser.parse_args()

    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
    request = json.loads(Path(runtime["request_path"]).read_text(encoding="utf-8"))
    receipt = execute_paper_proof(
        runtime=runtime,
        request=request,
        send=_request_sender(args.base_url),
        run_id=args.run_id,
        public_head=args.public_head,
    )
    Path(args.receipt).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("IBKR_REMOTE_SELECTED_RUNTIME_PAPER_PROOF=" + json.dumps({
        "ok": receipt.get("ok"),
        "status": receipt.get("status"),
        "run_id": args.run_id,
        "command_id": (receipt.get("command") or {}).get("command_id"),
        "runtime_id": (receipt.get("command") or {}).get("runtime_id"),
        "symbol": (receipt.get("command") or {}).get("symbol"),
        "submit_called": (receipt.get("submit") or {}).get("called"),
        "broker_order_placed": (receipt.get("submit") or {}).get("broker_order_placed"),
        "exact_cancel_called": (receipt.get("cleanup") or {}).get("exact_cancel_called"),
        "flatten_called": (receipt.get("cleanup") or {}).get("flatten_called"),
        "global_cancel_called": False,
        "live_execution_allowed": False,
    }, sort_keys=True))
    raise SystemExit(0 if receipt.get("ok") else 2)


if __name__ == "__main__":
    main()
