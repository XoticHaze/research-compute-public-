from __future__ import annotations

"""Consume one run-bound opaque envelope from the Cloudflare fleet authority.

The decrypted payload is treated as opaque bytes and is never printed. This module
only authenticates GitHub Actions to the authority, validates the run/recipient
binding, and writes the authenticated plaintext to a mode-0600 output file.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

AUDIENCE = "mmibkr-fleet-authority"
REQUEST_SCHEMA = "mmibkr-fleet-authority-seal-request-v1"
ENVELOPE_SCHEMA = "mmibkr-ibkr-readonly-gateway-env-x25519-hkdf-aesgcm-v1"
AUTHORITY = "ibkr-paper-readonly"
MAX_PLAINTEXT = 4096


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode(value: object, *, name: str, size: int | None = None) -> bytes:
    try:
        raw = base64.b64decode(str(value).encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError(f"{name}_invalid") from exc
    if size is not None and len(raw) != size:
        raise RuntimeError(f"{name}_size_invalid")
    return raw


def _oidc_url(base: str) -> str:
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["audience"] = AUDIENCE
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))


def _oidc_token() -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url or not token:
        raise RuntimeError("github_oidc_environment_missing")
    req = Request(_oidc_url(url), headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        node = json.loads(response.read().decode("utf-8"))
    value = str(node.get("value") or "")
    if value.count(".") != 2:
        raise RuntimeError("github_oidc_token_invalid")
    return value


def _request_envelope(url: str, *, run_id: str, recipient_b64: str, recipient_key_id: str) -> dict:
    payload = {
        "schema": REQUEST_SCHEMA,
        "authority": AUTHORITY,
        "run_id": run_id,
        "recipient_b64": recipient_b64,
        "recipient_key_id": recipient_key_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    req = Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Authorization": "Bearer " + _oidc_token(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "mmibkr-fleet-authority-consumer-v1",
        },
    )
    with urlopen(req, timeout=30) as response:
        body = response.read(65537)
        if response.status != 200:
            raise RuntimeError(f"fleet_authority_http_{response.status}")
    if len(body) > 65536:
        raise RuntimeError("fleet_authority_response_too_large")
    node = json.loads(body.decode("utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError("fleet_authority_response_invalid")
    return node


def _decrypt(envelope: dict, *, run_id: str, recipient: x25519.X25519PrivateKey, key_id: str) -> bytes:
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        raise RuntimeError("envelope_schema_rejected")
    if envelope.get("authority") != AUTHORITY or str(envelope.get("run_id")) != run_id:
        raise RuntimeError("envelope_identity_rejected")
    if envelope.get("recipient_key_id") != key_id:
        raise RuntimeError("envelope_recipient_rejected")

    peer = _decode(envelope.get("ephemeral_public_b64"), name="ephemeral_public", size=32)
    salt = _decode(envelope.get("salt_b64"), name="salt", size=32)
    iv = _decode(envelope.get("iv_b64"), name="iv", size=12)
    aad = _decode(envelope.get("aad_b64"), name="aad")
    ciphertext = _decode(envelope.get("ciphertext_b64"), name="ciphertext")
    expected_aad = f"mmibkr-fleet-authority|{AUTHORITY}|{run_id}|{key_id}".encode("utf-8")
    if aad != expected_aad:
        raise RuntimeError("envelope_aad_rejected")

    shared = recipient.exchange(x25519.X25519PublicKey.from_public_bytes(peer))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=aad).derive(shared)
    plaintext = AESGCM(key).decrypt(iv, ciphertext, aad)
    if not plaintext or len(plaintext) > MAX_PLAINTEXT or b"\x00" in plaintext:
        raise RuntimeError("envelope_plaintext_rejected")
    return plaintext


def consume(authority_url: str, *, run_id: str, output: Path, receipt: Path | None = None) -> dict:
    if not authority_url.startswith("https://"):
        raise RuntimeError("authority_url_rejected")
    if not run_id.isdigit() or not 4 <= len(run_id) <= 24:
        raise RuntimeError("run_id_rejected")

    private = x25519.X25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key_id = "sha256:" + hashlib.sha256(public).hexdigest()
    envelope = _request_envelope(authority_url, run_id=run_id, recipient_b64=_b64(public), recipient_key_id=key_id)
    plaintext = _decrypt(envelope, run_id=run_id, recipient=private, key_id=key_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(plaintext)
    os.chmod(output, 0o600)

    proof = {
        "schema": "mmibkr-fleet-authority-consumer-receipt-v1",
        "ok": True,
        "run_id": run_id,
        "authority": AUTHORITY,
        "envelope_schema": ENVELOPE_SCHEMA,
        "recipient_key_id": key_id,
        "plaintext_bytes": len(plaintext),
        "plaintext_emitted": False,
    }
    if receipt:
        receipt.write_text(json.dumps(proof, sort_keys=True) + "\n", encoding="utf-8")
    print("FLEET_AUTHORITY_ENVELOPE=" + json.dumps(proof, sort_keys=True))
    return proof


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-url", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt")
    args = parser.parse_args()
    consume(
        args.authority_url,
        run_id=str(args.run_id),
        output=Path(args.output),
        receipt=Path(args.receipt) if args.receipt else None,
    )


if __name__ == "__main__":
    main()
