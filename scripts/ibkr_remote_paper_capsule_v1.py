from __future__ import annotations

"""Decrypt and materialize one remote MM-IBKR paper-runtime capsule.

The public repository owns only this fixed consumer. MM-IBKR source and broker
credentials arrive through the run-bound encrypted envelope, live only in
RUNNER_TEMP, and are never printed. The consumer defaults to a broker/session
reconciliation posture; paper submit is an explicit capsule mode with mandatory
exact-order cancel + zero-baseline flatten cleanup guards.
"""

import argparse
import json
import os
import re
import tarfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext, sha256_bytes

ENVELOPE_SCHEMA = "ibkr-remote-paper-runtime-x25519-v1"
CAPSULE_SCHEMA = "mm-ibkr-remote-paper-capsule-v1"
HARNESS = "mm_ibkr_remote_paper_runtime_v1"
AUTHORITY = "mm_ibkr_paper_runtime"
SOURCE_REPOSITORY = "XoticHaze/mm-IBKR"
SOURCE_PREFIX = "/repos/XoticHaze/mm-IBKR/tarball/"
ALLOWED_MODES = {"session_reconcile", "paper_submit_proof"}
MAX_SOURCE_ARCHIVE_BYTES = 350_000_000
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
CAPSULE_FIELDS = {"schema", "mode", "source", "ibkr", "request", "cleanup"}
SOURCE_FIELDS = {"repository", "head", "archive_url", "archive_sha256", "authorization_bearer"}
IBKR_FIELDS = {"username", "password", "trading_mode"}
CLEANUP_FIELDS = {"cancel_open_order", "flatten_filled_position", "require_zero_baseline", "allow_global_cancel"}


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "live"}


