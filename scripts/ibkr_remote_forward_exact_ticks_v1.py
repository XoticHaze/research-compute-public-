from __future__ import annotations

"""Execute one exact MM-IBKR historical-tick plan on the authenticated B1 Gateway.

This adapter owns transport only. The attested private MM source owns request-plan
validation, IBKR historical-tick paging, and evidence semantics. This module never
submits, cancels, replaces, or flattens an order and requires the Gateway API to
remain read-only.
"""

import base64
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
MODE = "forward_exact_ticks"
RECEIPT_SCHEMA = "mmibkr.remote_forward_exact_tick_evidence_receipt.v1"
EVIDENCE_SCHEMA = "mmibkr.selected_runtime_forward_historical_tick_evidence.v1"
PRODUCER_SCHEMA = "mmibkr.selected_runtime_forward_historical_tick_producer.v1"
RETURN_RECIPIENT_SCHEMA = "ibkr-remote-paper-return-recipient-v1"
RETURN_ENVELOPE_SCHEMA = "ibkr-forward-exact-ticks-return-x25519-v1"
AUTHORITY = "mm_ibkr_paper_runtime"
HARNESS = "mmibkr_forward_exact_ticks_b1_v1"
RETURN_INFO = b"mmibkr-forward-exact-ticks-return-v1"
CHUNK_CHARS = 8000


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def validate_runtime(runtime: Mapping[str, Any], request: Mapping[str, Any]) -> None:
    if str(runtime.get("mode") or "") != MODE:
        raise RuntimeError("exact tick runtime mode mismatch")
    if runtime.get("paper_only") is not True:
        raise RuntimeError("exact tick runtime must remain paper session")
    if runtime.get("live_trading_change") is not False:
        raise RuntimeError("exact tick runtime live authority rejected")
    if runtime.get("read_only_api") != "yes":
        raise RuntimeError("exact tick Gateway API must remain read-only")
    if runtime.get("private_repository_token_used") is not False:
        raise RuntimeError("exact tick runtime must use attested private source")
    if runtime.get("source_transport") != "fleet_private_attested_source_v1":
        raise RuntimeError("exact tick attested source transport required")
    source_root = Path(str(runtime.get("source_root") or ""))
    if not source_root.is_dir():
        raise RuntimeError("exact tick private source root missing")
    if not str(runtime.get("mmibkr_head") or "").strip():
        raise RuntimeError("exact tick MM source identity missing")
    if str(request.get("command_id") or "") != str(runtime.get("command_id") or ""):
        raise RuntimeError("exact tick command identity mismatch")
    if str(request.get("source_sha") or "").strip().lower() != str(runtime.get("mmibkr_head") or "").strip().lower():
        raise RuntimeError("exact tick request/source identity mismatch")
    plan = request.get("tick_plan")
    if not isinstance(plan, Mapping):
        raise RuntimeError("exact tick plan missing")
    if plan.get("broker_submission") is not False or plan.get("live_execution_allowed") is not False:
        raise RuntimeError("exact tick plan authority drift")


