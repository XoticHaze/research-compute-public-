from __future__ import annotations

"""Fail-closed cooldown classifier for selected-runtime watchdog broker dependency.

This module owns no broker, runtime, StrategySpec, promotion, or live authority.
It only decides whether the watchdog should temporarily avoid dispatching a new
selected-runtime owner after repeated B1 dependency failures.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

B1_BRANCH = "ibkr-b1-authority-v1"
FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 1800
ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}
BROKER_DEPENDENCY_STEP = "Prove read-only broker session and historical data fetch"
HISTORICAL_CONFLICT_HANDOFF_STEP = "Materialize canonical post-auth broker and forward-data handoff"
HISTORICAL_CONFLICT_VALIDATION_STEP = "Validate and re-emit only the fixed-field historical session-conflict receipt"
HISTORICAL_CONFLICT_PUBLISH_STEP = "Publish fixed-field historical session-conflict failure"


def _utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")



CLOUD_RECEIPT_SCHEMA = "mmibkr.selected_runtime_cloud_session_receipt.v2"
CLOUD_SOURCE_TRANSPORT = "fleet_authority_exact_sha_encrypted_snapshot_vault"
_PAPER_FALSE_FIELDS = (
    "live_execution_allowed", "credentials_included", "account_state_included",
    "positions_included", "orders_included",
)


def checkpoint_receipt_origin_admitted(
    run: Mapping[str, Any], receipt: Mapping[str, Any], expected_source: str
) -> bool:
    """Fail closed before watchdog reuse of a prior owner checkpoint.

    A rendezvous JSON object and saved-cache marker are not sufficient:
    require a completed successful exact run, matching GitHub run/source
    identities, terminal accepted paper session, and safe receipt authority.
    This is a source/receipt guard, NOT cryptographic owner attestation or
    broker/session continuity proof.
    """
    if not isinstance(run, Mapping) or not isinstance(receipt, Mapping):
        return False
    if not isinstance(expected_source, str) or len(expected_source) != 40 or any(
        ch not in "0123456789abcdef" for ch in expected_source
    ):
        return False
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("head_branch") != "main"
        or run.get("event") not in ("workflow_dispatch", "push")
    ):
        return False
    run_id = str(run.get("id") or "")
    if not run_id.isdigit() or str(receipt.get("run_id") or "") != run_id:
        return False
    public_sha = run.get("head_sha")
    if (
        not isinstance(public_sha, str)
        or len(public_sha) != 40
        or any(ch not in "0123456789abcdef" for ch in public_sha.lower())
        or receipt.get("public_head") != public_sha
        or receipt.get("private_head") != expected_source
        or receipt.get("schema") != CLOUD_RECEIPT_SCHEMA
        or receipt.get("source_transport") != CLOUD_SOURCE_TRANSPORT
    ):
        return False
    if (
        receipt.get("ok") is not True
        or receipt.get("session_accepted") is not True
        or receipt.get("checkpoint_handoff_ready") is not True
    ):
        return False
    return all(receipt.get(key) is False for key in _PAPER_FALSE_FIELDS)


def _verified_broker_dependency_failure(run: Mapping[str, Any], jobs: Any) -> bool:
    """Require independently observed GitHub steps for an actual broker failure.

    Legacy B1 had a dedicated failing broker step. Current B1 fails its
    post-auth handoff step and then validates/publishes a STRICT fixed-field
    different-IP conflict receipt. All three must be completed in the SAME
    failed GitHub job before the watchdog may claim broker-dependency cooldown.
    A generic post-auth failure, missing/failed receipt, or zero-step nonstart
    remains unclassified.
    """
    if not isinstance(jobs, list):
        return False
    expected_run_id = str(run.get("id") or "")
    if not expected_run_id.isdigit():
        return False
    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        if (str(job.get("run_id") or "") != expected_run_id
                or job.get("conclusion") != "failure"):
            continue
        steps = [step for step in (job.get("steps") or [])
                 if isinstance(step, Mapping)]
        def exact_step(name: str, conclusion: str) -> bool:
            matches = [step for step in steps if step.get("name") == name]
            return (len(matches) == 1
                    and matches[0].get("status") == "completed"
                    and matches[0].get("conclusion") == conclusion)
        if exact_step(BROKER_DEPENDENCY_STEP, "failure"):
            return True
        if (exact_step(HISTORICAL_CONFLICT_HANDOFF_STEP, "failure")
                and exact_step(HISTORICAL_CONFLICT_VALIDATION_STEP, "success")
                and exact_step(HISTORICAL_CONFLICT_PUBLISH_STEP, "success")):
            return True
    return False



def evaluate_b1_failure_cooldown(
    runs: Iterable[Mapping[str, Any]],
    *,
    job_evidence_by_run_id: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    threshold: int = FAILURE_THRESHOLD,
    cooldown_seconds: int = COOLDOWN_SECONDS,
) -> dict[str, Any]:
    """Return whether recent consecutive B1 failures should suppress owner dispatch."""

    if threshold < 1:
        raise ValueError("threshold_must_be_positive")
    if cooldown_seconds < 1:
        raise ValueError("cooldown_seconds_must_be_positive")

    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    candidates = [
        dict(run)
        for run in runs
        if isinstance(run, Mapping)
        and str(run.get("event") or "") == "workflow_dispatch"
        and str(run.get("head_branch") or "") == B1_BRANCH
    ]
    candidates.sort(
        key=lambda row: _utc(row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    if candidates and str(candidates[0].get("status") or "") in ACTIVE_STATUSES:
        latest = candidates[0]
        return {
            "suppress": True,
            "reason": "b1_dependency_run_active",
            "consecutive_failure_count": 0,
            "latest_run_id": str(latest.get("id") or "") or None,
            "latest_failure_at_utc": None,
            "retry_after_utc": None,
            "cooldown_seconds": cooldown_seconds,
            "threshold": threshold,
        }

    failures: list[dict[str, Any]] = []
    unclassified_failure: dict[str, Any] | None = None
    for run in candidates:
        if str(run.get("status") or "") in ACTIVE_STATUSES:
            break
        if str(run.get("conclusion") or "") != "failure":
            break
        jobs = (job_evidence_by_run_id or {}).get(str(run.get("id") or ""))
        if not _verified_broker_dependency_failure(run, jobs):
            unclassified_failure = run
            break
        failures.append(run)
        if len(failures) >= threshold:
            break

    latest_failure = failures[0] if failures else None
    latest_failure_at = (
        _utc(latest_failure.get("updated_at") or latest_failure.get("created_at"))
        if latest_failure
        else None
    )
    retry_after = (
        latest_failure_at + timedelta(seconds=cooldown_seconds)
        if latest_failure_at
        else None
    )
    suppress = bool(
        len(failures) >= threshold
        and retry_after is not None
        and now_utc < retry_after
    )

    return {
        "suppress": suppress,
        "reason": (
            "recent_consecutive_b1_failures"
            if suppress
            else "b1_failure_unclassified" if unclassified_failure
            else "b1_dependency_cooldown_not_required"
        ),
        "consecutive_failure_count": len(failures),
        "unclassified_failure_run_id": (
            str(unclassified_failure.get("id") or "") or None
            if unclassified_failure else None
        ),
        "latest_run_id": (
            str(latest_failure.get("id") or "") or None
            if latest_failure
            else None
        ),
        "latest_failure_at_utc": _iso(latest_failure_at),
        "retry_after_utc": _iso(retry_after) if suppress else None,
        "cooldown_seconds": cooldown_seconds,
        "threshold": threshold,
    }
