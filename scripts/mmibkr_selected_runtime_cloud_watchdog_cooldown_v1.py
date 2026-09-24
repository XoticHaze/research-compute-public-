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


def evaluate_b1_failure_cooldown(
    runs: Iterable[Mapping[str, Any]],
    *,
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
    for run in candidates:
        if str(run.get("status") or "") in ACTIVE_STATUSES:
            break
        if str(run.get("conclusion") or "") != "failure":
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
            else "b1_dependency_cooldown_not_required"
        ),
        "consecutive_failure_count": len(failures),
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
