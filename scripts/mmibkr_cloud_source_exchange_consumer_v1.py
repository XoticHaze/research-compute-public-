from __future__ import annotations

"""Consume one OIDC-authenticated encrypted MM-IBKR source archive.

The public runner creates an ephemeral X25519 recipient and asks Fleet Authority
for one exact private source ref. A private MM-IBKR workflow encrypts a git archive
to that recipient and uploads ciphertext chunks to the source-exchange Durable
Object. Plaintext exists only in runner temp.

No private repository token or broker credential is required by this consumer.
"""

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

AUDIENCE = "mmibkr-fleet-authority"
REQUEST_SCHEMA = "mmibkr-cloud-source-request-v1"
RESPONSE_SCHEMA = "mmibkr-cloud-source-x25519-v1"
HARNESS = "mmibkr_cloud_source_exchange_v1"
INFO = b"mmibkr-cloud-source-exchange-v1"

PRIVATE_REPOSITORY = "XoticHaze/mm-IBKR"
PRIVATE_WORKFLOW_PATH = (
    "XoticHaze/mm-IBKR/.github/workflows/"
    "mmibkr-cloud-source-producer-r1.yml@"
)
ALLOWED_PRIVATE_REFS = {
    "refs/heads/main",
    "refs/heads/assistant/cloud-signal-history-split-20260918",
}

MAX_ARCHIVE_BYTES = 150 * 1024 * 1024
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_FILES = 30000


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(value: Any, *, name: str, size: int | None = None) -> bytes:
    try:
        raw = base64.b64decode(str(value).encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError(f"{name}_invalid") from exc
    if size is not None and len(raw) != size:
        raise RuntimeError(f"{name}_size_invalid")
    return raw


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
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
    caller_run_id: str,
    token: str,
    payload: Mapping[str, Any] | None = None,
    raw: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, bytes, Mapping[str, str]]:
    if not authority_base.startswith("https://"):
        raise RuntimeError("authority_url_rejected")
    url = authority_base.rstrip("/") + path
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "mmibkr-cloud-source-consumer-v1",
        "X-MMIBKR-Caller-Run-Id": str(caller_run_id),
    }
    data = raw
    if payload is not None:
        data = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read(MAX_ARCHIVE_BYTES * 2)
            return int(response.status), body, dict(response.headers.items())
    except HTTPError as exc:
        body = exc.read(65536)
        return int(exc.code), body, dict(exc.headers.items()) if exc.headers else {}


def _validate_source_ref(source_ref: str) -> str:
    ref = str(source_ref or "").strip()
    if (
        ref in {"main", "assistant/cloud-signal-history-split-20260918"}
        or (len(ref) == 40 and all(ch in "0123456789abcdef" for ch in ref.lower()))
    ):
        return ref
    raise ValueError("source_ref_rejected")


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
    ).encode("utf-8")


def _validate_producer_identity(identity: Mapping[str, Any]) -> None:
    if str(identity.get("repository") or "") != PRIVATE_REPOSITORY:
        raise RuntimeError("source_producer_repository_rejected")
    if str(identity.get("repository_visibility") or "private") not in {"", "private"}:
        raise RuntimeError("source_producer_visibility_rejected")
    ref = str(identity.get("ref") or "")
    if ref not in ALLOWED_PRIVATE_REFS:
        raise RuntimeError("source_producer_ref_rejected")
    if str(identity.get("workflow_ref") or "") != PRIVATE_WORKFLOW_PATH + ref:
        raise RuntimeError("source_producer_workflow_rejected")
    if str(identity.get("event_name") or "") not in {
        "push",
        "workflow_dispatch",
        "schedule",
    }:
        raise RuntimeError("source_producer_event_rejected")
    if not str(identity.get("run_id") or "").isdigit():
        raise RuntimeError("source_producer_run_id_rejected")


