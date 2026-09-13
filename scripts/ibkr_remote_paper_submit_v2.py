from __future__ import annotations

"""Bounded remote IBKR paper-order proof with exact cleanup.

R2 deliberately proves only one paper LMT BUY of quantity 1. It requires a
zero-position/zero-open-order baseline for the symbol, submits through the
existing canonical MM-IBKR route, cancels only the returned broker order ID if
it remains open, and attempts a single-symbol canonical lifecycle flatten only
if the proof created a position. Global cancel and flatten-all are prohibited.
"""

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SUBMIT_PATH = "/strategy/ibkr-paper-order-submit"
OPEN_ORDERS_PATH = "/strategy/ibkr-paper-open-orders"
POSITION_PATH = "/strategy/ibkr-paper-flatten-preview-suite"
CANCEL_PATH = "/strategy/ibkr-paper-cancel-submit"
LIFECYCLE_PATH = "/strategy/bot-owned-position-lifecycle"


def _request(base: str, path: str, *, method: str = "GET", payload: dict | None = None, query: dict | None = None, timeout: float = 90.0) -> tuple[int, dict]:
    url = base.rstrip("/") + path
    if query:
        url += "?" + urlencode(query)
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            status = int(response.getcode())
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    try:
        body = json.loads(raw) if raw.strip() else {}
    except Exception:
        body = {"ok": False, "error": "non_json_response", "http_status": status}
    return status, body if isinstance(body, dict) else {"ok": False, "error": "non_object_response"}


