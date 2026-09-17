from __future__ import annotations

"""Receive one run-bound encrypted read request for the warm IBKR gateway.

The GitHub workflow exposes only a boolean read-request flag and a random run
correlation nonce. Requested symbols and the one-run return recipient arrive
inside an X25519/HKDF/ChaCha20-Poly1305 envelope after the run starts.
"""

import argparse
import base64
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

import ephemeral_x25519_chunked_v1 as crypto
import ibkr_warm_selected_runtime_activation_v1 as exchange

RECIPIENT_SCHEMA = "ibkr-warm-read-request-recipient-v1"
ENVELOPE_SCHEMA = "ibkr-warm-read-request-x25519-v1"
REQUEST_SCHEMA = "mmibkr.ibkr_warm_read_request.v1"
RETURN_RECIPIENT_SCHEMA = "ibkr-remote-paper-return-recipient-v1"
AUTHORITY = "mm_ibkr_paper_runtime"
HARNESS = "mm_ibkr_warm_read_gateway_v1"
RECIPIENT_ROOT = "rendezvous/recipients"
RESPONSE_ROOT = "rendezvous/responses"


class WarmReadRequestError(RuntimeError):
    pass


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise WarmReadRequestError(f"{name} required")
    return text


def _valid_sha(value: Any) -> str:
    text = _required_text(value, "public_head").lower()
    if len(text) != 40 or any(ch not in "0123456789abcdef" for ch in text):
        raise WarmReadRequestError("public_head must be a 40-character hexadecimal SHA")
    return text


def _valid_nonce(value: Any) -> str:
    text = _required_text(value, "dispatch_nonce").lower()
    if not (8 <= len(text) <= 64) or any(ch not in "0123456789abcdef" for ch in text):
        raise WarmReadRequestError("dispatch_nonce must be 8-64 hexadecimal characters")
    return text


def normalize_symbols(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise WarmReadRequestError("symbols must be a list")
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        symbol = str(raw or "").strip().upper()
        if not symbol or len(symbol) > 24 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for ch in symbol):
            raise WarmReadRequestError("read request contains an invalid symbol")
        if symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    if not out or len(out) > 32:
        raise WarmReadRequestError("read request must contain 1-32 symbols")
    return out


def generate_recipient(*, run_id: str, private_key_path: Path) -> dict[str, Any]:
    run_id = _required_text(run_id, "run_id")
    if not run_id.isdigit():
        raise WarmReadRequestError("run_id must be numeric")
    private = x25519.X25519PrivateKey.generate()
    private_raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    private_key_path.write_text(base64.b64encode(private_raw).decode("ascii"), encoding="ascii")
    os.chmod(private_key_path, stat.S_IRUSR | stat.S_IWUSR)
    return {
        "schema": RECIPIENT_SCHEMA,
        "run_id": run_id,
        "recipient_b64": base64.b64encode(public_raw).decode("ascii"),
        "recipient_key_id": "sha256:" + hashlib.sha256(public_raw).hexdigest(),
        "authority": AUTHORITY,
        "harness": HARNESS,
    }


def publish_recipient(
    *, token: str, repository: str, branch: str, run_id: str, recipient: Mapping[str, Any],
    publisher: Callable[..., None] = exchange.publish_new_text,
) -> str:
    if recipient.get("schema") != RECIPIENT_SCHEMA or str(recipient.get("run_id")) != str(run_id):
        raise WarmReadRequestError("read request recipient identity mismatch")
    if recipient.get("authority") != AUTHORITY or recipient.get("harness") != HARNESS:
        raise WarmReadRequestError("read request recipient authority mismatch")
    path = f"{RECIPIENT_ROOT}/{run_id}-ibkr-warm-read.json"
    publisher(
        token=token, repository=repository, branch=branch, path=path,
        content=json.dumps(dict(recipient), sort_keys=True) + "\n",
        message="rendezvous: publish one-run IBKR warm-read request recipient",
    )
    return path


