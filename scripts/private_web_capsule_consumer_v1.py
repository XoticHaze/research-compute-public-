#!/usr/bin/env python3
"""Consume a privately approved encrypted web-asset capsule on an OIDC public runner.

Ciphertext may be committed publicly. This client never receives a GitHub
private-repository credential; the exact source approval and one-use key release
belong to the independent Cloudflare Fleet authority, not to this script.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CAPSULE_SCHEMA = "commandcenter.private_web_ciphertext_capsule.v1"
PLAIN_SCHEMA = "commandcenter.private_web_plain_overlay.v1"
REPLY_SCHEMA = "commandcenter.private_web_key_release.v1"
MANIFEST_SCHEMA = "commandcenter.private_web_static_overlay.v1"
SERVICE_PATH = "/v1/source-vault/private-web/unwrap"
AUDIENCE = "mmibkr-fleet-authority"
MAX_CAPSULE = 1_500_000
MAX_PLAIN = 1_000_000
MAX_FILES = 32
MAX_FILE = 512 * 1024
ALLOWED = {".html", ".js", ".css", ".png", ".svg", ".webp", ".ico", ".woff2"}
ID = re.compile(r"[a-z0-9][a-z0-9-]{15,63}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
SOURCE_SHA = re.compile(r"[a-f0-9]{40}\Z")
SLUG = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")


def b64(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("capsule_base64_invalid")
    try:
        return base64.b64decode(value, validate=True)
    except Exception as e:
        raise ValueError("capsule_base64_invalid") from e


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def capsule_input(data: bytes) -> tuple[dict, bytes]:
    if not (0 < len(data) <= MAX_CAPSULE):
        raise ValueError("ciphertext_capsule_size_rejected")
    try:
        c = json.loads(data)
    except (ValueError, UnicodeError) as e:
        raise ValueError("ciphertext_capsule_json_invalid") from e
    expected = {"schema", "capsule_id", "cipher", "key_id", "nonce_b64",
                "aad_b64", "sealed_key_b64", "ciphertext_b64", "ciphertext_sha256"}
    if not isinstance(c, dict) or set(c) != expected or c.get("schema") != CAPSULE_SCHEMA:
        raise ValueError("ciphertext_capsule_contract_rejected")
    if not ID.fullmatch(c["capsule_id"]) or c["cipher"] != "AES-256-GCM+RSA-OAEP-256":
        raise ValueError("ciphertext_capsule_identity_rejected")
    if not isinstance(c["key_id"], str) or not c["key_id"].startswith("sha256:"):
        raise ValueError("ciphertext_capsule_key_id_rejected")
    nonce, aad, sealed = b64(c["nonce_b64"]), b64(c["aad_b64"]), b64(c["sealed_key_b64"])
    if len(nonce) != 12 or len(aad) > 256 or len(sealed) < 128 or len(sealed) > 1024:
        raise ValueError("ciphertext_capsule_crypto_fields_rejected")
    expected_aad = (CAPSULE_SCHEMA + "|" + c["capsule_id"]).encode()
    if aad != expected_aad:
        raise ValueError("ciphertext_capsule_aad_rejected")
    cipher = b64(c["ciphertext_b64"])
    if not (16 < len(cipher) <= MAX_PLAIN + 16) or not SHA.fullmatch(c["ciphertext_sha256"]):
        raise ValueError("ciphertext_capsule_digest_or_size_rejected")
    if sha256(cipher) != c["ciphertext_sha256"]:
        raise ValueError("ciphertext_capsule_tampered")
    return c, cipher


def github_oidc() -> str:
    url = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL") or "")
    token = str(os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN") or "")
    if not url or not token:
        raise RuntimeError("github_oidc_environment_missing")
    u = urlparse(url)
    # GitHub-hosted regional OIDC issuers include pipeline-specific subdomains.
    # Match DNS label boundary, never a substring, suffix lookalike or userinfo.
    host = (u.hostname or "").lower()
    if (u.scheme != "https" or not (
            host == "actions.githubusercontent.com"
            or host.endswith(".actions.githubusercontent.com"))
            or u.username is not None or u.password is not None
            or u.port not in (None, 443)):
        raise RuntimeError("github_oidc_url_rejected")
    query = dict(parse_qsl(u.query, keep_blank_values=True))
    query["audience"] = AUDIENCE
    url = urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(query), ""))
    req = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urlopen(req, timeout=20) as res:
        jwt = str(json.load(res).get("value") or "")
    if jwt.count(".") != 2:
        raise RuntimeError("github_oidc_token_rejected")
    return jwt


def cloudflare_key_release(c: dict, *, base: str, run_id: str, token: str) -> dict:
    u = urlparse(base)
    if u.scheme != "https" or not u.hostname or u.path.strip("/") or u.query or u.fragment:
        raise ValueError("authority_origin_invalid")
    if not re.fullmatch(r"\d{4,24}", str(run_id)):
        raise ValueError("run_id_rejected")
    body = json.dumps({
        "schema": CAPSULE_SCHEMA, "capsule_id": c["capsule_id"],
        "ciphertext_sha256": c["ciphertext_sha256"], "key_id": c["key_id"],
        "sealed_key_b64": c["sealed_key_b64"],
    }, separators=(",", ":"), sort_keys=True).encode()
    req = Request(
        base.rstrip("/") + SERVICE_PATH, method="POST", data=body,
        headers={"Authorization": "Bearer " + token,
                 "X-MMIBKR-Caller-Run-Id": str(run_id),
                 "Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "cc-private-web-opaque-consumer-v1"},
    )
    with urlopen(req, timeout=30) as res:
        if res.status != 200:
            raise RuntimeError("private_web_key_release_denied")
        out = json.load(res)
    if (not isinstance(out, dict) or out.get("schema") != REPLY_SCHEMA
            or out.get("approved") is not True or out.get("ok") is not True
            or out.get("capsule_id") != c["capsule_id"]
            or out.get("ciphertext_sha256") != c["ciphertext_sha256"]
            or out.get("run_id") != str(run_id)
            or out.get("private_source_token_exposed") is not False
            or out.get("broker_mutation_authority") is not False):
        raise RuntimeError("private_web_key_release_identity_mismatch")
    return out


def materialize(c: dict, cipher: bytes, grant: dict, *, destination: Path, receipt: Path) -> dict:
    key = b64(grant.get("master_key_b64"))
    if len(key) != 32:
        raise RuntimeError("private_web_key_invalid")
    try:
        plain = AESGCM(key).decrypt(b64(c["nonce_b64"]), cipher, b64(c["aad_b64"]))
    except Exception as e:
        raise RuntimeError("private_web_capsule_decrypt_rejected") from e
    if len(plain) > MAX_PLAIN:
        raise RuntimeError("private_web_plain_size_rejected")
    try:
        data = json.loads(plain)
    except (UnicodeError, ValueError) as e:
        raise RuntimeError("private_web_plain_contract_rejected") from e
    if not isinstance(data, dict) or set(data) != {
            "schema", "app_slug", "source_sha", "files", "source_pin_verified"
    } or data.get("schema") != PLAIN_SCHEMA or data.get("source_pin_verified") is not True:
        raise RuntimeError("private_web_plain_contract_rejected")
    slug, source_sha, files = data["app_slug"], data["source_sha"], data["files"]
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise RuntimeError("private_web_slug_rejected")
    if not isinstance(source_sha, str) or not SOURCE_SHA.fullmatch(source_sha):
        raise RuntimeError("private_web_source_identity_rejected")
    if not isinstance(files, dict) or not (1 <= len(files) <= MAX_FILES):
        raise RuntimeError("private_web_file_inventory_rejected")
    manifest_path = destination.parent / (destination.name + ".manifest.json")
    if destination.exists() or receipt.exists() or manifest_path.exists():
        raise RuntimeError("private_web_output_must_be_new")
    manifest_assets = {}
    validated = {}
    for rel, row in files.items():
        if not isinstance(rel, str) or not rel.startswith("assets/" + slug + "/"):
            raise RuntimeError("private_web_asset_path_rejected")
        path = PurePosixPath(rel)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 3 or path.suffix not in ALLOWED:
            raise RuntimeError("private_web_asset_path_rejected")
        if not isinstance(row, dict) or set(row) != {"sha256", "data_b64"}:
            raise RuntimeError("private_web_asset_contract_rejected")
        raw = b64(row["data_b64"])
        if not raw or len(raw) > MAX_FILE or row["sha256"] != sha256(raw):
            raise RuntimeError("private_web_asset_digest_rejected")
        manifest_assets["/" + rel] = row["sha256"]
        validated[rel] = raw
    if "assets/" + slug + "/index.html" not in validated:
        raise RuntimeError("private_web_entrypoint_missing")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for rel, raw in validated.items():
            file = destination / rel
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
            os.chmod(file, 0o600)
        manifest = {
            "schema": MANIFEST_SCHEMA, "release_state": "STAGED_NOT_DEPLOYED",
            "source_sha_claim": source_sha, "source_sha_independently_verified": True,
            "app_slug": slug, "assets": manifest_assets,
            "no_public_plaintext_source": True, "access_served_verified": False,
            "oidc_release_grant_verified": True,
        }
        # Composer requires asset-only root. The private manifest is separate.
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        os.chmod(manifest_path, 0o600)
        record = {
            "schema": "commandcenter.private_web_release_materialization.v1",
            "state": "MATERIALIZED_NOT_DEPLOYED", "capsule_id": c["capsule_id"],
            "ciphertext_sha256": c["ciphertext_sha256"], "app_slug": slug,
            "asset_count": len(validated), "source_pin_private": True,
            "oidc_release_grant_verified": True, "access_served_verified": False,
            "private_source_published_to_public_git": False,
        }
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
        os.chmod(receipt, 0o600)
        return record
    except BaseException:
        import shutil
        shutil.rmtree(destination, ignore_errors=True)
        raise


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capsule", type=Path, required=True)
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--authority-base", default="https://fleet-authority.slenderiq.workers.dev")
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    c, cipher = capsule_input(args.capsule.read_bytes())
    grant = cloudflare_key_release(c, base=args.authority_base,
                                   run_id=args.run_id, token=github_oidc())
    result = materialize(c, cipher, grant, destination=args.destination, receipt=args.receipt)
    print("CC_PRIVATE_WEB_CAPSULE=" + result["state"])
    print("CC_PRIVATE_WEB_CAPSULE_FILES=" + str(result["asset_count"]))


if __name__ == "__main__":
    main()