def _num(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def validate_submit_request(request: dict) -> dict:
    if not isinstance(request, dict):
        raise RuntimeError("paper submit request must be an object")
    raw = request.get("canonical_submit_payload")
    if not isinstance(raw, dict) or not raw:
        raise RuntimeError("canonical_submit_payload required")
    payload = dict(raw)
    symbol = str(payload.get("symbol") or "").strip().upper()
    action = str(payload.get("action") or "").strip().upper()
    order_type = str(payload.get("order_type") or payload.get("orderType") or "").strip().upper()
    qty = _num(payload.get("quantity") if payload.get("quantity") is not None else payload.get("totalQuantity"))
    limit_price = _num(payload.get("limit_price") if payload.get("limit_price") is not None else payload.get("lmtPrice"))
    if not symbol or len(symbol) > 20:
        raise RuntimeError("bounded paper proof symbol required")
    if action != "BUY":
        raise RuntimeError("R2 admits BUY only")
    if order_type != "LMT":
        raise RuntimeError("R2 admits LMT only")
    if qty is None or abs(qty - 1.0) > 1e-9:
        raise RuntimeError("R2 requires quantity exactly 1")
    if limit_price is None or limit_price <= 0:
        raise RuntimeError("R2 requires a positive explicit limit price")
    forbidden_true = (
        "allow_market_order",
        "allow_short_sell_13z53",
        "allow_inactive_session",
        "live_allowed",
        "enable_live_trading",
        "ENABLE_LIVE_TRADING",
    )
    for key in forbidden_true:
        value = payload.get(key)
        if value is True or str(value or "").strip().lower() in {"1", "true", "yes", "on", "live"}:
            raise RuntimeError(f"R2 prohibited submit flag: {key}")
    payload["symbol"] = symbol
    payload["action"] = "BUY"
    payload["quantity"] = 1
    payload["order_type"] = "LMT"
    payload["limit_price"] = float(limit_price)
    payload["operator_approved"] = True
    payload["ibkr_paper_order_submit_ack_13z53"] = "IBKR_PAPER_ORDER_SUBMIT_ACK_13Z53"
    payload["allow_market_order"] = False
    payload["allow_short_sell_13z53"] = False
    payload["allow_inactive_session"] = False
    payload["broker_diagnostic_polls"] = max(2, min(int(payload.get("broker_diagnostic_polls") or 8), 12))
    payload["broker_diagnostic_poll_sleep_sec"] = max(0.25, min(float(payload.get("broker_diagnostic_poll_sleep_sec") or 0.5), 2.0))
    return payload


def _position_rows(body: dict) -> list[dict]:
    rows = body.get("flatten_candidates")
    return rows if isinstance(rows, list) else []


def position_for_symbol(body: dict, symbol: str) -> float:
    if body.get("position_read_error"):
        raise RuntimeError("broker position snapshot contains position_read_error")
    total = 0.0
    for row in _position_rows(body):
        if str(row.get("symbol") or "").strip().upper() == symbol:
            value = _num(row.get("position"))
            if value is None:
                raise RuntimeError("matched position row has non-numeric position")
            total += value
    return total


def exact_order_identity(submit: dict, symbol: str) -> dict:
    broker_submit = submit.get("broker_submit") if isinstance(submit.get("broker_submit"), dict) else {}
    order = broker_submit.get("order") if isinstance(broker_submit.get("order"), dict) else {}
    candidates: list[dict] = []
    if order:
        candidates.append(order)
    for node in submit.get("open_trades_after_for_ref") or []:
        if not isinstance(node, dict):
            continue
        row = node.get("order") if isinstance(node.get("order"), dict) else {}
        if row:
            candidates.append(row)
    ids = {int(float(row["orderId"])) for row in candidates if row.get("orderId") is not None}
    refs = {str(row.get("orderRef") or "") for row in candidates if str(row.get("orderRef") or "")}
    if len(ids) != 1:
        raise RuntimeError("canonical submit did not yield one exact broker orderId")
    order_id = next(iter(ids))
    order_ref = str(order.get("orderRef") or "")
    if not order_ref and len(refs) == 1:
        order_ref = next(iter(refs))
    return {
        "order_id": order_id,
        "perm_id": order.get("permId"),
        "order_ref": order_ref,
        "symbol": symbol,
    }


def _open_order_match(body: dict, order_id: int) -> dict | None:
    for row in body.get("orders") or []:
        if not isinstance(row, dict):
            continue
        try:
            candidate = int(float(row.get("orderId")))
        except Exception:
            continue
        if candidate == int(order_id):
            return row
    return None


def _sanitized_submit(submit: dict) -> dict:
    broker = submit.get("broker_submit") if isinstance(submit.get("broker_submit"), dict) else {}
    order = broker.get("order") if isinstance(broker.get("order"), dict) else {}
    status = broker.get("order_status") if isinstance(broker.get("order_status"), dict) else {}
    return {
        "ok": submit.get("ok") is True,
        "status": submit.get("status"),
        "place_order_called": submit.get("place_order_called") is True,
        "broker_order_placed": submit.get("broker_order_placed") is True,
        "order": {
            "orderId": order.get("orderId"),
            "permId": order.get("permId"),
            "clientId": order.get("clientId"),
            "action": order.get("action"),
            "orderType": order.get("orderType"),
            "totalQuantity": order.get("totalQuantity"),
            "lmtPrice": order.get("lmtPrice"),
            "tif": order.get("tif"),
            "orderRef": order.get("orderRef"),
        },
        "order_status": {
            "status": status.get("status"),
            "filled": status.get("filled"),
            "remaining": status.get("remaining"),
            "avgFillPrice": status.get("avgFillPrice"),
        },
        "post_submit": submit.get("post_submit") if isinstance(submit.get("post_submit"), dict) else {},
    }


def execute(base: str, runtime: dict, request: dict, *, run_id: str, job: str, public_head: str) -> dict:
    if runtime.get("mode") != "paper_submit_proof" or runtime.get("read_only_api") != "no":
        raise RuntimeError("R2 requires paper_submit_proof with READ_ONLY_API=no")
    if runtime.get("paper_only") is not True or runtime.get("live_trading_change") is not False:
        raise RuntimeError("R2 runtime authority mismatch")
    cleanup = runtime.get("cleanup") if isinstance(runtime.get("cleanup"), dict) else {}
    if cleanup != {
        "cancel_open_order": True,
        "flatten_filled_position": True,
        "require_zero_baseline": True,
        "allow_global_cancel": False,
    }:
        raise RuntimeError("R2 cleanup contract mismatch")

    submit_payload = validate_submit_request(request)
    symbol = submit_payload["symbol"]
    order_ref = f"MMIBKR_GH_R2_{run_id}_{symbol}"
    submit_payload["order_ref"] = order_ref

    open_status, open_body = _request(base, OPEN_ORDERS_PATH, query={"symbol": symbol}, timeout=45)
    pos_status, pos_body = _request(base, POSITION_PATH, method="POST", payload={"candidate_limit": 50, "preview_limit": 1, "batch_limit": 1}, timeout=60)
    baseline_position = position_for_symbol(pos_body, symbol) if pos_status == 200 and pos_body.get("ok") is True else None
    matched_open = int(open_body.get("matched_count") or 0) if open_status == 200 and open_body.get("ok") is True else None
    baseline_ok = baseline_position is not None and abs(baseline_position) <= 1e-12 and matched_open == 0

    receipt = {
        "schema": "mm-ibkr-remote-paper-submit-receipt-v2",
        "ok": False,
        "status": "BASELINE_BLOCKED",
        "github": {"run_id": str(run_id), "job": str(job), "public_head": str(public_head)},
        "mmibkr": {
            "repository": runtime.get("mmibkr_repository"),
            "head": runtime.get("mmibkr_head"),
            "source_archive_sha256": runtime.get("source_archive_sha256"),
        },
        "paper_only": True,
        "live_trading_change": False,
        "host_dependency": False,
        "symbol": symbol,
        "baseline": {
            "position": baseline_position,
            "matched_open_order_count": matched_open,
            "zero_baseline": baseline_ok,
        },
        "submit": None,
        "cleanup": {
            "exact_order_cancel_attempted": False,
            "exact_order_cancel_reconciled": False,
            "flatten_symbol_attempted": False,
            "flatten_symbol_reported_ok": False,
            "global_cancel_called": False,
            "flatten_all_called": False,
        },
        "final": {"position": None, "matched_open_order_count": None, "baseline_restored": False},
        "secrets_published": False,
    }
    if not baseline_ok:
        return receipt

    submit_status, submit_body = _request(base, SUBMIT_PATH, method="POST", payload=submit_payload, timeout=180)
    receipt["submit"] = _sanitized_submit(submit_body)
    if submit_status != 200 or submit_body.get("ok") is not True or submit_body.get("broker_order_placed") is not True:
        receipt["status"] = "SUBMIT_NOT_ACCEPTED"
        return receipt

    identity = exact_order_identity(submit_body, symbol)
    receipt["submit"]["exact_order_identity"] = identity

    open_status, open_body = _request(base, OPEN_ORDERS_PATH, query={"symbol": symbol, "order_id": identity["order_id"]}, timeout=45)
    row = _open_order_match(open_body, identity["order_id"]) if open_status == 200 else None
    unresolved = bool(row and row.get("unresolved"))
    if unresolved:
        cancel_payload = {
            "order_id": identity["order_id"],
            "symbol": symbol,
            "require_symbol_match": True,
            "operator_approved": True,
            "ibkr_paper_cancel_ack_13z37": "IBKR_PAPER_CANCEL_ACK_13Z37",
        }
        if identity.get("perm_id") is not None:
            cancel_payload["perm_id"] = identity["perm_id"]
        receipt["cleanup"]["exact_order_cancel_attempted"] = True
        cancel_status, cancel_body = _request(base, CANCEL_PATH, method="POST", payload=cancel_payload, timeout=120)
        receipt["cleanup"]["exact_order_cancel_reconciled"] = bool(
            cancel_status == 200
            and cancel_body.get("ok") is True
            and int(cancel_body.get("post_cancel_remaining_matched_count") or 0) == 0
        )

    pos_status, pos_body = _request(base, POSITION_PATH, method="POST", payload={"candidate_limit": 50, "preview_limit": 1, "batch_limit": 1}, timeout=60)
    current_position = position_for_symbol(pos_body, symbol) if pos_status == 200 and pos_body.get("ok") is True else None
    if current_position is not None and abs(current_position) > 1e-12:
        receipt["cleanup"]["flatten_symbol_attempted"] = True
        lifecycle_payload = {
            "mode": "flatten_symbol",
            "symbol": symbol,
            "qty": abs(current_position),
            "submit": True,
            "paper_only": True,
            "live_allowed": False,
            "bot_owned_lifecycle_submit_ack_13z": "BOT_OWNED_LIFECYCLE_SUBMIT_ACK_13Z",
        }
        lifecycle_status, lifecycle_body = _request(base, LIFECYCLE_PATH, method="POST", payload=lifecycle_payload, timeout=240)
        receipt["cleanup"]["flatten_symbol_reported_ok"] = bool(lifecycle_status == 200 and lifecycle_body.get("ok") is True)

    deadline = time.time() + 45
    final_position = None
    final_open = None
    while time.time() < deadline:
        open_status, open_body = _request(base, OPEN_ORDERS_PATH, query={"symbol": symbol, "order_id": identity["order_id"]}, timeout=30)
        pos_status, pos_body = _request(base, POSITION_PATH, method="POST", payload={"candidate_limit": 50, "preview_limit": 1, "batch_limit": 1}, timeout=45)
        if open_status == 200 and open_body.get("ok") is True:
            final_open = int(open_body.get("matched_count") or 0)
        if pos_status == 200 and pos_body.get("ok") is True:
            final_position = position_for_symbol(pos_body, symbol)
        if final_open == 0 and final_position is not None and abs(final_position) <= 1e-12:
            break
        time.sleep(2)

    restored = final_open == 0 and final_position is not None and abs(final_position) <= 1e-12
    receipt["final"] = {
        "position": final_position,
        "matched_open_order_count": final_open,
        "baseline_restored": restored,
    }
    receipt["ok"] = restored
    receipt["status"] = "PAPER_SUBMIT_AND_CLEANUP_PROVEN" if restored else "PAPER_SUBMIT_RESIDUAL_REQUIRES_ATTENTION"
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--public-head", required=True)
    args = parser.parse_args()
    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    receipt = execute(args.base_url, runtime, request, run_id=args.run_id, job=args.job, public_head=args.public_head)
    Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("IBKR_REMOTE_PAPER_SUBMIT=" + json.dumps(receipt, sort_keys=True))
    if not receipt.get("ok"):
        raise SystemExit(47)


if __name__ == "__main__":
    main()
