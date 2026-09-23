from __future__ import annotations

"""Read-only paper-account snapshot return for maintenance reconciliation.

This helper intentionally excludes strategy state, historical bars, quotes,
completed executions, order submission, cancellation, and live authority.
It reads only the current paper account summary, positions, and open-order
count from an already-authenticated B1 Gateway, then encrypts that bounded
snapshot to a one-run X25519 recipient.
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

SNAPSHOT_SCHEMA = "mmibkr.ibkr_account_snapshot.v1"
ENVELOPE_SCHEMA = "ibkr-account-snapshot-return-x25519-v1"
AUTHORITY = "mm_ibkr_paper_runtime"
HARNESS = "mmibkr_b1_account_snapshot_v1"
RETURN_INFO = b"mmibkr-b1-account-snapshot-return-v1"
CHUNK_CHARS = 8000


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


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
        "lastTradeDateOrContractMonth": str(
            getattr(contract, "lastTradeDateOrContractMonth", "") or ""
        ),
    }


def validate_snapshot(snapshot: Mapping[str, Any], *, run_id: str) -> None:
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise RuntimeError("account snapshot schema mismatch")
    if str(snapshot.get("run_id") or "") != str(run_id):
        raise RuntimeError("account snapshot run mismatch")
    if snapshot.get("authority") != AUTHORITY or snapshot.get("harness") != HARNESS:
        raise RuntimeError("account snapshot authority mismatch")
    if snapshot.get("trading_mode") != "paper" or snapshot.get("read_only") is not True:
        raise RuntimeError("account snapshot paper/read-only boundary violated")
    if snapshot.get("paper_account_verified") is not True:
        raise RuntimeError("account snapshot paper-account proof missing")
    if int(snapshot.get("managed_account_count") or 0) < 1:
        raise RuntimeError("account snapshot managed account count missing")
    if snapshot.get("account_identifiers_included") is not False:
        raise RuntimeError("account snapshot account identifiers must be excluded")
    capabilities = (
        snapshot.get("capabilities")
        if isinstance(snapshot.get("capabilities"), Mapping)
        else {}
    )
    for required in ("account_state", "positions", "open_orders"):
        if capabilities.get(required) is not True:
            raise RuntimeError(f"account snapshot capability missing: {required}")
    for forbidden in (
        "historical_market_data",
        "quotes",
        "completed_executions",
        "order_submission",
        "order_cancel",
        "global_cancel",
        "live_execution",
    ):
        if capabilities.get(forbidden) is not False:
            raise RuntimeError(f"account snapshot forbidden capability enabled: {forbidden}")
    if not isinstance(snapshot.get("account_summary"), list):
        raise RuntimeError("account snapshot account summary missing")
    if not isinstance(snapshot.get("positions"), list):
        raise RuntimeError("account snapshot positions missing")
    if int(snapshot.get("position_count") or 0) != len(snapshot.get("positions") or []):
        raise RuntimeError("account snapshot position count mismatch")
    if int(snapshot.get("open_order_count") or 0) < 0:
        raise RuntimeError("account snapshot open order count invalid")


def collect_snapshot(
    *,
    host: str,
    port: int,
    client_id: int,
    run_id: str,
    public_head: str,
) -> dict[str, Any]:
    ib = IB()
    try:
        ib.connect(host, int(port), clientId=int(client_id), timeout=10, readonly=True)
        if not ib.isConnected():
            raise RuntimeError("account snapshot connection did not become ready")

        managed_accounts = [str(value) for value in ib.managedAccounts()]
        if not managed_accounts or any(
            not value.upper().startswith("DU") for value in managed_accounts
        ):
            raise RuntimeError("account snapshot is not bound exclusively to DU paper accounts")

        account_summary: list[dict[str, Any]] = []
        for node in ib.accountSummary():
            account_summary.append(
                {
                    "tag": str(getattr(node, "tag", "") or ""),
                    "value": str(getattr(node, "value", "") or ""),
                    "currency": str(getattr(node, "currency", "") or ""),
                    "model_code": str(getattr(node, "modelCode", "") or ""),
                }
            )

        positions: list[dict[str, Any]] = []
        for node in ib.positions():
            quantity = _finite(getattr(node, "position", 0.0))
            if quantity is None or abs(quantity) <= 1e-12:
                continue
            positions.append(
                {
                    "contract": _contract(getattr(node, "contract", None)),
                    "position": quantity,
                    "avg_cost": _finite(getattr(node, "avgCost", None)),
                }
            )

        ib.reqAllOpenOrders()
        ib.sleep(1)
        open_order_count = len(list(ib.openTrades() or []))

        snapshot = {
            "schema": SNAPSHOT_SCHEMA,
            "generated_at_utc": _iso_now(),
            "run_id": str(run_id),
            "public_head": str(public_head).strip().lower(),
            "authority": AUTHORITY,
            "harness": HARNESS,
            "trading_mode": "paper",
            "read_only": True,
            "paper_account_verified": True,
            "managed_account_count": len(managed_accounts),
            "account_identifiers_included": False,
            "account_summary": account_summary,
            "positions": positions,
            "position_count": len(positions),
            "open_order_count": open_order_count,
            "broker_time_utc": ib.reqCurrentTime().astimezone(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "capabilities": {
                "account_state": True,
                "positions": True,
                "open_orders": True,
                "historical_market_data": False,
                "quotes": False,
                "completed_executions": False,
                "order_submission": False,
                "order_cancel": False,
                "global_cancel": False,
                "live_execution": False,
            },
        }
        validate_snapshot(snapshot, run_id=run_id)
        return snapshot
    finally:
        if ib.isConnected():
            ib.disconnect()


def _aad(*, run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": ENVELOPE_SCHEMA,
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
    validate_snapshot(snapshot, run_id=run_id)
    try:
        raw_recipient = base64.b64decode(
            str(recipient_b64).encode("ascii"),
            validate=True,
        )
    except Exception as exc:
        raise RuntimeError("account snapshot recipient key encoding invalid") from exc
    if len(raw_recipient) != 32:
        raise RuntimeError("account snapshot recipient key length invalid")
    computed_key_id = "sha256:" + hashlib.sha256(raw_recipient).hexdigest()
    if computed_key_id != str(recipient_key_id):
        raise RuntimeError("account snapshot recipient fingerprint mismatch")

    plaintext = json.dumps(
        dict(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    aad = _aad(run_id=run_id, recipient_key_id=computed_key_id)
    shared = sender.exchange(
        x25519.X25519PublicKey.from_public_bytes(raw_recipient)
    )
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=RETURN_INFO,
    ).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    payload_b64 = base64.b64encode(ciphertext).decode("ascii")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(payload_b64), CHUNK_CHARS)):
        text = payload_b64[start : start + CHUNK_CHARS]
        local_name = f"ibkr-account-snapshot-{index:03d}.txt"
        path = output_dir / local_name
        path.write_text(text, encoding="ascii")
        manifest.append(
            {
                "path": f"rendezvous/returns/{run_id}/{local_name}",
                "local_name": local_name,
                "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
                "chars": len(text),
            }
        )

    envelope = {
        "schema": ENVELOPE_SCHEMA,
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
    (output_dir / "ibkr-account-snapshot-envelope.json").write_text(
        json.dumps(envelope, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--client-id", type=int, default=80)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--public-head", required=True)
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
    )
    envelope = encrypt_snapshot(
        snapshot=snapshot,
        recipient_b64=args.recipient_b64,
        recipient_key_id=args.recipient_key_id,
        run_id=args.run_id,
        output_dir=Path(args.output_dir),
    )
    print(
        "IBKR_ACCOUNT_SNAPSHOT_RETURN_READY="
        + json.dumps(
            {
                "run_id": str(args.run_id),
                "positions": len(snapshot["positions"]),
                "open_orders": int(snapshot["open_order_count"]),
                "ciphertext_sha256": envelope["ciphertext_sha256"],
                "account_identifiers_included": False,
                "plaintext_published": False,
                "broker_action": False,
                "live_execution_allowed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
