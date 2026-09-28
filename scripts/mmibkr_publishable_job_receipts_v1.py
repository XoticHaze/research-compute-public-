from __future__ import annotations

"""Publish only dispatcher-sanitized canonical job receipts from a completed session."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

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
        raise ValueError(f"JSON root must be object: {path}")
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


def stage(session_terminal: Path, receipt_dir: Path, output_dir: Path) -> dict[str, Any]:
    session = _load(session_terminal)
    if session.get("schema") != SESSION_SCHEMA or session.get("status") != "completed":
        raise ValueError("completed canonical session receipt required")
    jobs = session.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        raise ValueError("canonical session jobs missing")

    source_root = (receipt_dir / "receipts").resolve()
    output_root = output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    published: list[dict[str, Any]] = []
    for job_id in sorted(jobs):
        state = jobs[job_id]
        if not isinstance(state, dict) or state.get("state") not in {"completed", "cached"}:
            raise ValueError(f"job is not publishable: {job_id}")
        fingerprint = str(state.get("job_fingerprint") or "").lower()
        if not SHA256.fullmatch(fingerprint):
            raise ValueError(f"invalid job fingerprint: {job_id}")
        source = (source_root / f"{fingerprint}.json").resolve()
        if source_root not in source.parents or not source.is_file():
            raise ValueError(f"canonical job receipt missing: {job_id}")

        receipt = _load(source)
        if receipt.get("schema") != JOB_SCHEMA:
            raise ValueError(f"canonical job receipt schema rejected: {job_id}")
        if receipt.get("job_id") != job_id or receipt.get("job_fingerprint") != fingerprint:
            raise ValueError(f"canonical job receipt identity mismatch: {job_id}")
        if receipt.get("status") != "completed":
            raise ValueError(f"canonical job receipt not completed: {job_id}")
        authority = receipt.get("authority")
        if not isinstance(authority, dict) or authority.get("research_only") is not True:
            raise ValueError(f"canonical job receipt research authority missing: {job_id}")
        if any(authority.get(key) is not False for key in FORBIDDEN):
            raise ValueError(f"canonical job receipt authority escalation rejected: {job_id}")

        raw = _compact(receipt) + b"\n"
        result_sha = str(receipt.get("result_sha256") or "").lower()
        if not SHA256.fullmatch(result_sha):
            raise ValueError(f"canonical job result digest missing: {job_id}")
        session_result_sha = str(state.get("result_sha256") or "").lower()
        if session_result_sha != result_sha:
            raise ValueError(f"session/job result digest mismatch: {job_id}")

        target = output_root / f"{job_id}.json"
        target.write_bytes(raw)
        desc = {
            "job_id": job_id,
            "job_fingerprint": fingerprint,
            "capability_id": receipt.get("capability_id"),
            "result_sha256": result_sha,
            "receipt_sha256": _sha256(raw.rstrip(b"\n")),
            "bytes": len(raw),
            "relative_path": target.name,
        }
        published.append(desc)

        if len(raw) <= MAX_LOG_BYTES:
            print(f"MMIBKR_CANONICAL_JOB_RECEIPT_BEGIN={job_id}")
            print(raw.decode("utf-8").rstrip())
            print(f"MMIBKR_CANONICAL_JOB_RECEIPT_END={job_id}")
        else:
            print(
                "MMIBKR_CANONICAL_JOB_RECEIPT_LARGE="
                + json.dumps(desc, sort_keys=True, separators=(",", ":"))
            )

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "session_id": session.get("session_id"),
        "session_fingerprint": session.get("session_fingerprint"),
        "job_count": len(published),
        "jobs": published,
        "authority": {
            "research_only": True,
            **{key: False for key in FORBIDDEN},
        },
    }
    (output_root / "manifest.json").write_bytes(_compact(manifest) + b"\n")
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
