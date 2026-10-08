from __future__ import annotations

import argparse
import json
from pathlib import Path

LEGACY_SCHEMA = "mmibkr.selected_runtime_cloud_session_receipt.v1"
SCHEMA = "mmibkr.selected_runtime_cloud_session_receipt.v2"
CANONICAL_PRIVATE_SHA = "d81df85788ebb6be6d4d69b9b9a537be96f16507"
EXPECTED_RUNTIME_COUNT = 3
EXPECTED_INITIAL_BACKFILL_RUN_ID = "35407829303"
EXPECTED_INITIAL_BACKFILL_ARTIFACT = "ibkr-cloudflare-readonly-b1-35407829303"
CHECKPOINT_CACHE_PREFIX = "mmibkr-selected-runtime-cloud-checkpoint-v1-"


def is_hex(value: object, length: int) -> bool:
    text = str(value or "").lower()
    return len(text) == length and all(ch in "0123456789abcdef" for ch in text)


def is_sha256(value: object) -> bool:
    return is_hex(value, 64)


def load_receipt(path: Path) -> dict:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError("MMIBKR cloud session receipt root must be an object")
    return node


def _boundary_canary_checks(
    node: dict,
    publish: dict,
    expected_runtime_count: int,
    stream_publish_count: object,
    stream_attempt_count: object,
) -> dict[str, bool]:
    """One successful evaluated boundary is not full 3-runtime readiness.

    The canonical MM snapshot contains *evaluated runtime_results*, not all
    selected bindings. A single-cycle canary may legitimately publish one
    runtime and only the final durable snapshot (no 30s streaming poll).
    This tier never establishes full selected-universe or streaming coverage.
    """
    count = publish.get("runtime_count")
    received = publish.get("received_runtime_count")
    runtime_ids = publish.get("runtime_ids")
    cycle = node.get("last_cycle")
    if not isinstance(cycle, dict):
        cycle = {}
    boundary_key = str(cycle.get("boundary_key") or "")
    boundary_runtime_id = boundary_key.rsplit("|", 1)[-1] if "|" in boundary_key else ""
    return {
        "canary_one_completed_cycle": (
            type(node.get("cycle_count")) is int
            and node["cycle_count"] == 1
            and type(node.get("success_count")) is int
            and node["success_count"] == 1
            and type(node.get("failure_count")) is int
            and node["failure_count"] == 0
            and cycle.get("ok") is True
            and cycle.get("broker_action") is False
            and node.get("checkpoint_handoff_ready") is True
        ),
        "canary_source_transport_exact": (
            node.get("source_transport")
            == "fleet_authority_exact_sha_encrypted_snapshot_vault"
        ),
        "canary_no_public_or_private_authority_leak": (
            node.get("public_strategy_authority") is False
            and node.get("public_execution_policy_authority") is False
            and node.get("private_repository_token_used") is False
        ),
        "canary_runtime_subset_not_full_coverage": (
            type(count) is int
            and type(received) is int
            and type(expected_runtime_count) is int
            and 1 <= received <= count <= expected_runtime_count
        ),
        "canary_exact_boundary_runtime_identity": (
            isinstance(runtime_ids, list)
            and type(received) is int
            and len(runtime_ids) == received
            and all(
                isinstance(runtime_id, str)
                and runtime_id
                and len(runtime_id) <= 80
                and all(c.isascii() and (c.isalnum() or c == "_") for c in runtime_id)
                for runtime_id in runtime_ids
            )
            and len(set(runtime_ids)) == len(runtime_ids)
            and boundary_runtime_id in runtime_ids
        ),
        "canary_exact_boundary_run_identity": (
            isinstance(publish.get("boundary_run_id"), str)
            and bool(publish["boundary_run_id"])
            and publish["boundary_run_id"] == str(cycle.get("boundary_run_id") or "")
        ),
        "canary_stream_or_final_delivery": (
            type(stream_publish_count) is int
            and type(stream_attempt_count) is int
            and 0 <= stream_publish_count <= stream_attempt_count
            and (
                stream_publish_count >= 1
                or (
                    stream_attempt_count == 0
                    and publish.get("status") == "accepted"
                    and publish.get("durable_readback_verified") is True
                )
            )
        ),
    }


