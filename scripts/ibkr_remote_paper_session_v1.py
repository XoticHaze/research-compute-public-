from __future__ import annotations

"""Read-only paper-session reconciliation driver for remote MM-IBKR.

The public receipt stays sanitized. When the encrypted request includes a one-run
return recipient, detailed account truth is normalized from canonical MM-IBKR
status/open-order surfaces and encrypted directly to that private recipient. The
plaintext detailed snapshot is never written as a public artifact or printed.
"""

import argparse
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

RETURN_RECIPIENT_SCHEMA = "ibkr-remote-paper-return-recipient-v1"
RETURN_ENVELOPE_SCHEMA = "ibkr-remote-paper-return-x25519-v1"
ACCOUNT_SNAPSHOT_SCHEMA = "mm_ibkr.portfolio_account_snapshot_r2"
AUTHORITY = "mm_ibkr_paper_runtime"
HARNESS = "mm_ibkr_remote_paper_runtime_v1"
RETURN_INFO = b"mm-ibkr-paper-account-return-v1"
RETURN_CHUNK_CHARS = 8000


def _json_request(url: str, *, method: str = "GET", payload: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            status = int(response.getcode())
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body) if body.strip() else {}
    except Exception:
        parsed = {"ok": False, "error": "non_json_response"}
    return status, parsed if isinstance(parsed, dict) else {"ok": False, "raw_type": type(parsed).__name__}


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_receipt(*, run_id: str, job: str, public_head: str, runtime: dict, health: tuple[int, dict], open_orders: tuple[int, dict], positions: tuple[int, dict]) -> dict:
    health_status, health_body = health
    open_status, open_body = open_orders
    pos_status, pos_body = positions
    account_identity = open_body.get("account_identity") if isinstance(open_body.get("account_identity"), dict) else {}

    paper_account_ok = bool(account_identity.get("selected_account_is_paper_du")) and int(account_identity.get("du_account_count") or 0) == 1
    broker_reads_ok = bool(open_status == 200 and open_body.get("ok") is True and pos_status == 200 and pos_body.get("ok") is True)
    session_ready = bool(health_status == 200 and broker_reads_ok and paper_account_ok)

    return {
        "schema": "mm-ibkr-remote-paper-session-receipt-v2",
        "ok": session_ready,
        "status": "REMOTE_PAPER_SESSION_RECONCILED" if session_ready else "REMOTE_PAPER_SESSION_NOT_READY",
        "github": {"run_id": str(run_id), "job": str(job), "public_head": str(public_head)},
        "mmibkr": {
            "repository": runtime.get("mmibkr_repository"),
            "head": runtime.get("mmibkr_head"),
            "source_archive_sha256": runtime.get("source_archive_sha256"),
        },
        "mode": runtime.get("mode"),
        "paper_only": runtime.get("paper_only") is True,
        "read_only_api": runtime.get("read_only_api") == "yes",
        "host_dependency": runtime.get("host_dependency") is True,
        "live_trading_change": runtime.get("live_trading_change") is True,
        "encrypted_account_return_requested": runtime.get("encrypted_return_requested") is True,
        "broker_session": {
            "health_http_status": health_status,
            "health_ok": health_body.get("ok") is not False,
            "open_orders_http_status": open_status,
            "open_orders_ok": open_body.get("ok") is True,
            "positions_http_status": pos_status,
            "positions_ok": pos_body.get("ok") is True,
            "managed_account_count": int(account_identity.get("managed_account_count") or 0),
            "du_account_count": int(account_identity.get("du_account_count") or 0),
            "single_paper_du_account": paper_account_ok,
            "open_order_count": int(open_body.get("open_order_count") or 0),
            "unresolved_open_order_count": int(open_body.get("unresolved_open_order_count") or 0),
            "position_count": int(pos_body.get("position_count") or 0),
        },
        "side_effects": {
            "submit_called": False,
            "cancel_called": False,
            "flatten_called": False,
            "broker_order_placed": False,
        },
        "detailed_account_plaintext_published": False,
        "secrets_published": False,
    }