def _validate_manifest(
    response: Mapping[str, Any],
    *,
    run_id: str,
    source_ref: str,
    recipient_key_id: str,
) -> dict[str, Any]:
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
        "producer_identity",
        "finalized_at",
    }
    if not isinstance(response, Mapping) or set(response) != required:
        raise RuntimeError("source_manifest_field_set_rejected")
    if response.get("schema") != RESPONSE_SCHEMA or response.get("harness") != HARNESS:
        raise RuntimeError("source_manifest_schema_rejected")
    if str(response.get("run_id") or "") != str(run_id):
        raise RuntimeError("source_manifest_run_rejected")
    if str(response.get("source_ref") or "") != source_ref:
        raise RuntimeError("source_manifest_ref_rejected")
    source_sha = str(response.get("source_sha") or "").lower()
    if len(source_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_sha):
        raise RuntimeError("source_manifest_sha_rejected")
    if str(response.get("recipient_key_id") or "") != recipient_key_id:
        raise RuntimeError("source_manifest_recipient_rejected")
    for field in ("ciphertext_sha256", "plaintext_sha256"):
        value = str(response.get(field) or "").lower()
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise RuntimeError(f"source_manifest_{field}_rejected")
    archive_bytes = int(response.get("archive_bytes") or 0)
    ciphertext_bytes = int(response.get("ciphertext_bytes") or 0)
    if archive_bytes <= 0 or archive_bytes > MAX_ARCHIVE_BYTES:
        raise RuntimeError("source_manifest_archive_size_rejected")
    if ciphertext_bytes <= archive_bytes or ciphertext_bytes > MAX_ARCHIVE_BYTES + 64:
        raise RuntimeError("source_manifest_ciphertext_size_rejected")
    chunk_count = int(response.get("chunk_count") or 0)
    chunks = response.get("chunks")
    if (
        chunk_count <= 0
        or chunk_count > 2048
        or not isinstance(chunks, list)
        or len(chunks) != chunk_count
    ):
        raise RuntimeError("source_manifest_chunks_rejected")
    for index, desc in enumerate(chunks):
        if (
            not isinstance(desc, Mapping)
            or int(desc.get("index", -1)) != index
            or int(desc.get("chars") or 0) <= 0
            or int(desc.get("chars") or 0) > 100000
        ):
            raise RuntimeError("source_manifest_chunk_descriptor_rejected")
        digest = str(desc.get("sha256") or "").lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise RuntimeError("source_manifest_chunk_digest_rejected")
    identity = response.get("producer_identity")
    if not isinstance(identity, Mapping):
        raise RuntimeError("source_manifest_producer_identity_missing")
    _validate_producer_identity(identity)
    return dict(response)


def decrypt_archive(
    manifest: Mapping[str, Any],
    chunk_texts: list[str],
    *,
    private_key: x25519.X25519PrivateKey,
    run_id: str,
    source_ref: str,
    recipient_key_id: str,
) -> bytes:
    response = _validate_manifest(
        manifest,
        run_id=run_id,
        source_ref=source_ref,
        recipient_key_id=recipient_key_id,
    )
    chunks = response["chunks"]
    if len(chunk_texts) != len(chunks):
        raise RuntimeError("source_chunk_count_rejected")
    encoded: list[str] = []
    for index, text in enumerate(chunk_texts):
        raw = str(text).encode("ascii")
        desc = chunks[index]
        if len(text) != int(desc["chars"]) or _sha256(raw) != str(desc["sha256"]):
            raise RuntimeError("source_chunk_integrity_rejected")
        encoded.append(text)
    try:
        ciphertext = base64.b64decode("".join(encoded).encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("source_ciphertext_base64_rejected") from exc
    if len(ciphertext) != int(response["ciphertext_bytes"]):
        raise RuntimeError("source_ciphertext_size_rejected")
    if _sha256(ciphertext) != str(response["ciphertext_sha256"]):
        raise RuntimeError("source_ciphertext_digest_rejected")

    peer = _b64d(response["sender_public_b64"], name="source_sender_public", size=32)
    salt = _b64d(response["salt_b64"], name="source_salt", size=32)
    nonce = _b64d(response["nonce_b64"], name="source_nonce", size=12)
    aad = _aad(
        run_id=run_id,
        source_ref=source_ref,
        source_sha=str(response["source_sha"]),
        recipient_key_id=recipient_key_id,
    )
    shared = private_key.exchange(x25519.X25519PublicKey.from_public_bytes(peer))
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=INFO,
    ).derive(shared)
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    if len(plaintext) != int(response["archive_bytes"]):
        raise RuntimeError("source_plaintext_size_rejected")
    if _sha256(plaintext) != str(response["plaintext_sha256"]):
        raise RuntimeError("source_plaintext_digest_rejected")
    return plaintext


def extract_archive(archive: bytes, destination: Path) -> Path:
    if not archive or len(archive) > MAX_ARCHIVE_BYTES:
        raise RuntimeError("source_archive_size_rejected")
    destination.mkdir(parents=True, exist_ok=True)
    root = (destination / "mm-ibkr").resolve()
    total = 0
    files = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
        members = tf.getmembers()
        if not members:
            raise RuntimeError("source_archive_empty")
        for member in members:
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] != "mm-ibkr"
            ):
                raise RuntimeError("source_archive_path_rejected")
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("source_archive_special_member_rejected")
            target = (destination / path).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("source_archive_escape_rejected")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError("source_archive_member_type_rejected")
            files += 1
            total += int(member.size or 0)
            if files > MAX_FILES or total > MAX_EXTRACTED_BYTES:
                raise RuntimeError("source_archive_expansion_rejected")
            handle = tf.extractfile(member)
            if handle is None:
                raise RuntimeError("source_archive_member_unreadable")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as out:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            try:
                os.chmod(target, int(member.mode) & 0o777)
            except OSError:
                pass
    if files <= 0 or not (root / "Dockerfile.bot").is_file():
        raise RuntimeError("source_archive_runtime_root_incomplete")
    return root


