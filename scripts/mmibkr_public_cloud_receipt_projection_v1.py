from __future__ import annotations

"""Bounded public projection of an MM-IBKR cloud owner receipt.

The canonical daemon and private checkpoint remain unchanged. Only this
projection is eligible for public GitHub receipt storage. The caller constructs
the original receipt from a private runtime session; NEVER publish that original
receipt, unbounded nested cycle state, roll state, or raw failure messages.
"""

from typing import Any

SCHEMA = "mmibkr.selected_runtime_cloud_session_receipt.v2"


def project(receipt: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise ValueError("public_cloud_receipt_schema_rejected")
    if type(receipt.get("session_accepted")) is not bool:
        raise ValueError("public_cloud_receipt_acceptance_type_rejected")

    # Values needed for existing checkpoint/owner acceptance remain unchanged.
    # These three source fields are unbounded and never required by the
    # documented acceptance consumer. Safely project rather than redact by
    # substring, which could miss nested sensitive data.
    public = dict(receipt)
    cycle = receipt.get("last_cycle")
    public["last_cycle"] = (
        {"ok": cycle.get("ok") is True} if isinstance(cycle, dict) else {}
    )
    public["futures_roll_maintenance"] = {}
    public["status"] = (
        "accepted" if receipt["session_accepted"] else "not_accepted"
    )

    # Prevent future callers from inserting raw diagnostic/result fields
    # without a reviewed, versioned expansion of the public receipt contract.
    expected = {
        "schema", "ok", "session_accepted", "status", "run_id",
        "public_head", "private_head", "cycle_count", "success_count",
        "failure_count", "checkpoint_handoff_ready", "last_cycle",
        "futures_roll_maintenance", "source_transport",
        "private_repository_token_used", "live_execution_allowed",
        "public_strategy_authority", "public_execution_policy_authority",
        "credentials_included", "account_state_included",
        "positions_included", "orders_included", "checkpoint_restored",
        "checkpoint_restored_sha256", "checkpoint_restored_cache_key",
        "expected_predecessor_checkpoint_cache_key",
        "expected_predecessor_checkpoint_sha256",
        "expected_predecessor_checkpoint_match",
        "predecessor_terminal_continuity_required",
        "predecessor_terminal_continuity_ready",
        "predecessor_terminal_continuity_entry_count",
        "checkpoint_cache_ready", "checkpoint_cache_saved",
        "checkpoint_cache_sha256", "checkpoint_cache_key",
        "initial_backfill_ingest", "operator_snapshot_stream_publish_count",
        "operator_snapshot_stream_attempt_count", "operator_snapshot_publish",
    }
    if set(public) - expected:
        raise ValueError("public_cloud_receipt_unreviewed_fields_rejected")
    return public