def load_ready_status(path: Path, *, timeout_sec: float = 45.0) -> dict:
    deadline = time.time() + max(0.1, timeout_sec)
    last_error = "status_not_seen"
    while time.time() < deadline:
        try:
            node = json.loads(path.read_text(encoding="utf-8"))
            account = node.get("account") if isinstance(node.get("account"), dict) else {}
            if _num(account.get("NetLiquidation")) not in (None, 0.0) and isinstance(node.get("positions"), list) and node.get("ts"):
                return node
            last_error = "status_missing_account_or_positions"
        except Exception as exc:
            last_error = type(exc).__name__
        time.sleep(1)
    raise RuntimeError("canonical MM-IBKR status did not become account-ready: " + last_error)


def build_account_snapshot(*, run_id: str, runtime: dict, status: dict, open_orders_body: dict) -> dict:
    account = status.get("account") if isinstance(status.get("account"), dict) else {}
    nav = _num(account.get("NetLiquidation"))
    cash = None
    cash_tag = None
    for tag in ("TotalCashValue", "SettledCash", "CashBalance"):
        value = _num(account.get(tag))
        if value is not None:
            cash = value
            cash_tag = tag
            break
    if nav is None or nav <= 0:
        raise RuntimeError("canonical account snapshot lacks positive NetLiquidation")
    if cash is None:
        raise RuntimeError("canonical account snapshot lacks cash value")

    identity = open_orders_body.get("account_identity") if isinstance(open_orders_body.get("account_identity"), dict) else {}
    if not bool(identity.get("selected_account_is_paper_du")) or int(identity.get("du_account_count") or 0) != 1:
        raise RuntimeError("open-order surface does not prove exactly one DU paper account")
    order_rows = open_orders_body.get("orders") if isinstance(open_orders_body.get("orders"), list) else []
    if int(open_orders_body.get("open_order_count") or 0) != len(order_rows):
        raise RuntimeError("open-order count/rows mismatch")

    positions = []
    for row in status.get("positions") or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        quantity = _num(row.get("position"))
        if not symbol or quantity is None or abs(quantity) <= 1e-12:
            continue
        positions.append({
            "symbol": symbol,
            "quantity": quantity,
            "market_price": _num(row.get("marketPrice")),
            "market_value": _num(row.get("marketValue")),
            "avg_cost": _num(row.get("avgCost")),
            "con_id": row.get("conId"),
            "sec_type": row.get("secType"),
            "currency": row.get("currency"),
            "exchange": row.get("exchange"),
        })

    orders = []
    for row in order_rows:
        if not isinstance(row, dict) or row.get("unresolved") is False:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        orders.append({
            "symbol": symbol,
            "status": row.get("status") or row.get("orderStatus") or "OPEN",
            "action": row.get("action"),
            "order_id": row.get("orderId"),
            "perm_id": row.get("permId"),
            "order_ref": row.get("orderRef"),
            "unresolved": row.get("unresolved", True),
        })

    return {
        "schema": ACCOUNT_SNAPSHOT_SCHEMA,
        "observed_at": status.get("ts"),
        "observation_ref": f"public-run:{run_id}:session_reconcile",
        "account_id": identity.get("selected_account_redacted") or "DU_PAPER_REDACTED",
        "account_mode": "paper",
        "paper_session_ready": True,
        "open_orders_complete": True,
        "net_liquidation": nav,
        "cash": cash,
        "cash_source_tag": cash_tag,
        "positions": positions,
        "open_orders": orders,
        "source": {
            "public_run_id": str(run_id),
            "mmibkr_head": runtime.get("mmibkr_head"),
            "source_archive_sha256": runtime.get("source_archive_sha256"),
            "status_source": status.get("status_source"),
            "status_ts": status.get("ts"),
            "open_order_contract_version": open_orders_body.get("contract_version"),
        },
        "boundaries": {
            "read_only": True,
            "broker_action": False,
            "paper_submit": False,
            "live_submit": False,
        },
    }


