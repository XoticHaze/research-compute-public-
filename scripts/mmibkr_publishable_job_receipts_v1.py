from __future__ import annotations

"""Publish only dispatcher-sanitized canonical job receipts from a completed session."""

import argparse
import hashlib
import json
import re
import os
import tempfile
from pathlib import Path
from typing import Any

# Resolve the sibling registry deterministically for both the workflow's
# direct-script entrypoint and package imports. Never search a third-party
# `scripts` namespace or mask a missing dispatcher dependency.
if __package__:
    from .mmibkr_canonical_workload_dispatch_v1 import CAPABILITIES
else:
    from mmibkr_canonical_workload_dispatch_v1 import CAPABILITIES

SESSION_SCHEMA = "mmibkr.canonical_session_receipt.v1"
JOB_SCHEMA = "mmibkr.canonical_workload_receipt.v1"
MANIFEST_SCHEMA = "mmibkr.publishable_canonical_job_receipts.v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN = (
    "broker_submit",
    "broker_cancel",
    "broker_flatten",
    "strategy_spec_write",
    "runtime_activation",
    "promotion_mutation",
    "live_trading",
)
MAX_LOG_BYTES = 512_000


def _load(path: Path) -> dict[str, Any]:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise ValueError("canonical JSON root must be object")
    return node