def load_private_producer(source_root: str | Path):
    root = str(Path(source_root).resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    mod = importlib.import_module(
        "scripts.operator.selected_runtime_forward_historical_tick_producer_v1"
    )
    if str(getattr(mod, "PRODUCER_SCHEMA", "")) != PRODUCER_SCHEMA:
        raise RuntimeError("exact tick private producer schema mismatch")
    if not callable(getattr(mod, "produce_historical_tick_evidence", None)):
        raise RuntimeError("exact tick private producer callable missing")
    return mod


def validate_evidence(evidence: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    node = _mapping(evidence)
    if node.get("schema") != EVIDENCE_SCHEMA:
        raise RuntimeError("exact tick evidence schema mismatch")
    if node.get("producer_schema") != PRODUCER_SCHEMA:
        raise RuntimeError("exact tick evidence producer mismatch")
    if node.get("pair_id") != plan.get("pair_id"):
        raise RuntimeError("exact tick evidence pair identity mismatch")
    if _mapping(node.get("identity")) != _mapping(plan.get("identity")):
        raise RuntimeError("exact tick evidence strategy identity mismatch")
    if node.get("historical_tick_domain") != "IBKR_TRADES":
        raise RuntimeError("exact tick evidence domain mismatch")
    if node.get("timestamp_resolution") != "seconds":
        raise RuntimeError("exact tick evidence timestamp resolution mismatch")
    for field in (
        "producer_inference",
        "broker_order_action",
        "broker_submission",
        "runtime_authority_change",
        "strategy_spec_mutation",
        "live_execution_allowed",
    ):
        if node.get(field) is not False:
            raise RuntimeError(f"exact tick evidence authority boundary violated: {field}")
    boundaries = node.get("boundaries")
    if not isinstance(boundaries, Mapping) or set(boundaries) != {"entry", "exit"}:
        raise RuntimeError("exact tick evidence boundary set mismatch")
    return node


def collect_with_connected_ib(
    *,
    runtime: Mapping[str, Any],
    request: Mapping[str, Any],
    ib: Any,
    producer: Any,
    run_id: str,
    public_head: str,
) -> dict[str, Any]:
    validate_runtime(runtime, request)
    plan = _mapping(request.get("tick_plan"))
    evidence = ib.run(producer.produce_historical_tick_evidence(ib, plan))
    evidence = validate_evidence(evidence, plan)
    return {
        "schema": RECEIPT_SCHEMA,
        "ok": True,
        "status": "EXACT_TICK_EVIDENCE_COLLECTED",
        "github": {"run_id": str(run_id), "public_head": str(public_head)},
        "mmibkr": {
            "head": runtime.get("mmibkr_head"),
            "source_archive_sha256": runtime.get("source_archive_sha256"),
            "source_transport": runtime.get("source_transport"),
        },
        "command": {
            "command_id": request.get("command_id"),
            "source_ref": request.get("source_ref"),
            "pair_id": plan.get("pair_id"),
        },
        "evidence": evidence,
        "authority": {
            "read_only_ibkr_historical_ticks": True,
            "private_mm_producer_authority": True,
            "public_producer_inference": False,
            "broker_order_action": False,
            "broker_submission": False,
            "cancel_called": False,
            "flatten_called": False,
            "global_cancel_called": False,
            "runtime_authority_change": False,
            "strategy_spec_mutation": False,
            "promotion_mutation": False,
            "live_execution_allowed": False,
        },
    }


def collect_evidence(
    *,
    runtime: Mapping[str, Any],
    request: Mapping[str, Any],
    host: str,
    port: int,
    client_id: int,
    run_id: str,
    public_head: str,
) -> dict[str, Any]:
    validate_runtime(runtime, request)
    producer = load_private_producer(runtime["source_root"])
    # Broker dependency belongs to the B1 execution path, not source-level
    # contract inspection/import.
    from ib_insync import IB

    ib = IB()
    try:
        ib.connect(str(host), int(port), clientId=int(client_id), timeout=10, readonly=True)
        if not ib.isConnected():
            raise RuntimeError("exact tick read-only Gateway connection failed")
        return collect_with_connected_ib(
            runtime=runtime,
            request=request,
            ib=ib,
            producer=producer,
            run_id=run_id,
            public_head=public_head,
        )
    finally:
        if ib.isConnected():
            ib.disconnect()


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


def encrypt_receipt(
    *,
    receipt: Mapping[str, Any],
    recipient: Mapping[str, Any],
    run_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("ok") is not True:
        raise RuntimeError("exact tick return receipt rejected")
    authority = _mapping(receipt.get("authority"))
    for field in (
        "broker_order_action",
        "broker_submission",
        "cancel_called",
        "flatten_called",
        "global_cancel_called",
        "runtime_authority_change",
        "strategy_spec_mutation",
        "promotion_mutation",
        "live_execution_allowed",
    ):
        if authority.get(field) is not False:
            raise RuntimeError(f"exact tick return authority boundary violated: {field}")
    if recipient.get("schema") != RETURN_RECIPIENT_SCHEMA:
        raise RuntimeError("exact tick return recipient schema mismatch")
    try:
        recipient_raw = base64.b64decode(
            str(recipient.get("recipient_b64") or "").encode("ascii"),
            validate=True,
        )
    except Exception as exc:
        raise RuntimeError("exact tick return recipient encoding invalid") from exc
    if len(recipient_raw) != 32:
        raise RuntimeError("exact tick return recipient key length invalid")
    key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if key_id != str(recipient.get("recipient_key_id") or ""):
        raise RuntimeError("exact tick return recipient fingerprint mismatch")

    plaintext = json.dumps(
        dict(receipt), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    sender = x25519.X25519PrivateKey.generate()
    sender_public = sender.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    aad = _aad(run_id=run_id, recipient_key_id=key_id)
    shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_raw))
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=RETURN_INFO,
    ).derive(shared)
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
    payload = base64.b64encode(ciphertext).decode("ascii")

    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    chunks: list[dict[str, Any]] = []
    for index, start in enumerate(range(0, len(payload), CHUNK_CHARS)):
        text = payload[start:start + CHUNK_CHARS]
        local_name = f"ibkr-forward-exact-ticks-{index:03d}.txt"
        path = output_dir / local_name
        path.write_text(text, encoding="ascii")
        os.chmod(path, 0o600)
        chunks.append({
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
        "recipient_key_id": key_id,
        "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "chunks": chunks,
    }
    envelope_path = output_dir / "ibkr-forward-exact-ticks-envelope.json"
    envelope_path.write_text(json.dumps(envelope, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(envelope_path, 0o600)
    return envelope


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--client-id", type=int, default=81)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--public-head", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    receipt = collect_evidence(
        runtime=runtime,
        request=request,
        host=args.host,
        port=args.port,
        client_id=args.client_id,
        run_id=args.run_id,
        public_head=args.public_head,
    )
    receipt_path = Path(args.output)
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(receipt_path, 0o600)

    recipient_path = Path(str(runtime.get("return_recipient_path") or ""))
    if runtime.get("encrypted_return_requested") is not True or not recipient_path.is_file():
        raise RuntimeError("exact tick encrypted return recipient missing")
    recipient = json.loads(recipient_path.read_text(encoding="utf-8"))
    envelope = encrypt_receipt(
        receipt=receipt,
        recipient=recipient,
        run_id=args.run_id,
        output_dir=Path(args.output_dir),
    )
    evidence = _mapping(receipt.get("evidence"))
    boundaries = _mapping(evidence.get("boundaries"))
    print("IBKR_FORWARD_EXACT_TICKS_READY=" + json.dumps({
        "run_id": str(args.run_id),
        "pair_id": evidence.get("pair_id"),
        "entry_ticks": len(_mapping(boundaries.get("entry")).get("ticks") or []),
        "exit_ticks": len(_mapping(boundaries.get("exit")).get("ticks") or []),
        "entry_coverage_complete": _mapping(boundaries.get("entry")).get("coverage_complete") is True,
        "exit_coverage_complete": _mapping(boundaries.get("exit")).get("coverage_complete") is True,
        "ciphertext_sha256": envelope["ciphertext_sha256"],
        "plaintext_published": False,
        "producer_inference": False,
        "broker_order_action": False,
        "broker_submission": False,
        "live_execution_allowed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