def _return_aad(*, run_id: str, recipient_key_id: str) -> bytes:
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


def encrypt_account_snapshot(*, run_id: str, snapshot: dict, recipient: dict, output_dir: Path) -> dict:
    if recipient.get("schema") != RETURN_RECIPIENT_SCHEMA:
        raise RuntimeError("encrypted return recipient schema mismatch")
    raw_recipient = base64.b64decode(str(recipient.get("recipient_b64") or "").encode("ascii"), validate=True)
    if len(raw_recipient) != 32:
        raise RuntimeError("encrypted return recipient key length invalid")
    recipient_key_id = "sha256:" + hashlib.sha256(raw_recipient).hexdigest()
    if recipient_key_id != recipient.get("recipient_key_id"):
        raise RuntimeError("encrypted return recipient fingerprint mismatch")

    plaintext = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    aad = _return_aad(run_id=run_id, recipient_key_id=recipient_key_id)
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(raw_recipient))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(aad).digest(), info=RETURN_INFO).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    payload_b64 = base64.b64encode(ciphertext).decode("ascii")

    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    manifest = []
    for index, start in enumerate(range(0, len(payload_b64), RETURN_CHUNK_CHARS)):
        text = payload_b64[start:start + RETURN_CHUNK_CHARS]
        local_name = f"ibkr-paper-account-{index:03d}.txt"
        path = output_dir / local_name
        path.write_text(text, encoding="ascii")
        os.chmod(path, 0o600)
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
        "recipient_key_id": recipient_key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "chunks": manifest,
    }
    envelope_path = output_dir / "ibkr-paper-account-envelope.json"
    envelope_path.write_text(json.dumps(envelope, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(envelope_path, 0o600)
    return envelope


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--public-head", required=True)
    parser.add_argument("--status-json")
    parser.add_argument("--encrypted-return-dir")
    args = parser.parse_args()

    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
    if runtime.get("mode") != "session_reconcile" or runtime.get("read_only_api") != "yes":
        raise SystemExit("session driver admits only session_reconcile with READ_ONLY_API=yes")

    base = args.base_url.rstrip("/")
    health = _json_request(base + "/healthz", timeout=15)
    open_orders = _json_request(base + "/strategy/ibkr-paper-open-orders", timeout=45)
    positions = _json_request(
        base + "/strategy/ibkr-paper-flatten-preview-suite",
        method="POST",
        payload={"candidate_limit": 50, "preview_limit": 1, "batch_limit": 1},
        timeout=60,
    )
    receipt = build_receipt(
        run_id=args.run_id,
        job=args.job,
        public_head=args.public_head,
        runtime=runtime,
        health=health,
        open_orders=open_orders,
        positions=positions,
    )
    if not receipt["ok"]:
        Path(args.receipt).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("IBKR_REMOTE_PAPER_SESSION=" + json.dumps(receipt, sort_keys=True))
        raise SystemExit(43)

    request = json.loads(Path(runtime["request_path"]).read_text(encoding="utf-8"))
    return_recipient = request.get("encrypted_return") if isinstance(request, dict) else None
    if return_recipient is not None:
        if not args.status_json or not args.encrypted_return_dir:
            raise SystemExit("encrypted account return requires --status-json and --encrypted-return-dir")
        status = load_ready_status(Path(args.status_json))
        snapshot = build_account_snapshot(
            run_id=args.run_id,
            runtime=runtime,
            status=status,
            open_orders_body=open_orders[1],
        )
        envelope = encrypt_account_snapshot(
            run_id=args.run_id,
            snapshot=snapshot,
            recipient=return_recipient,
            output_dir=Path(args.encrypted_return_dir),
        )
        receipt["encrypted_account_return"] = {
            "published": False,
            "recipient_key_id": envelope["recipient_key_id"],
            "ciphertext_sha256": envelope["ciphertext_sha256"],
            "plaintext_sha256": envelope["plaintext_sha256"],
            "chunk_count": len(envelope["chunks"]),
        }

    out = Path(args.receipt)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("IBKR_REMOTE_PAPER_SESSION=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
