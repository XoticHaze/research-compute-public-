"""Exact FORM v23 native Cycles consumer within the EXISTING admitted Blender harness.

No public entrypoint, GitHub dispatch, signer, issuer, token, arbitrary script,
or URLs. All input file bytes are hash-pinned and P256/AES-GCM request-sealed.
The controlling CommandCenter adapter MUST independently authenticate the
PLACED job/nonce before calling this function. A local source test is not
admission or a Blender execution result.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

from scripts.creative.form_v23_fixed_payload_v1 import (
    FIXED_MEMBERS, fixed_job, fixed_job_digest,
    open_sealed_inputs, read_fixed_payload, sha)
from scripts.creative.form_v23_fixed_result_v1 import (
    FILES, seal_native_outputs)
from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import open_capsule, seal

REQUEST_SCHEMA = "commandcenter.blender_sealed_request.v1"
RESPONSE_SCHEMA = "incomeengine.form_v23.fixed_blender_sealed_terminal.v1"


def _approved_checkout(root:Path, job:dict):
    root=Path(root).resolve(strict=True)
    checkout=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],
                            capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    if checkout != job["source"]["commit"]:
        raise ValueError("public_executor_checkout_identity_mismatch")
    return root


def _safe_root(root:Path, other:Path):
    given_root=Path(root);given_other=Path(other)
    if given_root.is_symlink() or given_other.is_symlink():
        raise ValueError("symlink_root_rejected")
    root=given_root.resolve();other=given_other.resolve()
    if root==other or root in other.parents or other in root.parents:
        raise ValueError("protected_work_and_ciphertext_roots_must_not_overlap")
    return root,other


def _stage_private_source(files:dict,stage:Path):
    stage.mkdir(mode=0o700,parents=False,exist_ok=False)
    for name in sorted(FIXED_MEMBERS):
        target=stage/name
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() or target.is_symlink():
            raise ValueError("private_stage_target_already_exists")
        target.write_bytes(files[name]);target.chmod(0o600)
        if sha(target.read_bytes())!=FIXED_MEMBERS[name][1]:
            raise RuntimeError("private_stage_member_digest_mismatch")
    return stage


def _run_exact_pinned_form(stage:Path,work:Path,blender_binary:Path,variant:str):
    name="source/form_v23_pair_first_native_review.py"
    source=stage/name
    if sha(source.read_bytes())!=FIXED_MEMBERS[name][1]:
        raise RuntimeError("trusted_renderer_wrapper_digest_mismatch")
    spec=importlib.util.spec_from_file_location("fixed_incomeengine_form_v23_renderer",source)
    if spec is None or spec.loader is None:
        raise RuntimeError("frozen_review_module_unavailable")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module) # Executing ONLY exact independently pinned private source
    return module.execute(stage,work,blender_binary,variant)


def execute_admitted_form_v23(
    request_envelope:dict, sealed_inputs:dict, *, run_id:str,
    worker_private_b64:str, source_root:Path, work_root:Path,
    ciphertext_root:Path, blender_binary:Path,
    placement_validator,
) -> dict:
    """Protected controller-supplied validation must authenticate before decrypt.

    `placement_validator` is supplied ONLY by the protected existing signed
    placement layer. It MUST validate issuer, nonce, job digest, executor id,
    trust mode, and run identity, and MUST reject replay. It is not a caller-
    serialized job field or a boolean skip flag.
    """
    if not callable(placement_validator):
        raise PermissionError("independent_placement_verifier_not_connected")
    decrypted=open_capsule(request_envelope,recipient_private_b64=worker_private_b64,
             expected_run_id=run_id,expected_direction="request")
    if len(decrypted)>4096:raise ValueError("sealed_small_job_request_oversize")
    request=json.loads(decrypted)
    if (not isinstance(request,dict) or set(request)!={"schema","job","result_recipient_public_b64"}
        or request["schema"]!=REQUEST_SCHEMA):
        raise ValueError("sealed_blender_job_request_invalid")
    job=fixed_job(request["job"])
    recipient=request["result_recipient_public_b64"]
    if not isinstance(recipient,str) or not 30<=len(recipient)<=200:
        raise ValueError("result_recipient_rejected")
    # Exact RUN-BOUND trusted admission: the protected callback is the sole
    # source of issuer/nonce verification, not a digest supplied in the job.
    placement_validator(job_digest=fixed_job_digest(job),run_id=run_id,
        executor_identity=job["source"],trust_mode="public_encrypted")
    _approved_checkout(source_root,job)
    base,cipher=_safe_root(work_root,ciphertext_root)
    base.mkdir(parents=True,exist_ok=True)
    cipher.mkdir(parents=True,exist_ok=True)
    stage=base/(job["job_id"]+".private_input")
    work=base/job["job_id"]
    destination=cipher/job["job_id"]
    if stage.exists() or work.exists() or destination.exists():
        raise ValueError("job_replay_or_preexisting_result_path")
    try:
        payload=open_sealed_inputs(sealed_inputs,job=job,run_id=run_id,
            recipient_private_b64=worker_private_b64,open_capsule_fn=open_capsule)
        files=read_fixed_payload(payload)
        _stage_private_source(files,stage)
        receipt=_run_exact_pinned_form(stage,work,Path(blender_binary),job["variant"])
        if not isinstance(receipt,dict) or receipt.get("selected_variant")!=job["variant"]:
            raise RuntimeError("native_result_variant_mismatch")
        output=work/"jar"
        artifacts={
           FILES[0]:(output/FILES[0]).read_bytes(),
           FILES[1]:(output/FILES[1]).read_bytes(),
           FILES[2]:(work/FILES[2]).read_bytes(),
           FILES[3]:(work/FILES[3]).read_bytes(),
        }
        ciphertext=seal_native_outputs(artifacts,job=job,run_id=run_id,
            recipient_public_b64=recipient,seal_fn=seal)
        destination.mkdir(mode=0o700,exist_ok=False)
        try:
            # Header and all pieces first. Public completion marker LAST.
            for name,record in sorted(ciphertext.items()):
                if name=="manifest.json":continue
                (destination/name).write_text(json.dumps(record,sort_keys=True,separators=(",", ":"))+"\n")
            (destination/"manifest.json").write_text(json.dumps(ciphertext["manifest.json"],
                  sort_keys=True,separators=(",", ":"))+"\n")
        except BaseException:
            shutil.rmtree(destination)
            raise
        return {"schema":RESPONSE_SCHEMA,"status":"CIPHERTEXT_READY",
             "job_sha256":fixed_job_digest(job),"run_id":run_id,
             "public_plaintext_artifacts":False,
             "ciphertext_parts":len(ciphertext["manifest.json"]["parts"])}
    finally:
        # Both success and failure; do NOT leave private assets/render/model
        # or raw Blender stdout on public runner disk.
        for path in (stage,work):
            if path.is_dir() and not path.is_symlink():shutil.rmtree(path)
