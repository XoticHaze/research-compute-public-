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


def evaluate(
    node: dict,
    *,
    require_checkpoint_restored: bool,
    previous_receipt: dict | None = None,
    expected_private_sha: str = CANONICAL_PRIVATE_SHA,
    expected_runtime_count: int = EXPECTED_RUNTIME_COUNT,
    expected_public_sha: str | None = None,
    allow_legacy_v1: bool = False,
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
            )
            checks["predecessor_receipt_accepted"] = previous_acceptance["accepted"]
            checks["predecessor_checkpoint_identity"] = (
                previous_receipt.get("checkpoint_cache_saved") is True
                and node.get("checkpoint_restored_sha256")
                    == previous_receipt.get("checkpoint_cache_sha256")
                and node.get("checkpoint_restored_cache_key")
                    == previous_receipt.get("checkpoint_cache_key")
            )

    accepted = all(checks.values())
    return {
        "schema": "mmibkr.cloud_session_acceptance.v1",
        "accepted": accepted,
        "mode": "steady_state" if require_checkpoint_restored else "first_post_fix",
        "run_id": str(node.get("run_id") or ""),
        "public_head": node.get("public_head"),
        "private_head": node.get("private_head"),
        "expected_private_head": expected_private_sha,
        "expected_runtime_count": expected_runtime_count,
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
        choices=("first-post-fix", "steady-state"),
        default="first-post-fix",
    )
    parser.add_argument("--previous-receipt", type=Path)
    parser.add_argument("--expected-public-sha")
    parser.add_argument("--expected-private-sha", default=CANONICAL_PRIVATE_SHA)
    parser.add_argument("--expected-runtime-count", type=int, default=EXPECTED_RUNTIME_COUNT)
    parser.add_argument(
        "--allow-legacy-v1",
        action="store_true",
        help="Allow historical v1 receipts for explicit legacy inspection only.",
    )
    args = parser.parse_args()

    previous = load_receipt(args.previous_receipt) if args.previous_receipt else None
    if args.mode == "steady-state" and previous is None:
        raise SystemExit("--previous-receipt is required in steady-state mode")
    result = evaluate(
        load_receipt(args.receipt),
        require_checkpoint_restored=args.mode == "steady-state",
        previous_receipt=previous,
        expected_private_sha=args.expected_private_sha,
        expected_runtime_count=args.expected_runtime_count,
        expected_public_sha=args.expected_public_sha,
        allow_legacy_v1=args.allow_legacy_v1,
    )
    print("MMIBKR_CLOUD_RECEIPT_ACCEPTANCE=" + json.dumps(result, sort_keys=True))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
