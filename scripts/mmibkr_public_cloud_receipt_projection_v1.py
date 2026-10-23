from __future__ import annotations

"""Bounded public projection of an MM-IBKR cloud owner receipt.

The canonical daemon and private checkpoint remain unchanged. Only this
projection is eligible for public GitHub receipt storage. The caller constructs
the original receipt from a private runtime session; NEVER publish that original
receipt, unbounded nested cycle state, roll state, or raw failure messages.
"""

from typing import Any
import re
from scripts.mmibkr_cloud_session_acceptance_v1 import (
    EXPECTED_INITIAL_BACKFILL_RUN_ID,
    EXPECTED_INITIAL_BACKFILL_ARTIFACT,
    CHECKPOINT_CACHE_PREFIX,
)

SCHEMA = "mmibkr.selected_runtime_cloud_session_receipt.v2"

# A top-level key allowlist is insufficient: two admitted keys carry nested
# dictionaries into a public GitHub receipt. Never pass arbitrary child keys
# or free-form values through those objects.
_PUBLISH_BOOL_KEYS = frozenset({
    "durable_readback_verified", "account_identifiers_included",
    "credentials_included", "tokens_included", "private_source_included",
    "execution_authority_included", "broker_mutation_authority",
    "live_execution_allowed",
})
_PUBLISH_COUNT_KEYS = frozenset({"runtime_count", "positions_count"})
_PUBLISH_OPTIONAL_BOOL_KEYS = _PUBLISH_BOOL_KEYS - {"durable_readback_verified"}
_BACKFILL_COUNT_KEYS = frozenset({
    "amat_target_rows", "aph_target_rows", "mnq_source_rows", "mnq_target_rows",
})
_BACKFILL_BOOL_KEYS = frozenset({
    "ready", "performed_this_run", "broker_action",
    "runtime_execution_contract_mutated", "live_execution_allowed",
    "preowner_checkpoint_saved",
})
_BACKFILL_TOKEN_RULES = {
    "public_run_id": r"[0-9]{1,24}",
    "artifact_name": r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}",
    "preowner_checkpoint_sha256": r"[a-fA-F0-9]{64}",
    "preowner_checkpoint_cache_key": r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}",
}


