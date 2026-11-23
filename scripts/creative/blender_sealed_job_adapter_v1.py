"""Blender job adapter for existing one-run sealed capsule / signed compute harness.

The harness owns OIDC, independent placement, one-time worker key, envelope
rendezvous and encrypted artifact return. This module only validates/decrypts
the already-admitted payload, executes fixed Blender recipe and encrypts output.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil

from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import open_capsule
from scripts.creative.blender_fixed_worker_v1 import run, validate
from scripts.creative.blender_result_envelope_v1 import encrypt_artifacts

REQUEST_SCHEMA = "commandcenter.blender_sealed_request.v1"


def execute_sealed_job(
    request_envelope: dict,
    *,
    run_id: str,
    worker_private_b64: str,
    source_root: Path,
    work_root: Path,
    ciphertext_root: Path,
    blender_binary: str,
    sealed_form_inputs: dict | None = None,
    placement_validator = None,
) -> dict:
    raw = open_capsule(
        request_envelope, recipient_private_b64=worker_private_b64,
        expected_run_id=run_id, expected_direction="request")
    if len(raw) > 4096:
        raise ValueError("sealed_blender_request_oversize")
    request = json.loads(raw)
    if not isinstance(request, dict) or set(request) != {"schema", "job", "result_recipient_public_b64"}:
        raise ValueError("sealed_job_shape_invalid")
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError("sealed_job_schema_invalid")
    # Opt-in exact FORM v23 private-encrypted recipe. A *trusted* harness must
    # provide both separately received A1 ciphertext parts and an
    # independent protected issuer/nonce verifier. Neither may be supplied in
    # the job itself. Existing industrial-arm demo semantics remain unchanged.
    if isinstance(request["job"], dict):
        from scripts.creative.form_v23_fixed_payload_v1 import RECIPE as FORM_RECIPE
        if request["job"].get("recipe_id") == FORM_RECIPE:
            if sealed_form_inputs is None or not callable(placement_validator):
                raise PermissionError("form_signed_placement_and_encrypted_input_required")
            from scripts.creative.form_v23_fixed_sealed_worker_v1 import execute_admitted_form_v23
            return execute_admitted_form_v23(
                request_envelope, sealed_form_inputs, run_id=run_id,
                worker_private_b64=worker_private_b64, source_root=source_root,
                work_root=work_root, ciphertext_root=ciphertext_root,
                blender_binary=blender_binary, placement_validator=placement_validator)
    job = validate(request["job"])
    recipient = request["result_recipient_public_b64"]
    if not isinstance(recipient, str) or len(recipient) > 200:
        raise ValueError("result_recipient_invalid")
    base = Path(work_root).resolve()
    out = Path(ciphertext_root).resolve()
    if base == out or out in base.parents or base in out.parents:
        raise ValueError("encrypted_and_plain_roots_must_be_separate")
    work_dir = base / job["job_id"]
    try:
        receipt = run(job, source_root=source_root, output_root=base, blender_binary=blender_binary)
        sealed = encrypt_artifacts(
            work_dir, out / job["job_id"], run_id=run_id, recipient_public_b64=recipient)
    finally:
        # The admitted harness must also clean up its own keys and staging.
        # This adapter only owns plaintext render files, not other worker data.
        if work_dir.is_dir() and not work_dir.is_symlink():
            shutil.rmtree(work_dir)
    return {"schema": "commandcenter.blender_sealed_terminal.v1",
            "status": "CIPHERTEXT_READY",
            "job_sha256": receipt["job_sha256"],
            "ciphertext_parts": sealed["part_count"],
            "public_plaintext_artifacts": False}
