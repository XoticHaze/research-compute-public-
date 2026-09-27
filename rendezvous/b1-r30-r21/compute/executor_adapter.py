"""Translate a fleet placement into invocation metadata for an existing portable executor.

This module does not execute workloads and does not understand domain capabilities.
"""
from __future__ import annotations
from typing import Any

EXECUTORS={
 "github_actions_generic":{
   "kind":"portable_session",
   "repository":"XoticHaze/research-compute-public-",
   "entrypoint":"scripts/mmibkr_canonical_session_runner_v1.py",
   "session_schema":"mmibkr.canonical_session.v1",
   "receipt_schema":"mmibkr.canonical_session_receipt.v1",
 }
}

def invocation_for(placement_receipt:dict[str,Any], job:dict[str,Any])->dict[str,Any]:
    executor=placement_receipt.get("executor") or {}
    kind=executor.get("kind")
    if kind not in EXECUTORS: raise RuntimeError("GENERIC_EXECUTOR_ADAPTER_UNAVAILABLE")
    if placement_receipt.get("job_id")!=job.get("job_id"): raise ValueError("PLACEMENT_JOB_ID_MISMATCH")
    e=EXECUTORS[kind]
    return {"schema":"commandcenter.compute_invocation.v1","job_id":job["job_id"],
      "job_sha256":placement_receipt["job_sha256"],"compute_id":placement_receipt["compute_id"],
      "executor_kind":kind,"repository":e["repository"],"entrypoint":e["entrypoint"],
      "portable_session":job["package"],"expected_receipt_schema":e["receipt_schema"],
      "state":"READY_TO_LAUNCH"}
