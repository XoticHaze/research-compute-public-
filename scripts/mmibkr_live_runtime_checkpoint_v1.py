#!/usr/bin/env python3
"""Sealed broker-state + canonical bot-data checkpoint, never an order grant.

Live successors must separately authenticate the exact broker account and
reconcile broker orders, executions, positions, and canonical owner state.
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
from mmibkr_live_gateway_state_envelope_v1 import read_master, derive

SCHEMA = "mmibkr.live_runtime_checkpoint.v1"
CONTEXT_SCHEMA = "mmibkr.live_runtime_checkpoint_context.v1"
MAGIC = b"MMIBKR_LIVE_RUNTIME_V1\x00"
SOURCE_SHA = "46fcdf26cf84603b305a3ea20bcd3cf28c67bc0b"
IMAGE = "ghcr.io/code-hustler-ft3d/ibg-controller@sha256:2e4f4911991386e941f6e95d58ee38a8242474dd3be239f21ad82557d24b4368"
MAX_BYTES = 512 * 1024 * 1024
RUN_ID = re.compile(r"^[0-9]{4,24}$")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(node: dict) -> bytes:
    return json.dumps(node, sort_keys=True, separators=(",", ":")).encode()


def context(run_id: str) -> dict:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("producer_run_invalid")
    return {
        "schema": CONTEXT_SCHEMA,
        "run_id": run_id,
        "source_sha": SOURCE_SHA,
        "gateway_image": IMAGE,
        "scope": ["AMAT", "APH", "MNQ"],
        "checkpoint_type": "gateway_and_canonical_bot_data",
        "order_authority": "none_checkpoint_requires_fresh_canonical_admission",
    }


def check_archive(raw: bytes) -> None:
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("archive_size_invalid")
    seen_gateway = False
    seen_data = False
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        members = archive.getmembers()
        if not 0 < len(members) <= 250000:
            raise ValueError("archive_member_count_invalid")
        for m in members:
            p = PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts or not (m.isfile() or m.isdir()):
                raise ValueError("unsafe_archive_member")
            if p.parts and p.parts[0] == "gateway":
                seen_gateway = True
            elif p.parts and p.parts[0] == "bot_data":
                seen_data = True
            else:
                raise ValueError("unexpected_archive_root")
            total += m.size
            if total > MAX_BYTES:
                raise ValueError("uncompressed_archive_too_large")
    if not seen_gateway or not seen_data:
        raise ValueError("checkpoint_missing_required_tree")


def seal(raw: bytes, producer_run: str, key: bytes) -> tuple[bytes, dict]:
    check_archive(raw)
    ctx = context(producer_run)
    if len(key) != 32:
        raise ValueError("key_length_invalid")
    salt = os.urandom(32)
    nonce = os.urandom(12)
    encrypted = AESGCM(derive(key, salt)).encrypt(nonce, raw, canonical(ctx))
    blob = MAGIC + salt + nonce + encrypted
    return blob, {
        "schema": SCHEMA, "context": ctx,
        "ciphertext_sha256": digest(blob), "archive_sha256": digest(raw),
        "ciphertext_bytes": len(blob),
    }


def unseal(blob: bytes, manifest: dict, successor_run: str, key: bytes) -> bytes:
    if set(manifest) != {"schema", "context", "ciphertext_sha256", "archive_sha256", "ciphertext_bytes"}:
        raise ValueError("manifest_fields_invalid")
    ctx = manifest["context"]
    if (manifest["schema"] != SCHEMA or not isinstance(ctx, dict) or
            ctx != context(ctx.get("run_id", "")) or
            not RUN_ID.fullmatch(successor_run) or ctx["run_id"] == successor_run):
        raise ValueError("invalid_successor_context")
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 60:
        raise ValueError("ciphertext_header_invalid")
    if manifest["ciphertext_bytes"] != len(blob) or manifest["ciphertext_sha256"] != digest(blob):
        raise ValueError("ciphertext_integrity_invalid")
    if len(key) != 32:
        raise ValueError("key_length_invalid")
    salt = blob[len(MAGIC):len(MAGIC) + 32]
    nonce = blob[len(MAGIC) + 32:len(MAGIC) + 44]
    try:
        raw = AESGCM(derive(key, salt)).decrypt(nonce, blob[len(MAGIC) + 44:], canonical(ctx))
    except Exception as exc:
        raise ValueError("ciphertext_authentication_failed") from exc
    if manifest["archive_sha256"] != digest(raw):
        raise ValueError("archive_integrity_invalid")
    check_archive(raw)
    return raw


def main() -> None:
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="action", required=True)
    a = sp.add_parser("seal")
    a.add_argument("--archive", required=True)
    a.add_argument("--producer-run", required=True)
    a.add_argument("--envelope", required=True)
    a.add_argument("--manifest", required=True)
    a = sp.add_parser("unseal")
    a.add_argument("--envelope", required=True)
    a.add_argument("--manifest", required=True)
    a.add_argument("--successor-run", required=True)
    a.add_argument("--archive", required=True)
    args = p.parse_args()
    key = read_master()
    if args.action == "seal":
        blob, meta = seal(Path(args.archive).read_bytes(), args.producer_run, key)
        for path, raw in [(args.envelope, blob), (args.manifest, canonical(meta))]:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o600)
        print("LIVE_RUNTIME_ENCRYPTED_CHECKPOINT=PASS")
    else:
        raw = unseal(Path(args.envelope).read_bytes(),
                     json.loads(Path(args.manifest).read_text()),
                     args.successor_run, key)
        target = Path(args.archive)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o600)
        print("LIVE_RUNTIME_SUCCESSOR_CHECKPOINT_DECRYPTED=PASS")


if __name__ == "__main__":
    main()
