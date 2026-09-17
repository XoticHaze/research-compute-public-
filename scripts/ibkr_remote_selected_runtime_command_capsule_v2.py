from __future__ import annotations

"""Decrypt and materialize an MM-IBKR selected-runtime command capsule v2.

V2 deliberately contains no broker username/password. Gateway authentication is
owned by the admitted Fleet Authority + clean warm-state lifecycle. The capsule
carries only exact private MM-IBKR source capability, one MM-authorized paper
command, and mandatory cleanup semantics.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from ephemeral_x25519_chunked_v1 import decrypt_assembled_ciphertext
from ibkr_remote_paper_capsule_v1 import (
    AUTHORITY,
    ENVELOPE_SCHEMA,
    HARNESS,
    _fetch_source,
    _safe_extract_tar,
    _validate_source,
    _write_private,
)

CAPSULE_SCHEMA = "mmibkr.remote_selected_runtime_command_capsule.v2"
MODE = "paper_submit_proof"
CAPSULE_FIELDS = {"schema", "mode", "source", "request", "cleanup"}
REQUEST_FIELDS = {
    "command_id",
    "source_ref",
    "canonical_submit_payload",
    "selected_runtime_authority",
}
CLEANUP_FIELDS = {
    "cancel_open_order",
    "flatten_filled_position",
    "require_zero_baseline",
    "allow_global_cancel",
}
SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "live"}


def _reject_live(value: Any, path: str = "request") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).strip().lower()
            child_path = f"{path}.{raw_key}"
            if key in {
                "enable_live_trading",
                "live_submit_enabled",
                "live_allowed",
                "live_mode_enabled",
                "live_execution_allowed",
            } and _truthy(child):
                raise RuntimeError(f"live authority rejected at {child_path}")
            if key in {"trading_mode", "account_mode"} and str(child or "").strip().lower() == "live":
                raise RuntimeError(f"live mode rejected at {child_path}")
            _reject_live(child, child_path)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_live(child, f"{path}[{index}]")


def _validate_cleanup(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping) or set(value) != CLEANUP_FIELDS:
        raise RuntimeError("cleanup contract field set mismatch")
    cleanup = {key: bool(value.get(key)) for key in CLEANUP_FIELDS}
    expected = {
        "cancel_open_order": True,
        "flatten_filled_position": True,
        "require_zero_baseline": True,
        "allow_global_cancel": False,
    }
    if cleanup != expected:
        raise RuntimeError("paper proof cleanup contract mismatch")
    return cleanup


def _validate_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != REQUEST_FIELDS:
        raise RuntimeError("selected-runtime command request field set mismatch")
    request = dict(value)
    _reject_live(request)

    command_id = str(request.get("command_id") or "").strip().lower()
    source_ref = str(request.get("source_ref") or "").strip()
    payload = request.get("canonical_submit_payload")
    authority = request.get("selected_runtime_authority")
    if not SHA256_ID.fullmatch(command_id):
        raise RuntimeError("command id invalid")
    if not source_ref:
        raise RuntimeError("source ref required")
    if not isinstance(payload, Mapping) or not payload:
        raise RuntimeError("canonical submit payload required")
    if not isinstance(authority, Mapping) or not authority:
        raise RuntimeError("selected runtime authority required")
    if authority.get("authority_source") != "MM-IBKR selected_runtime.execution_policy":
        raise RuntimeError("selected runtime authority source mismatch")
    if authority.get("paper_submit_enabled") is not True:
        raise RuntimeError("selected runtime paper authority required")
    if authority.get("live_submit_enabled") is not False:
        raise RuntimeError("selected runtime live submit must be disabled")

    runtime_id = str(authority.get("runtime_id") or "").strip()
    symbol = str(authority.get("symbol") or "").strip().upper()
    spec_digest = str(authority.get("strategy_spec_digest") or "").strip()
    if not runtime_id or not symbol or not spec_digest:
        raise RuntimeError("selected runtime identity incomplete")
    if str(payload.get("runtime_id") or "").strip() != runtime_id:
        raise RuntimeError("payload runtime id mismatch")
    if str(payload.get("symbol") or "").strip().upper() != symbol:
        raise RuntimeError("payload symbol mismatch")
    if not str(payload.get("idempotency_key") or "").strip():
        raise RuntimeError("payload idempotency key required")

    return {
        "command_id": command_id,
        "source_ref": source_ref,
        "canonical_submit_payload": dict(payload),
        "selected_runtime_authority": dict(authority),
    }


def validate_capsule(raw: bytes) -> dict[str, Any]:
    try:
        capsule = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("capsule is not valid UTF-8 JSON") from exc
    if not isinstance(capsule, Mapping) or set(capsule) != CAPSULE_FIELDS:
        raise RuntimeError("command capsule field set mismatch")
    if capsule.get("schema") != CAPSULE_SCHEMA:
        raise RuntimeError("command capsule schema mismatch")
    if capsule.get("mode") != MODE:
        raise RuntimeError("command capsule mode mismatch")
    source = _validate_source(capsule.get("source"))
    request = _validate_request(capsule.get("request"))
    cleanup = _validate_cleanup(capsule.get("cleanup"))
    return {
        "schema": CAPSULE_SCHEMA,
        "mode": MODE,
        "source": source,
        "request": request,
        "cleanup": cleanup,
    }


def materialize(capsule: Mapping[str, Any], *, runner_temp: Path) -> dict[str, Any]:
    source_archive = runner_temp / "mm-ibkr-source.tar.gz"
    source_archive.write_bytes(_fetch_source(dict(capsule["source"])))
    os.chmod(source_archive, 0o600)
    source_root = _safe_extract_tar(source_archive, runner_temp / "mm-ibkr-source")

    request_path = runner_temp / "ibkr-submit-request.json"
    _write_private(request_path, json.dumps(capsule["request"], sort_keys=True) + "\n")
    runtime_path = runner_temp / "ibkr-runtime.json"
    runtime = {
        "schema": "mmibkr.remote_selected_runtime_materialization.v3",
        "mode": MODE,
        "mmibkr_repository": capsule["source"]["repository"],
        "mmibkr_head": capsule["source"]["head"],
        "source_archive_sha256": capsule["source"]["archive_sha256"],
        "source_root": str(source_root),
        "request_path": str(request_path),
        "read_only_api": "no",
        "cleanup": dict(capsule["cleanup"]),
        "paper_only": True,
        "live_trading_change": False,
        "host_dependency": False,
        "secrets_in_receipt": False,
        "gateway_auth_source": "fleet_authority_warm_state",
        "gateway_credentials_in_capsule": False,
        "command_id": capsule["request"]["command_id"],
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
    print("IBKR_REMOTE_COMMAND_MATERIALIZED=" + json.dumps({
        "schema": runtime["schema"],
        "mode": runtime["mode"],
        "mmibkr_head": runtime["mmibkr_head"],
        "command_id": runtime["command_id"],
        "paper_only": runtime["paper_only"],
        "gateway_auth_source": runtime["gateway_auth_source"],
        "gateway_credentials_in_capsule": runtime["gateway_credentials_in_capsule"],
        "live_trading_change": runtime["live_trading_change"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