def wait_envelope(
    *, token: str, repository: str, branch: str, run_id: str, timeout_sec: int,
    fetcher: Callable[..., bytes] = exchange.fetch_raw, sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    path = f"{RESPONSE_ROOT}/{run_id}/ibkr-warm-read-envelope.json"
    deadline = time.monotonic() + max(1, int(timeout_sec))
    while time.monotonic() < deadline:
        try:
            raw = fetcher(token=token, repository=repository, branch=branch, path=path)
        except HTTPError as exc:
            if exc.code == 404:
                sleep(2.0)
                continue
            raise
        try:
            node = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise WarmReadRequestError("encrypted warm read request envelope is not valid JSON") from exc
        return node if isinstance(node, dict) else {}
    raise WarmReadRequestError("run-bound encrypted warm read request did not arrive")


def assemble_ciphertext(
    *, envelope: Mapping[str, Any], token: str, repository: str, branch: str, run_id: str,
    fetcher: Callable[..., bytes] = exchange.fetch_raw,
) -> bytes:
    chunks = envelope.get("chunks")
    if not isinstance(chunks, list) or not chunks or len(chunks) > 64:
        raise WarmReadRequestError("encrypted warm read request chunk list invalid")
    prefix = f"{RESPONSE_ROOT}/{run_id}/"
    pieces: list[str] = []
    seen: set[str] = set()
    for node in chunks:
        if not isinstance(node, Mapping) or set(node) != {"path", "sha256", "chars"}:
            raise WarmReadRequestError("encrypted warm read request chunk descriptor invalid")
        path = str(node.get("path") or "")
        if not path.startswith(prefix) or path in seen or ".." in path.split("/"):
            raise WarmReadRequestError("encrypted warm read request chunk path rejected")
        seen.add(path)
        raw = fetcher(token=token, repository=repository, branch=branch, path=path)
        if len(raw) != int(node.get("chars") or 0) or hashlib.sha256(raw).hexdigest() != str(node.get("sha256") or ""):
            raise WarmReadRequestError("encrypted warm read request chunk identity mismatch")
        pieces.append(raw.decode("ascii"))
    try:
        ciphertext = base64.b64decode("".join(pieces).encode("ascii"), validate=True)
    except Exception as exc:
        raise WarmReadRequestError("encrypted warm read request chunks are not valid base64") from exc
    if hashlib.sha256(ciphertext).hexdigest() != str(envelope.get("ciphertext_sha256") or ""):
        raise WarmReadRequestError("encrypted warm read request ciphertext digest mismatch")
    return ciphertext


def validate_request(
    node: Any, *, run_id: str, public_head: str, dispatch_nonce: str,
) -> dict[str, Any]:
    required = {"schema", "run_id", "public_head", "dispatch_nonce", "mode", "symbols", "return_recipient"}
    if not isinstance(node, dict) or set(node) != required:
        raise WarmReadRequestError("warm read request field set mismatch")
    if node.get("schema") != REQUEST_SCHEMA or str(node.get("run_id")) != str(run_id):
        raise WarmReadRequestError("warm read request run/schema mismatch")
    if _valid_sha(node.get("public_head")) != _valid_sha(public_head):
        raise WarmReadRequestError("warm read request public head mismatch")
    if _valid_nonce(node.get("dispatch_nonce")) != _valid_nonce(dispatch_nonce):
        raise WarmReadRequestError("warm read request dispatch nonce mismatch")
    if node.get("mode") != "readonly":
        raise WarmReadRequestError("warm read request mode must be readonly")
    symbols = normalize_symbols(node.get("symbols"))
    rr = node.get("return_recipient")
    if not isinstance(rr, dict) or set(rr) != {"schema", "recipient_b64", "recipient_key_id"}:
        raise WarmReadRequestError("warm read return recipient field set mismatch")
    if rr.get("schema") != RETURN_RECIPIENT_SCHEMA:
        raise WarmReadRequestError("warm read return recipient schema mismatch")
    try:
        raw = base64.b64decode(str(rr.get("recipient_b64") or "").encode("ascii"), validate=True)
    except Exception as exc:
        raise WarmReadRequestError("warm read return recipient encoding invalid") from exc
    if len(raw) != 32 or rr.get("recipient_key_id") != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise WarmReadRequestError("warm read return recipient fingerprint mismatch")
    out = dict(node)
    out["symbols"] = symbols
    out["return_recipient"] = dict(rr)
    return out


def materialize_request(
    *, envelope: Mapping[str, Any], ciphertext: bytes, private_key_path: Path,
    run_id: str, public_head: str, dispatch_nonce: str, output_path: Path,
) -> dict[str, Any]:
    plaintext = crypto.decrypt_assembled_ciphertext(
        envelope=dict(envelope), ciphertext=ciphertext, private_key_path=private_key_path,
        expected_schema=ENVELOPE_SCHEMA, expected_run_id=str(run_id), expected_harness=HARNESS,
        response_root=f"{RESPONSE_ROOT}/{run_id}", expected_authority=AUTHORITY,
    )
    try:
        node = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise WarmReadRequestError("warm read request plaintext is not valid JSON") from exc
    request = validate_request(node, run_id=run_id, public_head=public_head, dispatch_nonce=dispatch_nonce)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(request, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(output_path, stat.S_IRUSR | stat.S_IWUSR)
    return request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--public-head", required=True)
    parser.add_argument("--dispatch-nonce", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--exchange-ref", default="rendezvous-exchange")
    parser.add_argument("--runner-temp", required=True)
    parser.add_argument("--wait-seconds", type=int, default=900)
    args = parser.parse_args()

    token = str(os.environ.get("GH_TOKEN") or "").strip()
    if not token:
        raise WarmReadRequestError("GH_TOKEN required")
    root = Path(args.runner_temp) / "ibkr-warm-read-request"
    private_key_path = root / "request-private-key.b64"
    output_path = root / "request.json"
    recipient = generate_recipient(run_id=args.run_id, private_key_path=private_key_path)
    publish_recipient(token=token, repository=args.repository, branch=args.exchange_ref, run_id=args.run_id, recipient=recipient)
    envelope = wait_envelope(
        token=token, repository=args.repository, branch=args.exchange_ref, run_id=args.run_id,
        timeout_sec=args.wait_seconds,
    )
    ciphertext = assemble_ciphertext(
        envelope=envelope, token=token, repository=args.repository, branch=args.exchange_ref, run_id=args.run_id,
    )
    request = materialize_request(
        envelope=envelope, ciphertext=ciphertext, private_key_path=private_key_path,
        run_id=args.run_id, public_head=args.public_head, dispatch_nonce=args.dispatch_nonce, output_path=output_path,
    )
    print("IBKR_WARM_READ_REQUEST_READY=" + json.dumps({
        "run_id": str(args.run_id),
        "symbol_count": len(request["symbols"]),
        "request_encrypted": True,
        "return_recipient_bound": True,
        "plaintext_published": False,
        "broker_action": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