def _compact(node: Any) -> bytes:
    return json.dumps(
        node,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_public_atomic(root: Path, filename: str, raw: bytes) -> None:
    """Write fixed-name public output without following a planted target symlink.

    Atomic replacement preserves idempotent reruns while preventing a
    symlink at job-<digest>.json or manifest.json from redirecting writes.
    """
    if filename != "manifest.json" and not re.fullmatch(r"job-[0-9a-f]{64}\.json", filename):
        raise ValueError("public output filename rejected")
    target = root / filename
    if target.is_symlink():
        raise ValueError("public output target symlink rejected")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=root, prefix=".publish-", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        # os.replace never follows a final-component symlink, including a
        # concurrent symlink swap after the is_symlink check.
        os.replace(temp_path, target)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


PUBLIC_RECEIPT_SCHEMA = "mmibkr.public_canonical_workload_receipt.v1"


def project_safe_public_job_receipt(*, job_id: str, state: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    """Pure fixed-field projection, not authorization to publish or dispatch.

    The owning stage() remains fail-closed until independently authenticated
    encrypted private input, private full-result return, and trusted placement
    issuance are admitted. This helper NEVER prints or writes private objects.
    """
    if not isinstance(job_id, str) or not job_id or len(job_id) > 256:
        raise ValueError("public_job_id_rejected")
    if not isinstance(state, dict) or state.get("state") not in {"completed", "cached"}:
        raise ValueError("public_job_state_rejected")
    if not isinstance(receipt, dict) or receipt.get("schema") != JOB_SCHEMA:
        raise ValueError("public_job_receipt_schema_rejected")
    fingerprint = str(state.get("job_fingerprint") or "").lower()
    if not SHA256.fullmatch(fingerprint):
        raise ValueError("public_job_fingerprint_rejected")
    if receipt.get("job_id") != job_id or receipt.get("job_fingerprint") != fingerprint:
        raise ValueError("public_job_receipt_identity_mismatch")
    if receipt.get("status") != "completed":
        raise ValueError("public_job_receipt_not_completed")
    authority = receipt.get("authority")
    if not isinstance(authority, dict) or authority.get("research_only") is not True:
        raise ValueError("public_job_authority_missing")
    if any(authority.get(key) is not False for key in FORBIDDEN):
        raise ValueError("public_job_authority_escalation")
    capability = receipt.get("capability_id")
    if not isinstance(capability, str) or capability not in CAPABILITIES:
        raise ValueError("public_job_capability_identity_rejected")
    result_sha = str(receipt.get("result_sha256") or "").lower()
    if not SHA256.fullmatch(result_sha) or str(state.get("result_sha256") or "").lower() != result_sha:
        raise ValueError("public_job_result_digest_mismatch")
    if "result" not in receipt or _sha256(_compact(receipt["result"])) != result_sha:
        raise ValueError("public_job_result_content_digest_mismatch")
    return {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "job_id": "job-" + fingerprint,
        "job_fingerprint": fingerprint,
        "capability_id": capability,
        "status": "completed",
        "result_sha256": result_sha,
        "private_receipt_sha256": _sha256(_compact(receipt)),
        "authority": {"research_only": True, **{key: False for key in FORBIDDEN}},
    }

def stage(session_terminal: Path, receipt_dir: Path, output_dir: Path) -> dict[str, Any]:
    # Confidential canonical receipts include nested private results. The legacy
    # exporter copied the entire receipt into public artifacts and job logs.
    # A caller's "sanitized" label or local validation is not authorization to
    # publish: fail before opening inputs, creating files, or printing values.
    # The existing canonical session workflow also fails before job execution
    # until authenticated encrypted request AND full private result return exist.
    raise RuntimeError("two_sided_private_result_return_not_admitted")
    session = _load(session_terminal)
    if session.get("schema") != SESSION_SCHEMA or session.get("status") != "completed":
        raise ValueError("completed canonical session receipt required")
    session_fingerprint = str(session.get("session_fingerprint") or "").lower()
    if not SHA256.fullmatch(session_fingerprint):
        raise ValueError("canonical session fingerprint invalid")
    public_session_id = "session-" + session_fingerprint
    jobs = session.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise ValueError("canonical session jobs missing")

    source_root = (receipt_dir / "receipts").resolve()
    if output_dir.is_symlink():
        raise ValueError("public output directory symlink rejected")
    output_root = output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    published: list[dict[str, Any]] = []
    seen_public_jobs: set[str] = set()
    for job_id in sorted(jobs):
        state = jobs[job_id]
        # Private job IDs are caller-controlled. Only the verified digest may
        # cross the public log/artifact/filename boundary.
        if not isinstance(state, dict) or state.get("state") not in {"completed", "cached"}:
            raise ValueError("job is not publishable")
        fingerprint = str(state.get("job_fingerprint") or "").lower()
        if not SHA256.fullmatch(fingerprint):
            raise ValueError("canonical job fingerprint invalid")
        public_job_id = "job-" + fingerprint
        if public_job_id in seen_public_jobs:
            raise ValueError("duplicate public job fingerprint rejected")
        seen_public_jobs.add(public_job_id)
        source = (source_root / f"{fingerprint}.json").resolve()
        if source_root not in source.parents or not source.is_file():
            raise ValueError("canonical job receipt missing")

        receipt = _load(source)
        if receipt.get("schema") != JOB_SCHEMA:
            raise ValueError("canonical job receipt schema rejected")
        if receipt.get("job_id") != job_id or receipt.get("job_fingerprint") != fingerprint:
            raise ValueError("canonical job receipt identity mismatch")
        if receipt.get("status") != "completed":
            raise ValueError("canonical job receipt not completed")
        authority = receipt.get("authority")
        if not isinstance(authority, dict) or authority.get("research_only") is not True:
            raise ValueError("canonical job receipt research authority missing")
        if any(authority.get(key) is not False for key in FORBIDDEN):
            raise ValueError("canonical job receipt authority escalation rejected")

        result_sha = str(receipt.get("result_sha256") or "").lower()
        if not SHA256.fullmatch(result_sha):
            raise ValueError("canonical job result digest missing")
        session_result_sha = str(state.get("result_sha256") or "").lower()
        if session_result_sha != result_sha:
            raise ValueError("session/job result digest mismatch")
        if _sha256(_compact(receipt.get("result"))) != result_sha:
            raise ValueError("canonical job result content digest mismatch")
        capability = str(receipt.get("capability_id") or "")
        if capability not in CAPABILITIES:
            raise ValueError("canonical job capability identity invalid")
        # Explicit safe-field allowlist. Never publish private source, StrategySpec,
        # parameters, features, execution details, raw results or artifacts.
        public_receipt = {
            "schema": "mmibkr.public_canonical_workload_receipt.v1",
            "job_id": public_job_id,
            "job_fingerprint": fingerprint,
            "capability_id": capability,
            "status": "completed",
            "result_sha256": result_sha,
            "private_receipt_sha256": _sha256(_compact(receipt)),
            "authority": {"research_only": True, **{key: False for key in FORBIDDEN}},
        }
        raw = _compact(public_receipt) + b"\n"

        target = output_root / f"{public_job_id}.json"
        _write_public_atomic(output_root, target.name, raw)
        desc = {
            "job_id": public_job_id,
            "job_fingerprint": fingerprint,
            "capability_id": receipt.get("capability_id"),
            "result_sha256": result_sha,
            "receipt_sha256": _sha256(raw.rstrip(b"\n")),
            "private_receipt_sha256": public_receipt["private_receipt_sha256"],
            "bytes": len(raw),
            "relative_path": target.name,
        }
        published.append(desc)

        if len(raw) <= MAX_LOG_BYTES:
            print(f"MMIBKR_CANONICAL_JOB_RECEIPT_BEGIN={public_job_id}")
            print(raw.decode("utf-8").rstrip())
            print(f"MMIBKR_CANONICAL_JOB_RECEIPT_END={public_job_id}")
        else:
            print(
                "MMIBKR_CANONICAL_JOB_RECEIPT_LARGE="
                + json.dumps(desc, sort_keys=True, separators=(",", ":"))
            )

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "session_id": public_session_id,
        "session_fingerprint": session_fingerprint,
        "job_count": len(published),
        "jobs": published,
        "authority": {
            "research_only": True,
            **{key: False for key in FORBIDDEN},
        },
    }
    _write_public_atomic(output_root, "manifest.json", _compact(manifest) + b"\n")
    print(
        "MMIBKR_CANONICAL_JOB_RECEIPT_MANIFEST="
        + json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-terminal", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    stage(args.session_terminal, args.receipt_dir, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
