"""Chunked encrypted Blender artifact return via EXISTING P-256/AES-GCM capsule.

This is a fixed-output adapter, NOT an independent release signer, ingress
authority, compute executor, nonce ledger or replacement Cloudflare Worker.
The authenticated owning runtime must issue a signed placement and recipient,
consume the encrypted result, verify files, and clean transient plaintext.
"""
from __future__ import annotations

from hashlib import sha256
import io
import json
from pathlib import Path
import re
import zipfile

from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import seal, open_capsule

SCHEMA = "commandcenter.blender_encrypted_artifacts.v1"
EXPECTED = ("arm.blend", "arm.glb", "preview.png", "receipt.json")
CHUNK = 196608
MAX_ZIP = 16 * 1024 * 1024
MAX_CHUNKS = (MAX_ZIP + CHUNK - 1) // CHUNK
MAX_FILE = 16 * 1024 * 1024
RUN_ID = re.compile(r"^[A-Za-z0-9._:-]{6,128}$")


def _write_json(path: Path, node: dict) -> None:
    path.write_text(json.dumps(node, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")


def _check_run(run_id: str) -> None:
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("run_identity_invalid")


def encrypt_artifacts(work_dir: Path, out_dir: Path, *, run_id: str, recipient_public_b64: str) -> dict:
    """Seal fixed known render files and encrypted header; never write plaintext to public Git."""
    _check_run(run_id)
    work = Path(work_dir).resolve()
    out = Path(out_dir).resolve()
    if out == work or work in out.parents or out in work.parents:
        raise ValueError("ciphertext_dir_must_be_separate")
    out.mkdir(parents=True, exist_ok=False)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for name in EXPECTED:
            path = work / name
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_FILE:
                raise ValueError("missing_or_oversize_artifact")
            zipf.write(path, arcname=name)
    data = archive.getvalue()
    if not 0 < len(data) <= MAX_ZIP:
        raise ValueError("encrypted_result_size_limit")
    pieces = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
    if not 1 <= len(pieces) <= MAX_CHUNKS:
        raise ValueError("encrypted_chunk_limit")
    header = {
        "schema": SCHEMA, "run_id": run_id, "archive_sha256": sha256(data).hexdigest(),
        "archive_bytes": len(data), "part_count": len(pieces),
        "expected_files": list(EXPECTED),
    }
    _write_json(out / "header.json", seal(
        json.dumps(header, sort_keys=True, separators=(",", ":")).encode(),
        recipient_public_b64=recipient_public_b64, run_id=run_id + ":header", direction="result"))
    names = []
    for index, piece in enumerate(pieces):
        name = f"part-{index:04d}.json"
        _write_json(out / name, seal(piece, recipient_public_b64=recipient_public_b64,
                                   run_id=run_id + f":part:{index:04d}", direction="result"))
        names.append(name)
    public_manifest = {"schema": SCHEMA, "run_id": run_id,
                       "result_kind": "CIPHERTEXT_ONLY", "header": "header.json",
                       "parts": names}
    _write_json(out / "manifest.json", public_manifest)
    return {"schema": SCHEMA, "status": "SEALED",
            "part_count": len(pieces), "public_plaintext_artifacts": False}


def open_artifacts(encrypted_dir: Path, *, recipient_private_b64: str, run_id: str) -> dict[str, bytes]:
    """Used only by approved PRIVATE result consumer. Returns verified files in memory."""
    _check_run(run_id)
    base = Path(encrypted_dir).resolve()
    manifest = json.loads((base / "manifest.json").read_text())
    if (not isinstance(manifest, dict) or set(manifest) != {"schema", "run_id", "result_kind", "header", "parts"}
        or manifest["schema"] != SCHEMA or manifest["run_id"] != run_id
        or manifest["result_kind"] != "CIPHERTEXT_ONLY" or manifest["header"] != "header.json"):
        raise ValueError("manifest_invalid")
    names = manifest["parts"]
    if not isinstance(names, list) or not 1 <= len(names) <= MAX_CHUNKS or names != [f"part-{i:04d}.json" for i in range(len(names))]:
        raise ValueError("chunk_names_or_count_invalid")
    header = json.loads(open_capsule(
        json.loads((base / "header.json").read_text()),
        recipient_private_b64=recipient_private_b64,
        expected_run_id=run_id + ":header", expected_direction="result"))
    if (not isinstance(header, dict)
        or set(header) != {"schema", "run_id", "archive_sha256", "archive_bytes", "part_count", "expected_files"}
        or header["schema"] != SCHEMA or header["run_id"] != run_id
        or header["part_count"] != len(names) or header["expected_files"] != list(EXPECTED)
        or type(header["archive_bytes"]) is not int or not 0 < header["archive_bytes"] <= MAX_ZIP):
        raise ValueError("private_header_rejected")
    plain = bytearray()
    for index, name in enumerate(names):
        chunk = open_capsule(
            json.loads((base / name).read_text()),
            recipient_private_b64=recipient_private_b64,
            expected_run_id=run_id + f":part:{index:04d}", expected_direction="result")
        if not 0 < len(chunk) <= CHUNK:
            raise ValueError("decrypted_chunk_invalid")
        plain.extend(chunk)
        if len(plain) > MAX_ZIP:
            raise ValueError("decrypted_archive_too_large")
    zipped = bytes(plain)
    if len(zipped) != header["archive_bytes"] or sha256(zipped).hexdigest() != header["archive_sha256"]:
        raise ValueError("decrypted_archive_digest_mismatch")
    files = {}
    with zipfile.ZipFile(io.BytesIO(zipped), "r") as zf:
        if sorted(zf.namelist()) != sorted(EXPECTED):
            raise ValueError("unexpected_files_in_private_result")
        for name in EXPECTED:
            info = zf.getinfo(name)
            if not 0 < info.file_size <= MAX_FILE:
                raise ValueError("bad_private_file_size")
            files[name] = zf.read(name)
    receipt = json.loads(files["receipt.json"])
    if receipt.get("schema") != "commandcenter.blender_probe_result.v1" or receipt.get("status") != "SUCCESS":
        raise ValueError("private_receipt_invalid")
    for name in EXPECTED:
        if name == "receipt.json":
            continue
        actual = files[name]
        meta = receipt.get("files", {}).get(name)
        if (not isinstance(meta, dict) or meta.get("bytes") != len(actual)
            or meta.get("sha256") != sha256(actual).hexdigest()):
            raise ValueError("private_artifact_digest_mismatch")
    return files