def _reject_live_authority(value: object, path: str = "request") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower()
            child_path = f"{path}.{raw_key}"
            if key in {"enable_live_trading", "live_submit_enabled", "live_allowed", "live_mode_enabled"} and _is_truthy(child):
                raise RuntimeError(f"live authority rejected at {child_path}")
            if key in {"trading_mode", "mode", "account_mode"} and str(child or "").strip().lower() == "live":
                raise RuntimeError(f"live mode rejected at {child_path}")
            _reject_live_authority(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_live_authority(child, f"{path}[{index}]")


def _validate_source(source: object) -> dict:
    if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
        raise RuntimeError("source ticket field set mismatch")
    if source.get("repository") != SOURCE_REPOSITORY:
        raise RuntimeError("source repository mismatch")
    head = str(source.get("head") or "").strip().lower()
    digest = str(source.get("archive_sha256") or "").strip().lower()
    token = str(source.get("authorization_bearer") or "").strip()
    if not SHA40.fullmatch(head):
        raise RuntimeError("source head must be an exact 40-char git SHA")
    if not SHA64.fullmatch(digest):
        raise RuntimeError("source archive sha256 invalid")
    if len(token) < 16 or any(ch.isspace() for ch in token):
        raise RuntimeError("source authorization capability invalid")
    parsed = urlparse(str(source.get("archive_url") or ""))
    if parsed.scheme != "https" or parsed.hostname != "api.github.com" or parsed.query or parsed.fragment:
        raise RuntimeError("source archive URL rejected")
    if not parsed.path.startswith(SOURCE_PREFIX) or parsed.path != SOURCE_PREFIX + head:
        raise RuntimeError("source archive URL/head mismatch")
    return {
        "repository": SOURCE_REPOSITORY,
        "head": head,
        "archive_url": parsed.geturl(),
        "archive_sha256": digest,
        "authorization_bearer": token,
    }


def _validate_ibkr(node: object) -> dict:
    if not isinstance(node, dict) or set(node) != IBKR_FIELDS:
        raise RuntimeError("ibkr credential field set mismatch")
    username = str(node.get("username") or "").strip()
    password = str(node.get("password") or "")
    trading_mode = str(node.get("trading_mode") or "").strip().lower()
    if not username or not password:
        raise RuntimeError("IBKR username/password required")
    if trading_mode != "paper":
        raise RuntimeError("only IBKR paper trading_mode is admitted")
    return {"username": username, "password": password, "trading_mode": "paper"}


def _validate_cleanup(node: object, *, mode: str) -> dict:
    if not isinstance(node, dict) or set(node) != CLEANUP_FIELDS:
        raise RuntimeError("cleanup contract field set mismatch")
    result = {key: bool(node.get(key)) for key in CLEANUP_FIELDS}
    if result["allow_global_cancel"]:
        raise RuntimeError("global cancel is prohibited for remote paper proof")
    if mode == "paper_submit_proof":
        if not result["cancel_open_order"]:
            raise RuntimeError("paper submit proof requires exact-order cancel cleanup")
        if not result["flatten_filled_position"]:
            raise RuntimeError("paper submit proof requires filled-position cleanup")
        if not result["require_zero_baseline"]:
            raise RuntimeError("paper submit proof requires zero baseline position/open-order scope")
    return result


def validate_capsule(raw: bytes) -> dict:
    try:
        capsule = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("capsule is not valid UTF-8 JSON") from exc
    if not isinstance(capsule, dict) or set(capsule) != CAPSULE_FIELDS:
        raise RuntimeError("capsule field set mismatch")
    if capsule.get("schema") != CAPSULE_SCHEMA:
        raise RuntimeError("capsule schema mismatch")
    mode = str(capsule.get("mode") or "").strip()
    if mode not in ALLOWED_MODES:
        raise RuntimeError("unsupported remote paper runtime mode")
    source = _validate_source(capsule.get("source"))
    ibkr = _validate_ibkr(capsule.get("ibkr"))
    request = capsule.get("request")
    if not isinstance(request, dict):
        raise RuntimeError("request must be a JSON object")
    _reject_live_authority(request)
    cleanup = _validate_cleanup(capsule.get("cleanup"), mode=mode)

    if mode == "session_reconcile" and request:
        raise RuntimeError("session_reconcile request must be empty")
    if mode == "paper_submit_proof":
        payload = request.get("canonical_submit_payload")
        if not isinstance(payload, dict) or not payload:
            raise RuntimeError("paper_submit_proof requires canonical_submit_payload")
        symbol = str(payload.get("symbol") or "").strip().upper()
        if not symbol or len(symbol) > 20 or not re.fullmatch(r"[A-Z0-9.!_-]+", symbol):
            raise RuntimeError("paper submit proof symbol invalid")
        request = dict(request)
        request["symbol"] = symbol
    return {
        "schema": CAPSULE_SCHEMA,
        "mode": mode,
        "source": source,
        "ibkr": ibkr,
        "request": request,
        "cleanup": cleanup,
    }


def _fetch_source(source: dict) -> bytes:
    req = Request(
        source["archive_url"],
        headers={
            "Authorization": "Bearer " + source["authorization_bearer"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mm-ibkr-remote-paper-runtime/1",
        },
    )
    chunks: list[bytes] = []
    total = 0
    with urlopen(req, timeout=90) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in {"api.github.com", "codeload.github.com"}:
            raise RuntimeError("source archive redirect host rejected")
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_SOURCE_ARCHIVE_BYTES:
                raise RuntimeError("MM-IBKR source archive exceeds byte cap")
            chunks.append(block)
    payload = b"".join(chunks)
    if sha256_bytes(payload) != source["archive_sha256"]:
        raise RuntimeError("MM-IBKR source archive digest mismatch")
    return payload


def _safe_extract_tar(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    top_levels: set[str] = set()
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        if not members:
            raise RuntimeError("MM-IBKR source archive empty")
        for member in members:
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError("source archive links/devices rejected")
            parts = Path(member.name).parts
            if not parts or any(part in {"", ".", ".."} for part in parts):
                raise RuntimeError("source archive path rejected")
            top_levels.add(parts[0])
            target = (root / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("source archive path traversal rejected")
        if len(top_levels) != 1:
            raise RuntimeError("source archive must have exactly one top-level directory")
        tf.extractall(root)
    source_root = root / next(iter(top_levels))
    required = {"Dockerfile.bot", "main.py", "requirements.txt", "docker-compose.yml"}
    missing = sorted(name for name in required if not (source_root / name).is_file())
    if missing:
        raise RuntimeError("MM-IBKR source archive missing required files: " + ",".join(missing))
    return source_root


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    os.chmod(path, 0o600)


def materialize(capsule: dict, *, runner_temp: Path) -> dict:
    source_archive = runner_temp / "mm-ibkr-source.tar.gz"
    source_archive.write_bytes(_fetch_source(capsule["source"]))
    os.chmod(source_archive, 0o600)
    source_root = _safe_extract_tar(source_archive, runner_temp / "mm-ibkr-source")

    mode = capsule["mode"]
    read_only_api = "yes" if mode == "session_reconcile" else "no"
    ibkr = capsule["ibkr"]
    gateway_env = runner_temp / "ibkr-gateway.env"
    _write_private(
        gateway_env,
        "\n".join(
            [
                "TWS_USERID=" + ibkr["username"],
                "TWS_PASSWORD=" + ibkr["password"],
                "TRADING_MODE=paper",
                "READ_ONLY_API=" + read_only_api,
                "TWS_ACCEPT_INCOMING=accept",
                "TWOFA_TIMEOUT_ACTION=exit",
                "RELOGIN_AFTER_TWOFA_TIMEOUT=no",
                "SAVE_TWS_SETTINGS=no",
                "ENABLE_VNC=false",
                "",
            ]
        ),
    )

    request_path = runner_temp / "ibkr-submit-request.json"
    _write_private(request_path, json.dumps(capsule["request"], sort_keys=True) + "\n")
    runtime_path = runner_temp / "ibkr-runtime.json"
    runtime = {
        "schema": "mm-ibkr-remote-paper-materialization-v1",
        "mode": mode,
        "mmibkr_repository": SOURCE_REPOSITORY,
        "mmibkr_head": capsule["source"]["head"],
        "source_archive_sha256": capsule["source"]["archive_sha256"],
        "source_root": str(source_root),
        "gateway_env_path": str(gateway_env),
        "request_path": str(request_path),
        "read_only_api": read_only_api,
        "cleanup": capsule["cleanup"],
        "paper_only": True,
        "live_trading_change": False,
        "host_dependency": False,
        "secrets_in_receipt": False,
    }
    _write_private(runtime_path, json.dumps(runtime, sort_keys=True) + "\n")
    return runtime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--ciphertext", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--response-root", required=True)
    parser.add_argument("--runner-temp", required=True)
    args = parser.parse_args()

    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    ciphertext = Path(args.ciphertext).read_bytes()
    plaintext = decrypt_assembled_ciphertext(
        envelope=envelope,
        ciphertext=ciphertext,
        private_key_path=Path(args.private_key),
        expected_schema=ENVELOPE_SCHEMA,
        expected_run_id=args.run_id,
        expected_harness=HARNESS,
        response_root=args.response_root,
        expected_authority=AUTHORITY,
    )
    capsule = validate_capsule(plaintext)
    runtime = materialize(capsule, runner_temp=Path(args.runner_temp))
    print(
        "IBKR_REMOTE_PAPER_MATERIALIZED="
        + json.dumps(
            {
                key: runtime[key]
                for key in (
                    "schema",
                    "mode",
                    "mmibkr_repository",
                    "mmibkr_head",
                    "source_archive_sha256",
                    "read_only_api",
                    "paper_only",
                    "live_trading_change",
                    "host_dependency",
                    "secrets_in_receipt",
                )
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
