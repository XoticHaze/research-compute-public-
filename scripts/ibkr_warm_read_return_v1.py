from __future__ import annotations

"""Collect detailed read-only IBKR truth and encrypt it to a private one-run recipient.

This helper runs only after the accepted warm Gateway session is authenticated. It
never submits, cancels, or modifies an order. Detailed account state, positions,
open trades, and canonical forward bars are emitted only as X25519/ChaCha20-Poly1305
ciphertext bound to the GitHub run and recipient fingerprint.
"""

import argparse
import base64
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from ib_insync import IB

SNAPSHOT_SCHEMA = "mmibkr.ibkr_warm_read_snapshot.v1"
RETURN_RECIPIENT_SCHEMA = "ibkr-remote-paper-return-recipient-v1"
RETURN_ENVELOPE_SCHEMA = "ibkr-warm-read-return-x25519-v1"
AUTHORITY = "mm_ibkr_paper_runtime"
HARNESS = "mm_ibkr_warm_read_gateway_v1"
RETURN_INFO = b"mm-ibkr-warm-read-return-v1"
CHUNK_CHARS = 8000


def _contract(contract: Any) -> dict[str, Any]:
    return {
        "conId": int(getattr(contract, "conId", 0) or 0),
        "symbol": str(getattr(contract, "symbol", "") or ""),
        "secType": str(getattr(contract, "secType", "") or ""),
        "exchange": str(getattr(contract, "exchange", "") or ""),
        "primaryExchange": str(getattr(contract, "primaryExchange", "") or ""),
        "currency": str(getattr(contract, "currency", "") or ""),
        "localSymbol": str(getattr(contract, "localSymbol", "") or ""),
        "tradingClass": str(getattr(contract, "tradingClass", "") or ""),
        "lastTradeDateOrContractMonth": str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
    }


def _execution_fill(fill: Any) -> dict[str, Any]:
    execution = getattr(fill, "execution", None)
    report = getattr(fill, "commissionReport", None)
    when = getattr(execution, "time", None)
    if isinstance(when, datetime):
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        else:
            when = when.astimezone(timezone.utc)
        when_text = when.isoformat().replace("+00:00", "Z")
    else:
        when_text = str(when or "")
    return {
        "contract": _contract(getattr(fill, "contract", None)),
        "execution": {
            "execId": str(getattr(execution, "execId", "") or ""),
            "time": when_text,
            "acctNumber": str(getattr(execution, "acctNumber", "") or ""),
            "exchange": str(getattr(execution, "exchange", "") or ""),
            "side": str(getattr(execution, "side", "") or ""),
            "shares": float(getattr(execution, "shares", 0.0) or 0.0),
            "price": float(getattr(execution, "price", 0.0) or 0.0),
            "permId": int(getattr(execution, "permId", 0) or 0),
            "clientId": int(getattr(execution, "clientId", 0) or 0),
            "orderId": int(getattr(execution, "orderId", 0) or 0),
            "cumQty": float(getattr(execution, "cumQty", 0.0) or 0.0),
            "avgPrice": float(getattr(execution, "avgPrice", 0.0) or 0.0),
            "orderRef": str(getattr(execution, "orderRef", "") or ""),
        },
        "commission_report": {
            "execId": str(getattr(report, "execId", "") or ""),
            "commission": float(getattr(report, "commission", 0.0) or 0.0),
            "currency": str(getattr(report, "currency", "") or ""),
            "realizedPNL": float(getattr(report, "realizedPNL", 0.0) or 0.0),
        },
    }


def _contract_identity(contract: Mapping[str, Any]) -> tuple[str, str]:
    try:
        con_id = int(contract.get("conId") or 0)
    except Exception:
        con_id = 0
    if con_id > 0:
        return ("conId", str(con_id))
    local = str(contract.get("localSymbol") or "").strip().upper()
    if local:
        return ("localSymbol", local)
    symbol = str(contract.get("symbol") or "").strip().upper()
    sec_type = str(contract.get("secType") or "").strip().upper()
    return ("symbol_secType", symbol + "|" + sec_type)