def evaluate(
    node: dict,
    *,
    require_checkpoint_restored: bool,
    previous_receipt: dict | None = None,
    expected_private_sha: str = CANONICAL_PRIVATE_SHA,
    expected_runtime_count: int = EXPECTED_RUNTIME_COUNT,
    expected_public_sha: str | None = None,
    allow_legacy_v1: bool = False,
    boundary_canary: bool = False,
    expected_runtime_ids: list[str] | None = None,
) -> dict:
    publish = node.get("operator_snapshot_publish")
    if not isinstance(publish, dict):
        publish = {}

    safety_keys = (
        "account_identifiers_included",
        "credentials_included",
        "tokens_included",
        "private_source_included",
        "execution_authority_included",
        "broker_mutation_authority",
        "live_execution_allowed",
    )
    safety_ok = all(publish.get(key) is False for key in safety_keys)

    stream_publish_count = node.get("operator_snapshot_stream_publish_count")
    stream_attempt_count = node.get("operator_snapshot_stream_attempt_count")
    backfill = node.get("initial_backfill_ingest")
    if not isinstance(backfill, dict):
        backfill = {}
    receipt_schema = str(node.get("schema") or "")
    schema_ok = receipt_schema == SCHEMA or (
        allow_legacy_v1 and receipt_schema == LEGACY_SCHEMA
    )
    strict_backfill = receipt_schema == SCHEMA

    checks = {
        "schema": schema_ok,
        "session_accepted": node.get("session_accepted") is True and node.get("ok") is True,
        "public_head_reported": is_hex(node.get("public_head"), 40),
        "private_head": str(node.get("private_head") or "").lower() == expected_private_sha.lower(),
        "live_disabled": node.get("live_execution_allowed") is False,
        "no_account_state": node.get("account_state_included") is False,
        "no_position_payload": node.get("positions_included") is False,
        "no_order_payload": node.get("orders_included") is False,
        "no_credentials": node.get("credentials_included") is False,
        "operator_stream_publish": isinstance(stream_publish_count, int)
            and stream_publish_count >= 1,
        "operator_stream_attempts": isinstance(stream_attempt_count, int)
            and stream_attempt_count >= stream_publish_count,
        "operator_publish_accepted": publish.get("status") == "accepted",
        "operator_runtime_count": publish.get("runtime_count") == expected_runtime_count,
        "operator_positions_count_reported": isinstance(publish.get("positions_count"), int)
            and publish.get("positions_count") >= 0,
        "operator_durable_readback": publish.get("durable_readback_verified") is True,
        "operator_safety": safety_ok,
        "checkpoint_cache_ready": node.get("checkpoint_cache_ready") is True,
        "checkpoint_cache_saved": node.get("checkpoint_cache_saved") is True,
    }
    if boundary_canary:
        # Keep the strict full-readiness gate unchanged for normal sessions.
        checks.pop("operator_stream_publish")
        checks.pop("operator_runtime_count")
        checks.update(_boundary_canary_checks(
            node, publish, expected_runtime_count,
            stream_publish_count, stream_attempt_count,
        ))
    if not boundary_canary:
        # Stored runtime_count may be a merge of stale prior-session rows.
        # Full readiness requires all expected runtimes in this final source
        # snapshot, not merely a count read back from the operator console.
        fresh_received = publish.get("received_runtime_count")
        fresh_ids = publish.get("runtime_ids")
        last_cycle = node.get("last_cycle") if isinstance(node.get("last_cycle"), dict) else {}
        boundary_key = str(last_cycle.get("boundary_key") or "")
        boundary_runtime = boundary_key.rsplit("|", 1)[-1] if "|" in boundary_key else ""
        checks["strict_fresh_received_runtime_identity"] = (
            type(fresh_received) is int
            and fresh_received == expected_runtime_count
            and type(publish.get("runtime_count")) is int
            and publish.get("runtime_count") == fresh_received
            and publish.get("runtime_merge_applied") is False
            and isinstance(fresh_ids, list)
            and len(fresh_ids) == fresh_received
            and all(isinstance(x, str) and x and len(x) <= 80
                    and all(c.isascii() and (c.isalnum() or c == "_") for c in x)
                    for x in fresh_ids)
            and len(set(fresh_ids)) == len(fresh_ids)
            and boundary_runtime in fresh_ids
            and isinstance(publish.get("boundary_run_id"), str)
            and bool(publish.get("boundary_run_id"))
            and publish.get("boundary_run_id") == str(last_cycle.get("boundary_run_id") or "")
        )
    if not boundary_canary:
        # The source-backed expected set comes from the exact private MM
        # selected_runtime_universe, not from the publisher's claimed count.
        ids = publish.get("runtime_ids")
        expected = expected_runtime_ids
        checks["strict_canonical_selected_runtime_set"] = (
            isinstance(ids, list) and isinstance(expected, list)
            and len(ids) == expected_runtime_count
            and len(expected) == expected_runtime_count
            and all(isinstance(x, str) and x and len(x) <= 80 for x in ids)
            and all(isinstance(x, str) and x and len(x) <= 80 for x in expected)
            and len(set(expected)) == len(expected)
            and set(ids) == set(expected)
        )
    if strict_backfill:
        checks.update({
            "initial_backfill_ready": backfill.get("ready") is True,
            "initial_backfill_public_run": (
                str(backfill.get("public_run_id") or "") == EXPECTED_INITIAL_BACKFILL_RUN_ID
            ),
            "initial_backfill_artifact": (
                backfill.get("artifact_name") == EXPECTED_INITIAL_BACKFILL_ARTIFACT
            ),
            "initial_backfill_no_broker_action": backfill.get("broker_action") is False,
            "initial_backfill_no_execution_mutation": (
                backfill.get("runtime_execution_contract_mutated") is False
            ),
            "initial_backfill_live_disabled": backfill.get("live_execution_allowed") is False,
            "initial_backfill_preowner_checkpoint_saved": (
                backfill.get("preowner_checkpoint_saved") is True
            ),
            "initial_backfill_preowner_checkpoint_sha256": (
                is_sha256(backfill.get("preowner_checkpoint_sha256"))
            ),
            "initial_backfill_preowner_checkpoint_cache_key": (
                isinstance(backfill.get("preowner_checkpoint_cache_key"), str)
                and backfill.get("preowner_checkpoint_cache_key").startswith(
                    CHECKPOINT_CACHE_PREFIX
                )
            ),
        })
    if expected_public_sha is not None:
        checks["public_head_expected"] = (
            str(node.get("public_head") or "").lower() == expected_public_sha.lower()
        )

    expected_predecessor_key = str(
        node.get("expected_predecessor_checkpoint_cache_key") or ""
    ).strip()
    expected_predecessor_sha256 = str(
        node.get("expected_predecessor_checkpoint_sha256") or ""
    ).strip().lower()
    expected_predecessor_declared = bool(
        expected_predecessor_key or expected_predecessor_sha256
    )
    if expected_predecessor_declared:
        checks["expected_predecessor_identity_reported"] = (
            expected_predecessor_key.startswith(CHECKPOINT_CACHE_PREFIX)
            and is_sha256(expected_predecessor_sha256)
        )
        checks["expected_predecessor_restore_match"] = (
            node.get("expected_predecessor_checkpoint_match") is True
            and node.get("checkpoint_restored") is True
            and node.get("checkpoint_restored_cache_key") == expected_predecessor_key
            and node.get("checkpoint_restored_sha256") == expected_predecessor_sha256
        )

    predecessor_terminal_required = (
        node.get("predecessor_terminal_continuity_required") is True
    )
    if predecessor_terminal_required:
        entry_count = node.get("predecessor_terminal_continuity_entry_count")
        checks["predecessor_terminal_continuity_ready"] = (
            node.get("predecessor_terminal_continuity_ready") is True
            and isinstance(entry_count, int)
            and entry_count >= 1
        )
        checks["predecessor_terminal_continuity_has_exact_restore"] = (
            expected_predecessor_declared
            and node.get("expected_predecessor_checkpoint_match") is True
            and node.get("checkpoint_restored") is True
        )

    if require_checkpoint_restored:
        checks["checkpoint_restored"] = node.get("checkpoint_restored") is True
        checks["checkpoint_restored_identity_reported"] = (
            is_sha256(node.get("checkpoint_restored_sha256"))
            and isinstance(node.get("checkpoint_restored_cache_key"), str)
            and bool(node.get("checkpoint_restored_cache_key"))
        )
        checks["checkpoint_saved_identity_reported"] = (
            is_sha256(node.get("checkpoint_cache_sha256"))
            and isinstance(node.get("checkpoint_cache_key"), str)
            and bool(node.get("checkpoint_cache_key"))
        )
        if previous_receipt is not None:
            previous_acceptance = evaluate(
                previous_receipt,
                require_checkpoint_restored=False,
                expected_private_sha=expected_private_sha,
                expected_runtime_count=expected_runtime_count,
                allow_legacy_v1=allow_legacy_v1,
                expected_runtime_ids=expected_runtime_ids,
            )
            checks["predecessor_receipt_accepted"] = previous_acceptance["accepted"]
            checks["predecessor_checkpoint_identity"] = (
                previous_receipt.get("checkpoint_cache_saved") is True
                and node.get("checkpoint_restored_sha256")
                    == previous_receipt.get("checkpoint_cache_sha256")
                and node.get("checkpoint_restored_cache_key")
                    == previous_receipt.get("checkpoint_cache_key")
            )

    # The exact public publisher forwards Cloudflare's durable readback
    # source_sha from snapshot.runtime.source_sha. A stored/merged receipt
    # must not claim current private source merely from node.private_head.
    published_source_sha = publish.get("source_sha")
    checks["operator_published_source_matches_private_head"] = (
        isinstance(published_source_sha, str)
        and is_hex(published_source_sha, 40)
        and published_source_sha.lower() == expected_private_sha.lower()
    )
    accepted = all(checks.values())
    return {
        "schema": "mmibkr.cloud_session_acceptance.v1",
        "accepted": accepted,
        "mode": "boundary_canary" if boundary_canary else ("steady_state" if require_checkpoint_restored else "first_post_fix"),
        "run_id": str(node.get("run_id") or ""),
        "public_head": node.get("public_head"),
        "private_head": node.get("private_head"),
        "expected_private_head": expected_private_sha,
        "expected_runtime_count": expected_runtime_count,
        "full_runtime_readiness": accepted and not boundary_canary,
        "runtime_coverage": "BOUNDARY_SUBSET_ONLY" if boundary_canary else "FULL_EXPECTED",
        "streaming_proven": type(stream_publish_count) is int and stream_publish_count >= 1,
        "production_admission": False,
        "receipt_contract": "v2_backfill_checkpoint_strict" if receipt_schema == SCHEMA else "legacy_v1",
        "operator_snapshot_stream_publish_count": stream_publish_count,
        "operator_snapshot_stream_attempt_count": stream_attempt_count,
        "operator_snapshot_publish": {
            "status": publish.get("status"),
            "runtime_count": publish.get("runtime_count"),
            "positions_count": publish.get("positions_count"),
        },
        "checks": checks,
        "live_execution_allowed": False,
        "broker_mutation_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument(
        "--mode",
        choices=("first-post-fix", "steady-state", "boundary-canary"),
        default="first-post-fix",
    )
    parser.add_argument("--previous-receipt", type=Path)
    parser.add_argument("--expected-public-sha")
    parser.add_argument("--expected-private-sha", default=CANONICAL_PRIVATE_SHA)
    parser.add_argument("--expected-runtime-count", type=int, default=EXPECTED_RUNTIME_COUNT)
    parser.add_argument("--expected-runtime-ids-file", type=Path)
    parser.add_argument(
        "--allow-legacy-v1",
        action="store_true",
        help="Allow historical v1 receipts for explicit legacy inspection only.",
    )
    args = parser.parse_args()

    previous = load_receipt(args.previous_receipt) if args.previous_receipt else None
    if args.mode == "steady-state" and previous is None:
        raise SystemExit("--previous-receipt is required in steady-state mode")
    expected_runtime_ids = None
    if args.expected_runtime_ids_file is not None:
        source_bound = json.loads(args.expected_runtime_ids_file.read_text(encoding="utf-8"))
        if not isinstance(source_bound, dict) or source_bound.get("source_sha") != args.expected_private_sha:
            raise SystemExit("expected_runtime_ids_source_identity_mismatch")
        expected_runtime_ids = source_bound.get("runtime_ids")
    result = evaluate(
        load_receipt(args.receipt),
        require_checkpoint_restored=args.mode == "steady-state",
        previous_receipt=previous,
        expected_private_sha=args.expected_private_sha,
        expected_runtime_count=args.expected_runtime_count,
        expected_public_sha=args.expected_public_sha,
        allow_legacy_v1=args.allow_legacy_v1,
        boundary_canary=args.mode == "boundary-canary",
        expected_runtime_ids=expected_runtime_ids,
    )
    print("MMIBKR_CLOUD_RECEIPT_ACCEPTANCE=" + json.dumps(result, sort_keys=True))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
