from __future__ import annotations

"""Materialize an approved encrypted MM-IBKR source snapshot from the public vault branch."""

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

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AUDIENCE = "mmibkr-fleet-authority"
MANIFEST_SCHEMA = "mmibkr-source-vault-snapshot-v1"
UNWRAP_SCHEMA = "mmibkr-source-vault-unwrap-v2"
DEFAULT_AUTHORITY_BASE = "https://fleet-authority.slenderiq.workers.dev"
DEFAULT_PUBLIC_REPO = "XoticHaze/mm-ibkr-runtime"
DEFAULT_PUBLIC_BRANCH = "mmibkr-source-vault"
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
MAX_FILES = 20000


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_sha40(value: str) -> str:
    value = str(value or "").strip().lower()
    if len(value) != 40 or any(ch not in "0123456789abcdef" for ch in value):
        raise RuntimeError("exact_source_sha_required")
    return value


def _raw_url(repo: str, branch: str, path: str) -> str:
    owner, name = repo.split("/", 1)
    return f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/{path}"


def _fetch(
    url: str,
    *,
    timeout: int = 30,
    retry_404: int = 6,
    retry_delay_sec: float = 1.0,
) -> bytes:
    req = Request(url, headers={"User-Agent": "mmibkr-source-vault-consumer-v1"})
    attempts = max(1, int(retry_404) + 1)
    for attempt in range(attempts):
        try:
            with urlopen(req, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404 and attempt + 1 < attempts:
                time.sleep(max(0.0, float(retry_delay_sec)))
                continue
            raise RuntimeError(f"snapshot_fetch_http_{exc.code}") from exc
    raise RuntimeError("snapshot_fetch_retry_exhausted")


def _oidc_url(base: str) -> str:
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["audience"] = AUDIENCE
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))