def _checked_nested_public_field(key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("public_cloud_receipt_nested_type_rejected:" + key)
    if key == "operator_snapshot_publish":
        allowed = _PUBLISH_BOOL_KEYS | _PUBLISH_COUNT_KEYS | {"status"}
    elif key == "initial_backfill_ingest":
        allowed = _BACKFILL_BOOL_KEYS | _BACKFILL_COUNT_KEYS | set(_BACKFILL_TOKEN_RULES)
    else:
        raise ValueError("public_cloud_receipt_nested_contract_unknown")
    if set(value) - allowed:
        raise ValueError("public_cloud_receipt_unreviewed_nested_field:" + key)
    for field, item in value.items():
        if field in _PUBLISH_BOOL_KEYS and key == "operator_snapshot_publish":
            if type(item) is not bool and not (field in _PUBLISH_OPTIONAL_BOOL_KEYS and item is None):
                raise ValueError("public_cloud_receipt_nested_value_type_rejected:" + field)
        elif field in _PUBLISH_COUNT_KEYS and key == "operator_snapshot_publish":
            if item is not None and (type(item) is not int or item < 0):
                raise ValueError("public_cloud_receipt_nested_value_type_rejected:" + field)
        elif field == "status" and key == "operator_snapshot_publish":
            if type(item) is not str or item not in {"accepted", "not_accepted", "blocked", "failed", "not_run", "not_available_for_runtime_source", "rejected"}:
                raise ValueError("public_cloud_receipt_nested_value_rejected:status")
        elif field in _BACKFILL_BOOL_KEYS and key == "initial_backfill_ingest":
            if type(item) is not bool:
                raise ValueError("public_cloud_receipt_nested_value_type_rejected:" + field)
        elif field in _BACKFILL_COUNT_KEYS and key == "initial_backfill_ingest":
            if item is not None and (type(item) is not int or item < 0):
                raise ValueError("public_cloud_receipt_nested_value_type_rejected:" + field)
        elif field in _BACKFILL_TOKEN_RULES and key == "initial_backfill_ingest":
            if item is not None and (type(item) is not str or not re.fullmatch(_BACKFILL_TOKEN_RULES[field], item)):
                raise ValueError("public_cloud_receipt_nested_value_rejected:" + field)
    if key == "initial_backfill_ingest":
        for field, expected in (
            ("public_run_id", EXPECTED_INITIAL_BACKFILL_RUN_ID),
            ("artifact_name", EXPECTED_INITIAL_BACKFILL_ARTIFACT),
        ):
            if value.get(field) is not None and value[field] != expected:
                raise ValueError("public_cloud_receipt_nested_identity_rejected:" + field)
    return dict(value)


# The same public receipt must not launder arbitrary values through an
# already-admitted scalar field. These are the actual workflow producer types;
# checkpoint digests/keys are bounded references, not raw private state.
_PUBLIC_BOOL_FIELDS = frozenset({
    "ok", "session_accepted", "checkpoint_handoff_ready",
    "private_repository_token_used", "live_execution_allowed",
    "public_strategy_authority", "public_execution_policy_authority",
    "credentials_included", "account_state_included", "positions_included",
    "orders_included", "checkpoint_restored",
    "expected_predecessor_checkpoint_match",
    "predecessor_terminal_continuity_required",
    "predecessor_terminal_continuity_ready", "checkpoint_cache_ready",
    "checkpoint_cache_saved",
})
_PUBLIC_OPTIONAL_BOOL_FIELDS = frozenset({"checkpoint_handoff_ready"})
_PUBLIC_FALSE_ONLY_FIELDS = frozenset({
    "private_repository_token_used", "live_execution_allowed",
    "public_strategy_authority", "public_execution_policy_authority",
    "credentials_included", "account_state_included", "positions_included",
    "orders_included",
})
_PUBLIC_COUNT_FIELDS = frozenset({
    "cycle_count", "success_count", "failure_count",
    "predecessor_terminal_continuity_entry_count",
    "operator_snapshot_stream_publish_count",
    "operator_snapshot_stream_attempt_count",
})
_CHECKPOINT_KEY_PATTERN = r"mmibkr-selected-runtime-cloud-checkpoint-v1-[A-Za-z0-9_.-]{1,200}"
_PUBLIC_TOKEN_RULES = {
    "run_id": r"[0-9]{1,24}",
    "public_head": r"[a-fA-F0-9]{40}",
    "private_head": r"[a-fA-F0-9]{40}",
    "checkpoint_restored_sha256": r"[a-fA-F0-9]{64}",
    "checkpoint_restored_cache_key": _CHECKPOINT_KEY_PATTERN,
    "expected_predecessor_checkpoint_cache_key": _CHECKPOINT_KEY_PATTERN,
    "expected_predecessor_checkpoint_sha256": r"[a-fA-F0-9]{64}",
    "checkpoint_cache_sha256": r"[a-fA-F0-9]{64}",
    "checkpoint_cache_key": _CHECKPOINT_KEY_PATTERN,
}


def _check_public_scalar_fields(public: dict[str, Any]) -> None:
    excluded = {"schema", "status", "last_cycle", "futures_roll_maintenance",
                "initial_backfill_ingest", "operator_snapshot_publish"}
    allowed = _PUBLIC_BOOL_FIELDS | _PUBLIC_COUNT_FIELDS | set(_PUBLIC_TOKEN_RULES) | {"source_transport"}
    if set(public) - excluded - allowed:
        raise ValueError("public_cloud_receipt_unreviewed_scalar_field_rejected")
    for key, value in public.items():
        if key in _PUBLIC_BOOL_FIELDS:
            if value is None and key in _PUBLIC_OPTIONAL_BOOL_FIELDS:
                continue
            if type(value) is not bool:
                raise ValueError("public_cloud_receipt_scalar_type_rejected:" + key)
            if key in _PUBLIC_FALSE_ONLY_FIELDS and value is not False:
                raise ValueError("public_cloud_receipt_scalar_authority_rejected:" + key)
        elif key in _PUBLIC_COUNT_FIELDS:
            if value is not None and (type(value) is not int or not 0 <= value <= 1000000000):
                raise ValueError("public_cloud_receipt_scalar_count_rejected:" + key)
        elif key in _PUBLIC_TOKEN_RULES:
            if value is not None and (type(value) is not str or not re.fullmatch(_PUBLIC_TOKEN_RULES[key], value)):
                raise ValueError("public_cloud_receipt_scalar_token_rejected:" + key)
        elif key == "source_transport":
            if value != "fleet_authority_exact_sha_encrypted_snapshot_vault":
                raise ValueError("public_cloud_receipt_scalar_transport_rejected")


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
    for nested in ("operator_snapshot_publish", "initial_backfill_ingest"):
        public[nested] = _checked_nested_public_field(nested, receipt.get(nested))
    # Validate each scalar before checking cross-field identity. Invalid run_id
    # must fail at its own typed allowlist gate, not via a derived key regex.
    _check_public_scalar_fields(public)
    preowner = public["initial_backfill_ingest"].get("preowner_checkpoint_cache_key")
    if preowner is not None:
        run_id = public.get("run_id")
        pattern = re.escape(CHECKPOINT_CACHE_PREFIX) + re.escape(str(run_id)) + r"-[a-f0-9]{3,40}-initial-backfill-preowner"
        if type(run_id) is not str or not re.fullmatch(pattern, preowner):
            raise ValueError("public_cloud_receipt_nested_identity_rejected:preowner_checkpoint_cache_key")
    return public
