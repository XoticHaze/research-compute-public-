#!/usr/bin/env python3
"""Encrypted live Gateway warm-state envelope for an AUTHORIZED future owner.

This codec has NO broker network logic and NO execution grants. It is deliberately
separate from the existing production-live workflow. Never call it with a paper
password, live password, or low-entropy passphrase as the master key.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

SCHEMA = "mmibkr.live_gateway_warm_state_envelope.v1"
CONTEXT_SCHEMA = "mmibkr.live_gateway_warm_state_context.v1"
MASTER_KEY_ENV = "MMIBKR_LIVE_GATEWAY_WARM_KEY_B64"
MAGIC = b"MMIBKR_LIVE_WARM_V1\x00"
MAX_ARCHIVE_BYTES = 134217728
MAX_MEMBERS = 15000
EXPECTED_IMAGE = "ghcr.io/code-hustler-ft3d/ibg-controller@sha256:5db4074ec952d130937afc3bb926ee97f115d09f7f46676eb16d98c2805572b5"
EXPECTED_SOURCE = "46fcdf26cf84603b305a3ea20bcd3cf28c67bc0b"
HEX40 = re.compile(r"^[a-f0-9]{40}$")
RUN = re.compile(r"^[0-9]{4,24}$")
CONTEXT_FIELDS = {"schema", "run_id", "source_sha", "gateway_image",
                  "admission_only", "orders_allowed", "paper_account"}
ENVELOPE_FIELDS = {"schema", "context", "ciphertext_sha256", "salt_b64",
                   "nonce_b64", "archive_sha256", "archive_bytes"}


class GateError(ValueError):
    pass


def require(condition: bool, name: str):
    if not condition:
        raise GateError(name)


def canonical(node: dict) -> bytes:
    return json.dumps(node, sort_keys=True, separators=(",", ":")).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def context(run_id: str, source_sha=EXPECTED_SOURCE,
            gateway_image=EXPECTED_IMAGE) -> dict:
    require(bool(RUN.fullmatch(str(run_id))), "run_id_invalid")
    require(bool(HEX40.fullmatch(str(source_sha))), "source_sha_invalid")
    require(source_sha == EXPECTED_SOURCE, "source_not_pinned")
    require(gateway_image == EXPECTED_IMAGE, "gateway_image_not_pinned")
    return {
        "schema": CONTEXT_SCHEMA, "run_id": str(run_id),
        "source_sha": source_sha, "gateway_image": gateway_image,
        "admission_only": True, "orders_allowed": False, "paper_account": False,
    }


def validate_context(node: dict):
    require(isinstance(node, dict) and set(node) == CONTEXT_FIELDS,
            "context_fields_not_exact")
    require(node == context(node["run_id"], node["source_sha"],
                            node["gateway_image"]), "context_not_allowed")


def read_master(env=os.environ) -> bytes:
    encoded = env.get(MASTER_KEY_ENV)
    require(isinstance(encoded, str) and bool(encoded),
            "independent_master_key_not_configured")
    try:
        key = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise GateError("master_key_encoding_invalid") from exc
    require(len(key) == 32, "master_key_must_be_32_random_bytes")
    return key


def validate_tar(raw: bytes) -> None:
    require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_ARCHIVE_BYTES,
            "tar_size_out_of_bounds")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            members = archive.getmembers()
            require(0 < len(members) <= MAX_MEMBERS, "tar_members_out_of_bounds")
            total = 0
            for m in members:
                name = m.name
                p = PurePosixPath(name)
                require(bool(name) and not p.is_absolute() and
                        ".." not in p.parts and not name.startswith("./../") and
                        all(x not in ("", ".") for x in p.parts),
                        "tar_unsafe_path")
                require(m.isfile() or m.isdir(), "tar_nonregular_entry")
                require(m.size >= 0, "tar_invalid_member_size")
                total += m.size
                require(total <= MAX_ARCHIVE_BYTES, "tar_total_unpacked_too_large")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise GateError("tar_invalid_archive") from exc


def derive(key: bytes, salt: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=salt, info=b"mmibkr-live-gateway-state-r1").derive(key)


def seal(raw: bytes, ctx: dict, master: bytes) -> tuple[bytes, dict]:
    validate_context(ctx)
    require(len(master) == 32, "master_key_length_invalid")
    validate_tar(raw)
    salt = os.urandom(32)
    nonce = os.urandom(12)
    ciphertext = AESGCM(derive(master, salt)).encrypt(nonce, raw, canonical(ctx))
    blob = MAGIC + salt + nonce + ciphertext
    metadata = {
        "schema": SCHEMA, "context": ctx,
        "ciphertext_sha256": sha(blob),
        "salt_b64": base64.b64encode(salt).decode(),
        "nonce_b64": base64.b64encode(nonce).decode(),
        "archive_sha256": sha(raw),
        "archive_bytes": len(raw),
    }
    return blob, metadata


def unseal(blob: bytes, metadata: dict, master: bytes,
           *, current_run_id: str) -> bytes:
    require(len(master) == 32, "master_key_length_invalid")
    require(isinstance(metadata, dict) and set(metadata) == ENVELOPE_FIELDS,
            "envelope_metadata_not_exact")
    require(metadata.get("schema") == SCHEMA, "envelope_version_invalid")
    ctx = metadata["context"]
    validate_context(ctx)
    require(bool(RUN.fullmatch(str(current_run_id))), "current_run_invalid")
    require(ctx["run_id"] != str(current_run_id), "same_run_not_successor")
    require(isinstance(blob, bytes) and len(blob) >= len(MAGIC) + 32 + 12 + 16
            and len(blob) <= MAX_ARCHIVE_BYTES + len(MAGIC) + 60,
            "ciphertext_size_out_of_bounds")
    require(blob.startswith(MAGIC), "ciphertext_magic_invalid")
    require(metadata["ciphertext_sha256"] == sha(blob),
            "ciphertext_digest_mismatch")
    salt = blob[len(MAGIC):len(MAGIC) + 32]
    nonce = blob[len(MAGIC) + 32:len(MAGIC) + 44]
    require(metadata["salt_b64"] == base64.b64encode(salt).decode() and
            metadata["nonce_b64"] == base64.b64encode(nonce).decode(),
            "envelope_nonce_or_salt_mismatch")
    try:
        raw = AESGCM(derive(master, salt)).decrypt(
            nonce, blob[len(MAGIC) + 44:], canonical(ctx))
    except Exception as exc:
        raise GateError("ciphertext_authentication_failed") from exc
    require(metadata["archive_sha256"] == sha(raw) and
            metadata["archive_bytes"] == len(raw), "archive_digest_mismatch")
    validate_tar(raw)
    return raw


def private_write(path: Path, raw: bytes):
    require(not path.exists(), "refuse_overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as fp:
        fp.write(raw)


def run(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="operation", required=True)
    make = sub.add_parser("seal")
    make.add_argument("--archive", type=Path, required=True)
    make.add_argument("--run-id", required=True)
    make.add_argument("--envelope", type=Path, required=True)
    make.add_argument("--manifest", type=Path, required=True)
    restore = sub.add_parser("unseal")
    restore.add_argument("--envelope", type=Path, required=True)
    restore.add_argument("--manifest", type=Path, required=True)
    restore.add_argument("--current-run-id", required=True)
    restore.add_argument("--output-archive", type=Path, required=True)
    a = parser.parse_args(argv)
    try:
        master = read_master()
        if a.operation == "seal":
            blob, manifest = seal(a.archive.read_bytes(),
                                  context(a.run_id), master)
            private_write(a.envelope, blob)
            private_write(a.manifest, canonical(manifest) + b"\n")
            print("MMIBKR_ENCRYPTED_LIVE_GATEWAY_STATE_CREATED=1")
            print("MMIBKR_WARM_STATE_LIVE_ORDERS_ALLOWED=0")
        else:
            manifest = json.loads(a.manifest.read_text())
            archive = unseal(a.envelope.read_bytes(), manifest, master,
                             current_run_id=a.current_run_id)
            private_write(a.output_archive, archive)
            print("MMIBKR_ENCRYPTED_LIVE_GATEWAY_STATE_RESTORED=1")
            print("MMIBKR_GATEWAY_AUTHENTICATED_SESSION_PROVEN=0")
            print("MMIBKR_EXECUTION_OWNER_GRANTED=0")
        return 0
    except (GateError, OSError, ValueError, TypeError) as exc:
        name = str(exc) if isinstance(exc, GateError) else "invalid_envelope_or_io"
        print("MMIBKR_LIVE_GATEWAY_STATE_FAIL_CLOSED=" + name)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