def _filter_requested_fills(
    fills: list[dict[str, Any]],
    *,
    handoff: Mapping[str, Any],
    managed_accounts: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    requested_contracts: set[tuple[str, str]] = set()
    for node in handoff.get("symbols") or []:
        if not isinstance(node, Mapping):
            continue
        resolved = node.get("resolved_contract") if isinstance(node.get("resolved_contract"), Mapping) else {}
        requested_contracts.add(_contract_identity(resolved))
    requested_contracts.discard(("symbol_secType", "|"))
    if not requested_contracts:
        raise RuntimeError("warm read completed-execution requested contracts missing")

    allowed_accounts = {str(item).strip().upper() for item in managed_accounts if str(item).strip()}
    out: list[dict[str, Any]] = []
    execution_ids: list[str] = []
    for row in fills:
        if not isinstance(row, Mapping):
            continue
        contract = row.get("contract") if isinstance(row.get("contract"), Mapping) else {}
        if _contract_identity(contract) not in requested_contracts:
            continue
        execution = row.get("execution") if isinstance(row.get("execution"), Mapping) else {}
        account = str(execution.get("acctNumber") or "").strip().upper()
        if account and account not in allowed_accounts:
            raise RuntimeError("warm read completed execution account escaped managed DU accounts")
        out.append(dict(row))
        exec_id = str(execution.get("execId") or "").strip()
        if exec_id:
            execution_ids.append(exec_id)
    return out, sorted(set(execution_ids))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        node = json.loads(raw)
        if not isinstance(node, dict):
            raise RuntimeError("canonical forward-bar row must be an object")
        rows.append(node)
    return rows


def collect_snapshot(
    *,
    host: str,
    port: int,
    client_id: int,
    run_id: str,
    public_head: str,
    handoff_file: Path,
    bars_file: Path,
) -> dict[str, Any]:
    ib = IB()
    try:
        ib.connect(host, int(port), clientId=int(client_id), timeout=10, readonly=True)
        if not ib.isConnected():
            raise RuntimeError("IBKR read snapshot connection did not become ready")

        managed_accounts = [str(a) for a in ib.managedAccounts()]
        if not managed_accounts or any(not str(a).upper().startswith("DU") for a in managed_accounts):
            raise RuntimeError("read snapshot is not bound exclusively to DU paper accounts")

        account_summary = []
        for node in ib.accountSummary():
            account_summary.append({
                "account": str(getattr(node, "account", "") or ""),
                "tag": str(getattr(node, "tag", "") or ""),
                "value": str(getattr(node, "value", "") or ""),
                "currency": str(getattr(node, "currency", "") or ""),
                "model_code": str(getattr(node, "modelCode", "") or ""),
            })

        positions = []
        for node in ib.positions():
            positions.append({
                "account": str(getattr(node, "account", "") or ""),
                "contract": _contract(getattr(node, "contract", None)),
                "position": float(getattr(node, "position", 0.0) or 0.0),
                "avg_cost": float(getattr(node, "avgCost", 0.0) or 0.0),
            })

        ib.reqAllOpenOrders()
        ib.sleep(1)
        open_trades = []
        for trade in ib.openTrades():
            order = getattr(trade, "order", None)
            status = getattr(trade, "orderStatus", None)
            open_trades.append({
                "contract": _contract(getattr(trade, "contract", None)),
                "order": {
                    "order_id": int(getattr(order, "orderId", 0) or 0),
                    "perm_id": int(getattr(order, "permId", 0) or 0),
                    "client_id": int(getattr(order, "clientId", 0) or 0),
                    "action": str(getattr(order, "action", "") or ""),
                    "total_quantity": float(getattr(order, "totalQuantity", 0.0) or 0.0),
                    "order_type": str(getattr(order, "orderType", "") or ""),
                    "limit_price": float(getattr(order, "lmtPrice", 0.0) or 0.0),
                    "aux_price": float(getattr(order, "auxPrice", 0.0) or 0.0),
                    "tif": str(getattr(order, "tif", "") or ""),
                    "account": str(getattr(order, "account", "") or ""),
                    "order_ref": str(getattr(order, "orderRef", "") or ""),
                },
                "status": {
                    "status": str(getattr(status, "status", "") or ""),
                    "filled": float(getattr(status, "filled", 0.0) or 0.0),
                    "remaining": float(getattr(status, "remaining", 0.0) or 0.0),
                    "avg_fill_price": float(getattr(status, "avgFillPrice", 0.0) or 0.0),
                },
            })

        completed_execution_started = datetime.now(timezone.utc)
        completed_execution_fills_all = [
            _execution_fill(fill)
            for fill in list(ib.reqExecutions() or [])
        ]
        completed_execution_finished = datetime.now(timezone.utc)

        handoff = json.loads(handoff_file.read_text(encoding="utf-8")) if handoff_file.is_file() else {}
        bars = _load_jsonl(bars_file)
        if not isinstance(handoff, Mapping) or handoff.get("schema") != "mmibkr-ibkr-post-auth-handoff-v2":
            raise RuntimeError("warm read post-auth handoff schema mismatch")
        if handoff.get("trading_mode") != "paper" or handoff.get("read_only") is not True:
            raise RuntimeError("warm read post-auth paper/read-only boundary violated")
        if handoff.get("paper_account_verified") is not True or handoff.get("consumer_ready") is not True:
            raise RuntimeError("warm read post-auth consumer is not ready")

        requested_symbols = [
            str(node.get("symbol") or "").strip().upper()
            for node in (handoff.get("symbols") or [])
            if isinstance(node, Mapping) and str(node.get("symbol") or "").strip()
        ]
        requested_symbols = list(dict.fromkeys(requested_symbols))
        if not requested_symbols:
            raise RuntimeError("warm read requested symbol coverage missing")
        forward_bar_symbols = sorted({
            str(node.get("symbol") or "").strip().upper()
            for node in bars
            if str(node.get("symbol") or "").strip()
        })
        if set(forward_bar_symbols) != set(requested_symbols):
            raise RuntimeError("warm read forward-bar symbol coverage mismatch")
        handoff_bar_symbols = sorted(str(item).strip().upper() for item in (handoff.get("forward_bar_symbols") or []) if str(item).strip())
        if set(handoff_bar_symbols) != set(requested_symbols):
            raise RuntimeError("warm read post-auth forward-bar coverage mismatch")
        handoff_caps = handoff.get("capabilities") if isinstance(handoff.get("capabilities"), Mapping) else {}
        for required in ("account_state", "positions", "open_orders", "historical_market_data", "canonical_forward_bar_materialization"):
            if handoff_caps.get(required) is not True:
                raise RuntimeError(f"warm read post-auth capability missing: {required}")
        if not account_summary:
            raise RuntimeError("warm read account summary is empty")

        completed_fills, execution_ids = _filter_requested_fills(
            completed_execution_fills_all,
            handoff=handoff,
            managed_accounts=managed_accounts,
        )
        execution_elapsed_ms = round(
            (completed_execution_finished - completed_execution_started).total_seconds() * 1000.0,
            3,
        )

        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run_id),
            "public_head": str(public_head),
            "authority": AUTHORITY,
            "harness": HARNESS,
            "trading_mode": "paper",
            "read_only": True,
            "managed_accounts": managed_accounts,
            "account_summary": account_summary,
            "positions": positions,
            "open_trades": open_trades,
            "fills": completed_fills,
            "completed_execution_evidence": {
                "requested": True,
                "req_executions_called": True,
                "source": "ibkr.reqExecutions",
                "returned_fill_count": len(completed_execution_fills_all),
                "requested_contract_fill_count": len(completed_fills),
                "execution_ids": execution_ids,
                "request_elapsed_ms": execution_elapsed_ms,
                "complete_history_claimed": False,
                "broker_mutation_called": False,
                "global_cancel_called": False,
                "live_execution_allowed": False,
            },
            "broker_time": ib.reqCurrentTime().isoformat(),
            "post_auth_handoff": handoff,
            "requested_symbols": requested_symbols,
            "forward_bar_symbols": forward_bar_symbols,
            "forward_bars": bars,
            "capabilities": {
                "account_state": True,
                "positions": True,
                "open_orders": True,
                "historical_market_data": True,
                "completed_executions": True,
                "order_submission": False,
                "global_cancel": False,
                "live_execution": False,
            },
        }
        return snapshot
    finally:
        if ib.isConnected():
            ib.disconnect()