def consume(
    *,
    authority_base: str,
    run_id: str,
    source_ref: str,
    destination: Path,
    output: Path,
    timeout_sec: int = 900,
    api: Callable[..., tuple[int, bytes, Mapping[str, str]]] = _api,
    token_factory: Callable[[], str] = _oidc_token,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not str(run_id).isdigit():
        raise RuntimeError("run_id_rejected")
    source_ref = _validate_source_ref(source_ref)

    private = x25519.X25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    recipient_key_id = "sha256:" + hashlib.sha256(public).hexdigest()

    token = token_factory()
    request_payload = {
        "schema": REQUEST_SCHEMA,
        "run_id": str(run_id),
        "source_ref": source_ref,
        "recipient_b64": _b64(public),
        "recipient_key_id": recipient_key_id,
    }
    status, raw, _ = api(
        authority_base,
        "/v1/source-exchange/request",
        method="POST",
        caller_run_id=str(run_id),
        token=token,
        payload=request_payload,
    )
    if status not in {200, 201}:
        raise RuntimeError(f"source_exchange_request_http_{status}")
    node = json.loads(raw.decode("utf-8"))
    if node.get("ok") is not True:
        raise RuntimeError("source_exchange_request_not_ok")

    deadline = time.time() + max(30, int(timeout_sec))
    response: dict[str, Any] | None = None
    last_token_refresh = time.monotonic()
    while time.time() < deadline:
        if time.monotonic() - last_token_refresh > 240:
            token = token_factory()
            last_token_refresh = time.monotonic()
        status, raw, _ = api(
            authority_base,
            f"/v1/source-exchange/response/{run_id}",
            method="GET",
            caller_run_id=str(run_id),
            token=token,
        )
        if status == 200:
            wrapper = json.loads(raw.decode("utf-8"))
            if wrapper.get("ok") is not True or not isinstance(wrapper.get("response"), Mapping):
                raise RuntimeError("source_exchange_response_not_ok")
            response = dict(wrapper["response"])
            break
        if status != 404:
            raise RuntimeError(f"source_exchange_response_http_{status}")
        sleep(5)
    if response is None:
        raise RuntimeError("source_exchange_response_timeout")

    response = _validate_manifest(
        response,
        run_id=str(run_id),
        source_ref=source_ref,
        recipient_key_id=recipient_key_id,
    )
    chunk_texts: list[str] = []
    for desc in response["chunks"]:
        index = int(desc["index"])
        status, raw, headers = api(
            authority_base,
            f"/v1/source-exchange/response/{run_id}/chunk/{index}",
            method="GET",
            caller_run_id=str(run_id),
            token=token,
        )
        if status != 200:
            raise RuntimeError(f"source_exchange_chunk_http_{status}:{index}")
        text = raw.decode("ascii")
        header_digest = ""
        for key, value in headers.items():
            if key.lower() == "x-mmibkr-chunk-sha256":
                header_digest = value
                break
        if header_digest and header_digest != str(desc["sha256"]):
            raise RuntimeError("source_exchange_chunk_header_digest_rejected")
        chunk_texts.append(text)

    archive = decrypt_archive(
        response,
        chunk_texts,
        private_key=private,
        run_id=str(run_id),
        source_ref=source_ref,
        recipient_key_id=recipient_key_id,
    )
    source_root = extract_archive(archive, destination)

    cleanup_status, _, _ = api(
        authority_base,
        f"/v1/source-exchange/cleanup/{run_id}",
        method="POST",
        caller_run_id=str(run_id),
        token=token,
        payload={},
    )
    cleanup_ok = cleanup_status == 200

    result = {
        "schema": "mmibkr.cloud_source_materialization.v1",
        "ok": True,
        "run_id": str(run_id),
        "source_ref": source_ref,
        "source_sha": str(response["source_sha"]),
        "source_root": str(source_root),
        "source_archive_sha256": str(response["plaintext_sha256"]),
        "source_archive_bytes": int(response["archive_bytes"]),
        "producer_identity": dict(response["producer_identity"]),
        "source_exchange_cleanup_ok": cleanup_ok,
        "private_repository_token_used": False,
        "broker_credentials_used": False,
        "plaintext_emitted": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(output, 0o600)
    except OSError:
        pass
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-base", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout-sec", type=int, default=900)
    args = parser.parse_args()
    result = consume(
        authority_base=args.authority_base,
        run_id=str(args.run_id),
        source_ref=args.source_ref,
        destination=Path(args.destination),
        output=Path(args.output),
        timeout_sec=args.timeout_sec,
    )
    print(
        "MMIBKR_CLOUD_SOURCE_MATERIALIZED="
        + json.dumps(
            {
                "ok": True,
                "run_id": result["run_id"],
                "source_ref": result["source_ref"],
                "source_sha": result["source_sha"],
                "source_archive_sha256": result["source_archive_sha256"],
                "source_archive_bytes": result["source_archive_bytes"],
                "source_exchange_cleanup_ok": result["source_exchange_cleanup_ok"],
                "private_repository_token_used": False,
                "broker_credentials_used": False,
                "plaintext_emitted": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
