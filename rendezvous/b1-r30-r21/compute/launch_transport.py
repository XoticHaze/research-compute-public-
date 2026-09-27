"""Launch an already-placed portable compute invocation through its executor driver.

This module owns no workload semantics, compute placement, or scheduler policy.
"""
from __future__ import annotations
from typing import Any, Protocol

class ExecutorDriver(Protocol):
    def launch(self, invocation: dict[str, Any]) -> dict[str, Any]: ...

class TerminalExecutorDriver(ExecutorDriver, Protocol):
    def wait_terminal(self, invocation: dict[str, Any], launch_result: dict[str, Any]) -> dict[str, Any]: ...


def launch(invocation: dict[str, Any], driver: ExecutorDriver) -> dict[str, Any]:
    if not isinstance(invocation, dict):
        raise ValueError("COMPUTE_INVOCATION_INVALID")
    required = {
        "schema", "job_id", "job_sha256", "compute_id", "executor_kind",
        "repository", "entrypoint", "portable_session", "expected_receipt_schema", "state",
    }
    if set(invocation) != required:
        raise ValueError("COMPUTE_INVOCATION_FIELD_SET_INVALID")
    if invocation.get("schema") != "commandcenter.compute_invocation.v1":
        raise ValueError("COMPUTE_INVOCATION_SCHEMA_INVALID")
    if invocation.get("state") != "READY_TO_LAUNCH":
        raise ValueError("COMPUTE_INVOCATION_NOT_READY")
    result = driver.launch(dict(invocation))
    if not isinstance(result, dict):
        raise RuntimeError("COMPUTE_LAUNCH_RESULT_INVALID")
    if result.get("job_id") != invocation["job_id"] or result.get("job_sha256") != invocation["job_sha256"]:
        raise RuntimeError("COMPUTE_LAUNCH_IDENTITY_MISMATCH")
    if result.get("execution_repository") != invocation["repository"]:
        raise RuntimeError("COMPUTE_LAUNCH_REPOSITORY_MISMATCH")
    workflow_ref = str(result.get("workflow_ref") or "")
    if not workflow_ref.startswith(invocation["repository"] + "/.github/workflows/") or "@refs/heads/" not in workflow_ref:
        raise RuntimeError("COMPUTE_LAUNCH_WORKFLOW_IDENTITY_MISSING")
    if not str(result.get("surface_run_id") or "").strip():
        raise RuntimeError("COMPUTE_LAUNCH_RUN_ID_MISSING")
    return result


def launch_and_wait(invocation: dict[str, Any], driver: TerminalExecutorDriver) -> dict[str, Any]:
    """Launch one already-placed invocation and consume its exact terminal artifact."""
    launched = launch(invocation, driver)
    terminal = driver.wait_terminal(dict(invocation), dict(launched))
    if not isinstance(terminal, dict):
        raise RuntimeError("COMPUTE_TERMINAL_RESULT_INVALID")
    for key in ("job_id", "job_sha256", "surface_run_id", "workflow_ref"):
        if terminal.get(key) != launched.get(key):
            raise RuntimeError(f"COMPUTE_TERMINAL_{key.upper()}_MISMATCH")
    if not str(terminal.get("artifact_id") or "").strip():
        raise RuntimeError("COMPUTE_TERMINAL_ARTIFACT_ID_MISSING")
    archive_sha = str(terminal.get("artifact_archive_sha256") or "")
    if len(archive_sha) != 64 or any(ch not in "0123456789abcdef" for ch in archive_sha):
        raise RuntimeError("COMPUTE_TERMINAL_ARTIFACT_SHA256_INVALID")
    receipt = terminal.get("terminal_receipt")
    if not isinstance(receipt, dict) or receipt.get("job_sha256") != invocation["job_sha256"]:
        raise RuntimeError("COMPUTE_TERMINAL_RECEIPT_IDENTITY_MISMATCH")
    return terminal