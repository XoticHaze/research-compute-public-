from __future__ import annotations

from dataclasses import dataclass


class TimingRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class TimingPolicy:
    max_admission_seconds: int = 900
    max_execution_seconds: int = 6 * 60 * 60
    max_result_return_grace_seconds: int = 60 * 60
    max_result_retention_seconds: int = 7 * 24 * 60 * 60


def validate_intent(
    *,
    now: int,
    intent_not_before: int,
    intent_not_after: int,
    execution_seconds: int,
    result_return_grace_seconds: int,
    result_retention_seconds: int,
    policy: TimingPolicy = TimingPolicy(),
) -> None:
    if intent_not_after <= intent_not_before or intent_not_after <= now:
        raise TimingRejected("intent_window_rejected")
    if not 1 <= execution_seconds <= policy.max_execution_seconds:
        raise TimingRejected("execution_window_rejected")
    if not 0 <= result_return_grace_seconds <= policy.max_result_return_grace_seconds:
        raise TimingRejected("result_return_window_rejected")
    if not 1 <= result_retention_seconds <= policy.max_result_retention_seconds:
        raise TimingRejected("result_retention_window_rejected")


def bind_admission(
    *,
    now: int,
    intent_not_before: int,
    intent_not_after: int,
    admission_not_after: int,
    policy: TimingPolicy = TimingPolicy(),
) -> None:
    if now < intent_not_before:
        raise TimingRejected("intent_not_yet_valid")
    if now >= intent_not_after:
        raise TimingRejected("intent_expired")
    if admission_not_after <= now:
        raise TimingRejected("admission_expired")
    if admission_not_after - now > policy.max_admission_seconds:
        raise TimingRejected("admission_ttl_too_long")


def admit(
    *,
    now: int,
    admission_not_after: int,
    execution_seconds: int,
    result_return_grace_seconds: int,
    policy: TimingPolicy = TimingPolicy(),
) -> dict:
    if admission_not_after <= now:
        raise TimingRejected("admission_expired")
    if not 1 <= execution_seconds <= policy.max_execution_seconds:
        raise TimingRejected("execution_window_rejected")
    if not 0 <= result_return_grace_seconds <= policy.max_result_return_grace_seconds:
        raise TimingRejected("result_return_window_rejected")
    execution_not_after = now + execution_seconds
    return {
        "admitted_at": now,
        "execution_not_after": execution_not_after,
        "result_return_not_after": execution_not_after + result_return_grace_seconds,
    }


def complete(
    *,
    now: int,
    result_return_not_after: int,
    result_retention_seconds: int,
    policy: TimingPolicy = TimingPolicy(),
) -> dict:
    if now > result_return_not_after:
        raise TimingRejected("result_return_expired")
    if not 1 <= result_retention_seconds <= policy.max_result_retention_seconds:
        raise TimingRejected("result_retention_window_rejected")
    return {
        "completed_at": now,
        "result_retain_until": now + result_retention_seconds,
    }
