"""Canonical encrypted-source capsule sender for existing neutral public rendezvous.

Run only in a PRIVATE producer context that already holds the canonical source.
No Github/Cloudflare credential or API connection. Only the versioned P-256
ciphertext envelope may be published; no plaintext archive is written to disk.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

from commandcenter_neutral_gate_ephemeral_consumer_v1 import (
    EXPECTED_GIT_BLOBS, POLICY_ONLY_FILES, MANIFEST_SCHEMA, HARNESS,
    MAX_ARCHIVE, _git_blob,
)
from opaque_bidirectional_capsule_p256_aesgcm_v1 import (
    FIELDS as CANONICAL_FIELDS, seal,
)


class ProducerRejected(ValueError):
    pass


def _read_private(root: Path, name: str) -> bytes:
    # Files must be real, regular, inside the private checkout and not symlinked.
    if root.is_symlink() or not root.is_dir():
        raise ProducerRejected("private_source_root_rejected")
    target = root / name
    current = target
    while current != root:
        if current.is_symlink():
            raise ProducerRejected("private_source_symlink_rejected")
        current = current.parent
    if not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
        raise ProducerRejected("private_source_missing")
    data = target.read_bytes()
    if not 0 < len(data) <= 80_000:
        raise ProducerRejected("private_source_size_rejected")
    if _git_blob(data) != EXPECTED_GIT_BLOBS[name]:
        raise ProducerRejected("immutable_source_blob_rejected")
    return data


def _archive_private(root: Path, suite: str) -> bytes:
    if suite not in {"policy", "full"}:
        raise ProducerRejected("unknown_bounded_suite")
    names = POLICY_ONLY_FILES if suite == "policy" else set(EXPECTED_GIT_BLOBS)
    members = {name: _read_private(root, name) for name in sorted(names)}
    manifest = {
        "schema": MANIFEST_SCHEMA, "harness": HARNESS,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in members.items()},
    }
    members["payload-manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, content in sorted(members.items()):
            member = tarfile.TarInfo(name=name)
            member.size = len(content)
            member.mtime = 0
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(content))
    if len(output.getvalue()) > MAX_ARCHIVE:
        raise ProducerRejected("encrypted_payload_size_rejected")
    return output.getvalue()


def produce(private_root: Path, offer: dict, *, run_id: str, suite: str = "policy") -> dict:
    # Preserve the existing one-run rendezvous identity; never use ambient
    # public workflow or source identity as the authorization proof.
    if not str(run_id).isdigit() or offer.get("schema") != "commandcenter-ledger-ephemeral-recipient-v1":
        raise ProducerRejected("public_offer_schema_rejected")
    if str(offer.get("run_id")) != str(run_id):
        raise ProducerRejected("public_offer_run_rejected")
    public_key = offer.get("canonical_recipient_b64")
    key_id = offer.get("canonical_recipient_key_id")
    if not isinstance(public_key, str) or not isinstance(key_id, str):
        raise ProducerRejected("canonical_offer_missing")
    try:
        raw = base64.b64decode(public_key, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ProducerRejected("canonical_offer_key_malformed") from exc
    if key_id != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ProducerRejected("canonical_offer_key_id_rejected")
    content = _archive_private(private_root, suite)
    envelope = seal(content, recipient_public_b64=public_key, run_id=str(run_id), direction="request")
    if set(envelope) != CANONICAL_FIELDS or "plaintext_sha256" in envelope:
        raise ProducerRejected("outer_metadata_policy_rejected")
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(description="Create only a canonical encrypted neutral policy capsule")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--public-offer", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--suite", choices=("policy", "full"), default="policy")
    parser.add_argument("--encrypted-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        offer = json.loads(args.public_offer.read_text(encoding="utf-8"))
        encrypted = produce(args.private_root, offer, run_id=args.run_id, suite=args.suite)
        # Exclusive creation and private mode prevent overwrite/symlink races.
        fd = os.open(args.encrypted_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(encrypted, output, separators=(",", ":"), sort_keys=True)
            output.write("\n")
        print("NEUTRAL_CANONICAL_CAPSULE=ENCRYPTED_ONLY")
        return 0
    except (ProducerRejected, OSError, ValueError, TypeError):
        print("NEUTRAL_CANONICAL_CAPSULE=FAIL_CLOSED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
