from __future__ import annotations

"""Consume a Fleet-attested MM-IBKR source relay inside canonical B1.

The hot B1 run already owns one ephemeral X25519 private key used for its
selected-runtime command recipient. MM's public runtime re-encrypts the exact
private-producer-attested source archive to that same recipient. Fleet Authority
admits the relay only when the source SHA/archive digest/byte count match a
private MM producer attestation.

This module has no private-repository token and no contract/strategy authority.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

AUDIENCE = "mmibkr-fleet-authority"
RESPONSE_SCHEMA = "mmibkr-cloud-source-x25519-v1"
HARNESS = "mmibkr_cloud_source_exchange_v1"
INFO = b"mmibkr-cloud-source-exchange-v1"
PRIVATE_REPOSITORY = "XoticHaze/mm-IBKR"
PRIVATE_WORKFLOW_PREFIX = (
    "XoticHaze/mm-IBKR/.github/workflows/mmibkr-cloud-source-producer-r1.yml@"
)
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _b64d(value: Any, *, name: str, size: int | None = None) -> bytes:
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
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )


def _oidc_token() -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url or not token:
        raise RuntimeError("github_oidc_environment_missing")
    req = Request(
        _oidc_url(url),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=20) as response:
        node = json.loads(response.read().decode("utf-8"))
    value = str(node.get("value") or "")
    if value.count(".") != 2:
        raise RuntimeError("github_oidc_token_invalid")
    return value


def _api(
    authority_base: str,
    path: str,
    *,
    method: str,
    run_id: str,
    token: str,
    payload: Mapping[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, bytes, Mapping[str, str]]:
    if not str(authority_base).startswith("https://"):
        raise RuntimeError("authority_url_rejected")
    body = None
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "mmibkr-b1-attested-source-consumer-v1",
        "X-MMIBKR-Caller-Run-Id": str(run_id),
    }
    if payload is not None:
        body = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    req = Request(
        str(authority_base).rstrip("/") + path,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return (
                int(response.status),
                response.read(MAX_ARCHIVE_BYTES * 2),
                dict(response.headers.items()),
            )
    except HTTPError as exc:
        return (
            int(exc.code),
            exc.read(65536),
            dict(exc.headers.items()) if exc.headers else {},
        )


def _source_ticket(source: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "repository",
        "head",
        "archive_sha256",
        "archive_bytes",
        "transport",
    }
    if not isinstance(source, Mapping) or set(source) != required:
        raise RuntimeError("b1_attested_source_ticket_field_set_rejected")
    if source.get("repository") != PRIVATE_REPOSITORY:
        raise RuntimeError("b1_attested_source_repository_rejected")
    if source.get("transport") != "fleet_private_attested_source_v1":
        raise RuntimeError("b1_attested_source_transport_rejected")
    head = str(source.get("head") or "").strip().lower()
    digest = str(source.get("archive_sha256") or "").strip().lower()
    size = int(source.get("archive_bytes") or 0)
    if len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
        raise RuntimeError("b1_attested_source_head_rejected")
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise RuntimeError("b1_attested_source_digest_rejected")
    if size <= 0 or size > MAX_ARCHIVE_BYTES:
        raise RuntimeError("b1_attested_source_size_rejected")
    return {
        "repository": PRIVATE_REPOSITORY,
        "head": head,
        "archive_sha256": digest,
        "archive_bytes": size,
        "transport": "fleet_private_attested_source_v1",
    }


def _producer_attestation(
    value: Mapping[str, Any],
    *,
    ticket: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError("b1_private_source_attestation_missing")
    if value.get("schema") != "mmibkr-cloud-source-private-attestation-v1":
        raise RuntimeError("b1_private_source_attestation_schema_rejected")
    if str(value.get("source_sha") or "").lower() != ticket["head"]:
        raise RuntimeError("b1_private_source_attestation_head_mismatch")
    if str(value.get("plaintext_sha256") or "").lower() != ticket["archive_sha256"]:
        raise RuntimeError("b1_private_source_attestation_digest_mismatch")
    if int(value.get("archive_bytes") or 0) != ticket["archive_bytes"]:
        raise RuntimeError("b1_private_source_attestation_size_mismatch")
    producer = value.get("producer_identity")
    if not isinstance(producer, Mapping):
        raise RuntimeError("b1_private_source_producer_identity_missing")
    if producer.get("repository") != PRIVATE_REPOSITORY:
        raise RuntimeError("b1_private_source_producer_repository_rejected")
    if str(producer.get("repository_visibility") or "") != "private":
        raise RuntimeError("b1_private_source_producer_visibility_rejected")
    workflow_ref = str(producer.get("workflow_ref") or "")
    if not workflow_ref.startswith(PRIVATE_WORKFLOW_PREFIX):
        raise RuntimeError("b1_private_source_producer_workflow_rejected")
    if str(producer.get("run_id") or "").isdigit() is not True:
        raise RuntimeError("b1_private_source_producer_run_id_rejected")
    return dict(value)


def _aad(
    *,
    run_id: str,
    source_ref: str,
    source_sha: str,
    recipient_key_id: str,
) -> bytes:
    return json.dumps(
        {
            "schema": RESPONSE_SCHEMA,
            "run_id": str(run_id),
            "harness": HARNESS,
            "source_ref": str(source_ref),
            "source_sha": str(source_sha),
            "recipient_key_id": str(recipient_key_id),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def consume_attested_source(
    *,
    authority_base: str,
    run_id: str,
    source_ticket: Mapping[str, Any],
    private_key_path: str | Path,
    token_factory=_oidc_token,
    api=_api,
) -> dict[str, Any]:
    run_id = str(run_id or "").strip()
    if not run_id.isdigit():
        raise RuntimeError("b1_attested_source_run_id_rejected")
    ticket = _source_ticket(source_ticket)

    private_raw = _b64d(
        Path(private_key_path).read_text(encoding="ascii").strip(),
        name="b1_source_private_key",
        size=32,
    )
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    recipient_key_id = "sha256:" + hashlib.sha256(public).hexdigest()

    token = token_factory()
    status, raw, _ = api(
        authority_base,
        f"/v1/source-exchange/b1/response/{run_id}",
        method="GET",
        run_id=run_id,
        token=token,
    )
    if status != 200:
        raise RuntimeError(f"b1_attested_source_manifest_http_{status}")
    wrapper = json.loads(raw.decode("utf-8"))
    manifest = wrapper.get("response") if isinstance(wrapper, Mapping) else None
    if wrapper.get("ok") is not True or not isinstance(manifest, Mapping):
        raise RuntimeError("b1_attested_source_manifest_not_ok")

    required = {
        "schema",
        "run_id",
        "harness",
        "source_ref",
        "source_sha",
        "recipient_key_id",
        "sender_public_b64",
        "salt_b64",
        "nonce_b64",
        "ciphertext_sha256",
        "plaintext_sha256",
        "archive_bytes",
        "ciphertext_bytes",
        "chunk_count",
        "chunks",
        "private_attestation",
        "relay_identity",
        "finalized_at",
    }
    if set(manifest) != required:
        raise RuntimeError("b1_attested_source_manifest_field_set_rejected")
    if manifest.get("schema") != RESPONSE_SCHEMA or manifest.get("harness") != HARNESS:
        raise RuntimeError("b1_attested_source_manifest_schema_rejected")
    if str(manifest.get("run_id") or "") != run_id:
        raise RuntimeError("b1_attested_source_manifest_run_mismatch")
    if str(manifest.get("source_sha") or "").lower() != ticket["head"]:
        raise RuntimeError("b1_attested_source_manifest_head_mismatch")
    if str(manifest.get("plaintext_sha256") or "").lower() != ticket["archive_sha256"]:
        raise RuntimeError("b1_attested_source_manifest_digest_mismatch")
    if int(manifest.get("archive_bytes") or 0) != ticket["archive_bytes"]:
        raise RuntimeError("b1_attested_source_manifest_size_mismatch")
    if str(manifest.get("recipient_key_id") or "") != recipient_key_id:
        raise RuntimeError("b1_attested_source_manifest_recipient_mismatch")
    _producer_attestation(manifest["private_attestation"], ticket=ticket)

    chunks = manifest.get("chunks")
    count = int(manifest.get("chunk_count") or 0)
    if not isinstance(chunks, list) or count <= 0 or len(chunks) != count or count > 2048:
        raise RuntimeError("b1_attested_source_chunk_manifest_rejected")
    encoded: list[str] = []
    for index, desc in enumerate(chunks):
        if not isinstance(desc, Mapping) or int(desc.get("index", -1)) != index:
            raise RuntimeError("b1_attested_source_chunk_descriptor_rejected")
        status, chunk_raw, headers = api(
            authority_base,
            f"/v1/source-exchange/b1/response/{run_id}/chunk/{index}",
            method="GET",
            run_id=run_id,
            token=token,
        )
        if status != 200:
            raise RuntimeError(f"b1_attested_source_chunk_http_{status}:{index}")
        text = chunk_raw.decode("ascii")
        expected = str(desc.get("sha256") or "")
        if len(text) != int(desc.get("chars") or 0) or _sha256(text.encode()) != expected:
            raise RuntimeError("b1_attested_source_chunk_integrity_rejected")
        header_digest = next(
            (
                value
                for key, value in headers.items()
                if key.lower() == "x-mmibkr-chunk-sha256"
            ),
            "",
        )
        if header_digest and header_digest != expected:
            raise RuntimeError("b1_attested_source_chunk_header_rejected")
        encoded.append(text)

    try:
        ciphertext = base64.b64decode("".join(encoded).encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("b1_attested_source_ciphertext_base64_rejected") from exc
    if len(ciphertext) != int(manifest.get("ciphertext_bytes") or 0):
        raise RuntimeError("b1_attested_source_ciphertext_size_rejected")
    if _sha256(ciphertext) != str(manifest.get("ciphertext_sha256") or ""):
        raise RuntimeError("b1_attested_source_ciphertext_digest_rejected")

    sender = _b64d(manifest["sender_public_b64"], name="b1_source_sender", size=32)
    salt = _b64d(manifest["salt_b64"], name="b1_source_salt", size=32)
    nonce = _b64d(manifest["nonce_b64"], name="b1_source_nonce", size=12)
    source_ref = str(manifest.get("source_ref") or "")
    aad = _aad(
        run_id=run_id,
        source_ref=source_ref,
        source_sha=ticket["head"],
        recipient_key_id=recipient_key_id,
    )
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender))
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=INFO,
    ).derive(shared)
    archive = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    if len(archive) != ticket["archive_bytes"]:
        raise RuntimeError("b1_attested_source_plaintext_size_rejected")
    if _sha256(archive) != ticket["archive_sha256"]:
        raise RuntimeError("b1_attested_source_plaintext_digest_rejected")

    cleanup_status, _, _ = api(
        authority_base,
        f"/v1/source-exchange/b1/cleanup/{run_id}",
        method="POST",
        run_id=run_id,
        token=token,
        payload={},
    )
    return {
        "schema": "mmibkr.b1_attested_source_materialization.v1",
        "ok": True,
        "run_id": run_id,
        "source_ref": source_ref,
        "source_sha": ticket["head"],
        "archive_sha256": ticket["archive_sha256"],
        "archive_bytes": ticket["archive_bytes"],
        "archive": archive,
        "private_attestation_verified": True,
        "source_exchange_cleanup_ok": cleanup_status == 200,
        "private_repository_token_used": False,
    }


__all__ = [
    "consume_attested_source",
]
