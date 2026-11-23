"""Fixed Blender CPU work executor. Invoked only by an independently admitted compute owner.

No arbitrary script/package/shell/URL from request. This module does NOT issue a
placement, sign a ticket, decrypt protected inputs or dispatch GitHub Actions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

SCHEMA = "commandcenter.blender_job.v1"
OUTPUT_SCHEMA = "commandcenter.blender_probe_result.v1"
UPSTREAM = "d5e8889eef0b33e0bbe62ddca6f713f94b154b68"
SOURCE = "XoticHaze/research-compute-public-"
EXPECTED = ("arm.blend", "arm.glb", "preview.png")
RANGES = {"camera_azimuth_deg": (-90, 90), "preview_frame": (1, 120),
          "preview_samples": (4, 32)}
RECIPE = Path(__file__).with_name("industrial_arm_v1.py").resolve()


def canonical(node):
    return json.dumps(node, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def validate(job):
    keys = {"schema", "job_id", "recipe_id", "source", "upstream_commit", "revision",
            "parent_job_sha256", "parameters", "classification"}
    if not isinstance(job, dict) or set(job) != keys or job.get("schema") != SCHEMA:
        raise ValueError("job_shape")
    if not isinstance(job["job_id"], str) or not re.fullmatch(r"blender-[a-z0-9-]{4,64}", job["job_id"]):
        raise ValueError("job_id_invalid")
    if job["recipe_id"] != "industrial_arm_v1" or job["upstream_commit"] != UPSTREAM:
        raise ValueError("unapproved_recipe_or_upstream")
    if job["classification"] != "public_demo_no_private_inputs":
        raise ValueError("private_request_rejected")
    source = job["source"]
    if not isinstance(source, dict) or set(source) != {"repository", "commit"}:
        raise ValueError("source_shape")
    if source["repository"] != SOURCE or not isinstance(source["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
        raise ValueError("source_identity_rejected")
    revision = job["revision"]
    if type(revision) is not int or not 0 <= revision <= 8:
        raise ValueError("revision_limit")
    parent = job["parent_job_sha256"]
    if (revision == 0 and parent is not None) or (revision > 0 and (not isinstance(parent, str) or not re.fullmatch(r"[0-9a-f]{64}", parent))):
        raise ValueError("parent_revision_invalid")
    params = job["parameters"]
    if not isinstance(params, dict) or set(params) != set(RANGES):
        raise ValueError("parameters_invalid")
    for name, (low, high) in RANGES.items():
        if type(params[name]) is not int or not low <= params[name] <= high:
            raise ValueError("parameter_out_of_range")
    if len(canonical(job)) > 4096:
        raise ValueError("input_too_large")
    return job


def digest(job):
    validate(job)
    return hashlib.sha256(canonical(job)).hexdigest()


def run(job, *, source_root, output_root, blender_binary):
    validate(job)
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    if source_root == output_root or source_root in output_root.parents:
        raise ValueError("output_must_not_be_inside_source")
    actual_sha = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    if actual_sha != job["source"]["commit"]:
        raise ValueError("exact_source_commit_mismatch")
    if not RECIPE.is_file() or RECIPE != (source_root / "scripts/creative/industrial_arm_v1.py").resolve():
        raise ValueError("fixed_recipe_identity_mismatch")
    binary = Path(blender_binary).resolve()
    if not binary.is_file() or not binary.name.startswith("blender"):
        raise ValueError("trusted_blender_not_found")
    ver = subprocess.run([str(binary), "--version"], capture_output=True,
                         text=True, check=True, timeout=15).stdout
    version = re.search(r"Blender\s+(\d+)\.(\d+)\.(\d+)", ver)
    if not version or tuple(int(n) for n in version.groups()) < (5, 2, 0):
        raise ValueError("blender_5_2_or_newer_required")
    work = output_root / job["job_id"]
    work.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env["CC_BLENDER_PROBE_OUTPUT"] = str(work)
    env["CC_BLENDER_PARAMS_JSON"] = json.dumps(job["parameters"], sort_keys=True)
    env["OMP_NUM_THREADS"] = "2"
    command = [str(binary), "--background", "--factory-startup", "--threads", "2",
               "--python-exit-code", "1", "--python", str(RECIPE)]
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=300)
        (work / "blender.log").write_text((result.stdout + "\n" + result.stderr)[-131072:])
        if result.returncode:
            raise RuntimeError("blender_child_failed")
        # Reopen the exported GLB in a fresh Blender process and verify real
        # scene meshes and animated actions, not only the glTF file signature.
        verifier = Path(__file__).with_name("verify_glb_blender_v1.py").resolve()
        if verifier != (source_root / "scripts/creative/verify_glb_blender_v1.py").resolve() or not verifier.is_file():
            raise RuntimeError("fixed_glb_verifier_identity_mismatch")
        verify_env = env.copy()
        verify_env["CC_BLENDER_VERIFY_GLB"] = str(work / "arm.glb")
        verify_env["CC_BLENDER_VERIFY_RESULT"] = str(work / "glb_import_verification.json")
        verification_run = subprocess.run(
            [str(binary), "--background", "--factory-startup", "--threads", "2",
             "--python-exit-code", "1", "--python", str(verifier)],
            env=verify_env, capture_output=True, text=True, timeout=100)
        with (work / "blender.log").open("a") as log:
            log.write(("\\n" + verification_run.stdout + "\\n" + verification_run.stderr)[-65536:])
        if verification_run.returncode:
            raise RuntimeError("blender_glb_reimport_failed")
        verify_json = json.loads((work / "glb_import_verification.json").read_text())
        if verify_json.get("status") != "PASS" or verify_json.get("action_count", 0) < 1:
            raise RuntimeError("blender_glb_reimport_no_motion")
        # Verify there is actual animated glTF data, not merely a file with a GLB header.
        from scripts.creative.blender_artifact_verify_v1 import verify_output_files
        verification = verify_output_files(work)
        receipt = {"schema": OUTPUT_SCHEMA, "status": "SUCCESS", "job_sha256": digest(job),
                   "created_at": datetime.now(timezone.utc).isoformat(),
                   "blender_version": ".".join(version.groups()),
                   "source_commit": actual_sha, "recipe_id": job["recipe_id"],
                   "revision": job["revision"], "files": verification["files"],
                   "gltf": verification["gltf"], "preview": verification["preview"],
                   "independent_blender_reimport": verify_json}
        (work / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        return receipt
    except Exception:
        # All exception messages remain with the trusted job owner, never public stdout.
        (work / "status.json").write_text(json.dumps({"status": "FAILED", "job_sha256": digest(job)}) + "\n")
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--job", type=Path, required=True)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    a = p.parse_args()
    binary = os.environ.get("CC_APPROVED_BLENDER_BINARY") or shutil.which("blender")
    if not binary:
        print("BLENDER_RUNTIME_UNAVAILABLE")
        return 2
    try:
        job = json.loads(a.job.read_text(encoding="utf-8"))
        receipt = run(job, source_root=a.source_root, output_root=a.output_root, blender_binary=binary)
        print(json.dumps({"status": "SUCCESS", "job_sha256": receipt["job_sha256"]}))
        return 0
    except Exception:
        print("BLENDER_FIXED_JOB_REJECTED_OR_FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