def _oidc_token() -> str:
    url = str(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL") or "")
    token = str(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN") or "")
    if not url or not token:
        raise RuntimeError("github_oidc_environment_missing")
    req = Request(_oidc_url(url), headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        node = json.load(response)
    value = str(node.get("value") or "")
    if value.count(".") != 2:
        raise RuntimeError("github_oidc_token_invalid")
    return value


def _unwrap_api(authority_base: str, run_id: str, token: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    req = Request(
        authority_base.rstrip("/") + "/v1/source-vault/unwrap",
        data=json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-MMIBKR-Caller-Run-Id": str(run_id),
            "User-Agent": "mmibkr-source-vault-consumer-v1",
        },
    )
    try:
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"source_vault_unwrap_http_{exc.code}:{detail[:300]}") from exc


def _validate_manifest(node: Mapping[str, Any], *, source_sha: str) -> dict[str, Any]:
    if not isinstance(node, Mapping) or node.get("schema") != MANIFEST_SCHEMA:
        raise RuntimeError("source_vault_manifest_schema_rejected")
    if str(node.get("source_sha") or "").lower() != source_sha:
        raise RuntimeError("source_vault_manifest_source_sha_rejected")
    for field in ("archive_sha256", "ciphertext_sha256"):
        value = str(node.get(field) or "").lower()
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise RuntimeError(f"source_vault_manifest_{field}_rejected")
    archive_bytes = int(node.get("archive_bytes") or 0)
    ciphertext_bytes = int(node.get("ciphertext_bytes") or 0)
    if archive_bytes <= 0 or archive_bytes > MAX_ARCHIVE_BYTES:
        raise RuntimeError("source_vault_archive_size_rejected")
    if ciphertext_bytes <= archive_bytes or ciphertext_bytes > MAX_ARCHIVE_BYTES + 64:
        raise RuntimeError("source_vault_ciphertext_size_rejected")
    if node.get("cipher") != "AES-256-GCM" or node.get("key_wrap") != "RSA-OAEP-256" or node.get("encoding") != "base64":
        raise RuntimeError("source_vault_crypto_contract_rejected")
    if node.get("public_plaintext_included") is not False or node.get("private_repository_token_used") is not False:
        raise RuntimeError("source_vault_publication_boundary_rejected")
    chunks = node.get("chunks")
    if not isinstance(chunks, list) or not chunks or len(chunks) > 4096:
        raise RuntimeError("source_vault_chunk_manifest_rejected")
    prefix = f"source-vault/{source_sha}/"
    for index, desc in enumerate(chunks):
        if not isinstance(desc, Mapping) or int(desc.get("index", -1)) != index:
            raise RuntimeError("source_vault_chunk_descriptor_rejected")
        path = str(desc.get("path") or "")
        digest = str(desc.get("sha256") or "")
        if not path.startswith(prefix) or ".." in Path(path).parts or not path.endswith(".txt"):
            raise RuntimeError("source_vault_chunk_path_rejected")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise RuntimeError("source_vault_chunk_digest_rejected")
        if int(desc.get("chars") or 0) <= 0 or int(desc.get("chars") or 0) > 8 * 1024 * 1024:
            raise RuntimeError("source_vault_chunk_chars_rejected")
    return dict(node)


def _safe_extract(archive: bytes, destination: Path) -> Path:
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

        top_parts: set[str] = set()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise RuntimeError("source_archive_path_rejected")
            top_parts.add(path.parts[0])
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("source_archive_special_member_rejected")
        if len(top_parts) != 1:
            raise RuntimeError("source_archive_single_root_required")

        root.mkdir(parents=True, exist_ok=True)
        for member in members:
            path = Path(member.name)
            if len(path.parts) == 1:
                continue
            relative = Path(*path.parts[1:])
            target = (root / relative).resolve()
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


def materialize(
    *,
    source_sha: str,
    destination: Path,
    archive_output: Path,
    output: Path,
    authority_base: str = DEFAULT_AUTHORITY_BASE,
    public_repo: str = DEFAULT_PUBLIC_REPO,
    public_branch: str = DEFAULT_PUBLIC_BRANCH,
    run_id: str,
    fetch: Callable[[str], bytes] = _fetch,
    token_factory: Callable[[], str] = _oidc_token,
    unwrap_api: Callable[[str, str, str, Mapping[str, Any]], dict[str, Any]] = _unwrap_api,
) -> dict[str, Any]:
    source_sha = _valid_sha40(source_sha)
    if not str(run_id).isdigit():
        raise RuntimeError("run_id_rejected")
    manifest_path = f"source-vault/{source_sha}/manifest.json"
    manifest_raw = fetch(_raw_url(public_repo, public_branch, manifest_path))
    manifest_sha = _sha256(manifest_raw)
    try:
        manifest_node = json.loads(manifest_raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("source_vault_manifest_json_rejected") from exc
    manifest = _validate_manifest(manifest_node, source_sha=source_sha)

    parts: list[str] = []
    for desc in manifest["chunks"]:
        raw = fetch(_raw_url(public_repo, public_branch, str(desc["path"])))
        if len(raw) != int(desc["chars"]) or _sha256(raw) != str(desc["sha256"]):
            raise RuntimeError("source_vault_chunk_integrity_rejected")
        parts.append(raw.decode("ascii"))
    try:
        ciphertext = base64.b64decode("".join(parts).encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("source_vault_ciphertext_base64_rejected") from exc
    if len(ciphertext) != int(manifest["ciphertext_bytes"]) or _sha256(ciphertext) != manifest["ciphertext_sha256"]:
        raise RuntimeError("source_vault_ciphertext_integrity_rejected")

    token = token_factory()
    unwrap = unwrap_api(
        authority_base,
        str(run_id),
        token,
        {
            "schema": UNWRAP_SCHEMA,
            "source_sha": source_sha,
            "manifest_sha256": manifest_sha,
            "archive_sha256": manifest["archive_sha256"],
            "archive_bytes": int(manifest["archive_bytes"]),
            "key_id": manifest["key_id"],
            "sealed_key_b64": manifest["sealed_key_b64"],
        },
    )
    if unwrap.get("ok") is not True or unwrap.get("approved") is not True:
        raise RuntimeError("source_vault_unwrap_not_approved")
    if str(unwrap.get("source_sha") or "") != source_sha or str(unwrap.get("manifest_sha256") or "") != manifest_sha:
        raise RuntimeError("source_vault_unwrap_identity_rejected")
    if str(unwrap.get("archive_sha256") or "") != manifest["archive_sha256"] or int(unwrap.get("archive_bytes") or 0) != int(manifest["archive_bytes"]):
        raise RuntimeError("source_vault_unwrap_archive_identity_rejected")
    try:
        master_key = base64.b64decode(str(unwrap.get("master_key_b64") or "").encode("ascii"), validate=True)
        nonce = base64.b64decode(str(manifest["nonce_b64"]).encode("ascii"), validate=True)
        aad = base64.b64decode(str(manifest["aad_b64"]).encode("ascii"), validate=True)
    except Exception as exc:
        raise RuntimeError("source_vault_decryption_material_rejected") from exc
    if len(master_key) != 32 or len(nonce) != 12:
        raise RuntimeError("source_vault_decryption_material_size_rejected")
    archive = AESGCM(master_key).decrypt(nonce, ciphertext, aad)
    if len(archive) != int(manifest["archive_bytes"]) or _sha256(archive) != manifest["archive_sha256"]:
        raise RuntimeError("source_vault_plaintext_integrity_rejected")

    source_root = _safe_extract(archive, destination)
    archive_output.parent.mkdir(parents=True, exist_ok=True)
    archive_output.write_bytes(archive)
    try:
        os.chmod(archive_output, 0o600)
    except OSError:
        pass
    result = {
        "schema": "mmibkr.attested_source_materialization.v2",
        "ok": True,
        "source_ref": str(manifest.get("source_ref") or source_sha),
        "source_sha": source_sha,
        "source_archive_sha256": manifest["archive_sha256"],
        "source_archive_bytes": int(manifest["archive_bytes"]),
        "source_archive_path": str(archive_output),
        "source_root": str(source_root),
        "source_manifest_sha256": manifest_sha,
        "source_transport": "fleet_authority_exact_sha_encrypted_snapshot_vault",
        "fleet_authority_base": authority_base,
        "caller_run_id": str(run_id),
        "vault_attestation_verified": unwrap.get("reusable_attestation_stored") is True,
        "private_repository_token_used": False,
        "broker_credentials_used": False,
        "plaintext_emitted": False,
        "live_execution_allowed": False,
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
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--archive-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--authority-base", default=DEFAULT_AUTHORITY_BASE)
    parser.add_argument("--public-repo", default=DEFAULT_PUBLIC_REPO)
    parser.add_argument("--public-branch", default=DEFAULT_PUBLIC_BRANCH)
    args = parser.parse_args()
    result = materialize(
        source_sha=args.source_sha,
        destination=args.destination,
        archive_output=args.archive_output,
        output=args.output,
        authority_base=args.authority_base,
        public_repo=args.public_repo,
        public_branch=args.public_branch,
        run_id=str(args.run_id),
    )
    print("MMIBKR_SOURCE_VAULT_MATERIALIZED=" + json.dumps({
        "ok": True,
        "source_sha": result["source_sha"],
        "source_archive_sha256": result["source_archive_sha256"],
        "source_archive_bytes": result["source_archive_bytes"],
        "source_manifest_sha256": result["source_manifest_sha256"],
        "vault_attestation_verified": result["vault_attestation_verified"],
        "private_repository_token_used": False,
        "plaintext_emitted": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