def _json_transport_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_transport_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_transport_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_transport_safe(item) for item in value]
    return value


def _aad(*, run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": RETURN_ENVELOPE_SCHEMA,
            "run_id": str(run_id),
            "authority": AUTHORITY,
            "harness": HARNESS,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def encrypt_snapshot(
    *,
    snapshot: Mapping[str, Any],
    recipient_b64: str,
    recipient_key_id: str,
    run_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    if snapshot.get("schema") != SNAPSHOT_SCHEMA or str(snapshot.get("run_id")) != str(run_id):
        raise RuntimeError("warm read snapshot identity mismatch")
    if snapshot.get("authority") != AUTHORITY or snapshot.get("harness") != HARNESS:
        raise RuntimeError("warm read snapshot authority mismatch")
    if snapshot.get("trading_mode") != "paper" or snapshot.get("read_only") is not True:
        raise RuntimeError("warm read snapshot paper/read-only boundary violated")
    accounts = [str(item) for item in (snapshot.get("managed_accounts") or [])]
    if not accounts or any(not item.upper().startswith("DU") for item in accounts):
        raise RuntimeError("warm read snapshot DU paper-account boundary violated")
    capabilities = snapshot.get("capabilities") if isinstance(snapshot.get("capabilities"), Mapping) else {}
    for required in ("account_state", "positions", "open_orders", "historical_market_data", "completed_executions"):
        if capabilities.get(required) is not True:
            raise RuntimeError(f"warm read snapshot required capability missing: {required}")
    if capabilities.get("order_submission") is not False or capabilities.get("global_cancel") is not False or capabilities.get("live_execution") is not False:
        raise RuntimeError("warm read snapshot mutation boundary violated")
    execution_evidence = snapshot.get("completed_execution_evidence") if isinstance(snapshot.get("completed_execution_evidence"), Mapping) else {}
    if (
        execution_evidence.get("requested") is not True
        or execution_evidence.get("req_executions_called") is not True
        or execution_evidence.get("source") != "ibkr.reqExecutions"
        or execution_evidence.get("complete_history_claimed") is not False
        or execution_evidence.get("broker_mutation_called") is not False
        or execution_evidence.get("global_cancel_called") is not False
        or execution_evidence.get("live_execution_allowed") is not False
    ):
        raise RuntimeError("warm read completed execution evidence boundary violated")
    requested_symbols = {str(item).strip().upper() for item in (snapshot.get("requested_symbols") or []) if str(item).strip()}
    forward_bar_symbols = {str(item).strip().upper() for item in (snapshot.get("forward_bar_symbols") or []) if str(item).strip()}
    if not requested_symbols or requested_symbols != forward_bar_symbols:
        raise RuntimeError("warm read snapshot forward-bar coverage mismatch")
    try:
        raw_recipient = base64.b64decode(str(recipient_b64).encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("warm read recipient key encoding invalid") from exc
    if len(raw_recipient) != 32:
        raise RuntimeError("warm read recipient key length invalid")
    computed_key_id = "sha256:" + hashlib.sha256(raw_recipient).hexdigest()
    if computed_key_id != str(recipient_key_id):
        raise RuntimeError("warm read recipient fingerprint mismatch")

    transport_snapshot = _json_transport_safe(dict(snapshot))
    plaintext = json.dumps(transport_snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    aad = _aad(run_id=run_id, recipient_key_id=computed_key_id)
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(raw_recipient))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(aad).digest(), info=RETURN_INFO).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    payload_b64 = base64.b64encode(ciphertext).decode("ascii")

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(output_dir, 0o700)
    except OSError:
        pass
    manifest: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(payload_b64), CHUNK_CHARS)):
        text = payload_b64[start:start + CHUNK_CHARS]
        local_name = f"ibkr-warm-read-{index:03d}.txt"
        path = output_dir / local_name
        path.write_text(text, encoding="ascii")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        manifest.append({
            "path": f"rendezvous/returns/{run_id}/{local_name}",
            "local_name": local_name,
            "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
            "chars": len(text),
        })

    envelope = {
        "schema": RETURN_ENVELOPE_SCHEMA,
        "run_id": str(run_id),
        "authority": AUTHORITY,
        "harness": HARNESS,
        "recipient_key_id": computed_key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "chunks": manifest,
    }
    envelope_path = output_dir / "ibkr-warm-read-envelope.json"
    envelope_path.write_text(json.dumps(envelope, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(envelope_path, 0o600)
    except OSError:
        pass
    return envelope


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--client-id", type=int, default=79)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--public-head", required=True)
    parser.add_argument("--handoff-file", required=True)
    parser.add_argument("--bars-file", required=True)
    parser.add_argument("--recipient-b64", required=True)
    parser.add_argument("--recipient-key-id", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    snapshot = collect_snapshot(
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        run_id=args.run_id,
        public_head=args.public_head,
        handoff_file=Path(args.handoff_file),
        bars_file=Path(args.bars_file),
    )
    envelope = encrypt_snapshot(
        snapshot=snapshot,
        recipient_b64=args.recipient_b64,
        recipient_key_id=args.recipient_key_id,
        run_id=args.run_id,
        output_dir=Path(args.output_dir),
    )
    print("IBKR_WARM_READ_RETURN_READY=" + json.dumps({
        "run_id": str(args.run_id),
        "account_summary_fields": len(snapshot["account_summary"]),
        "positions": len(snapshot["positions"]),
        "open_trades": len(snapshot["open_trades"]),
        "completed_fills": len(snapshot["fills"]),
        "forward_bars": len(snapshot["forward_bars"]),
        "ciphertext_sha256": envelope["ciphertext_sha256"],
        "plaintext_published": False,
        "broker_action": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
