from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "mmibkr.selected_runtime_cloud_session_receipt.v1"
CANONICAL_PRIVATE_SHA = "d81df85788ebb6be6d4d69b9b9a537be96f16507"
EXPECTED_RUNTIME_COUNT = 3


def load_receipt(path: Path) -> dict:
    node = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError("MMIBKR cloud session receipt root must be an object")
    return node


def evaluate(
    node: dict,
    *,
    require_checkpoint_restored: bool,
    expected_private_sha: str = CANONICAL_PRIVATE_SHA,
    expected_runtime_count: int = EXPECTED_RUNTIME_COUNT,
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

    checks = {
        "schema": node.get("schema") == SCHEMA,
        "session_accepted": node.get("session_accepted") is True and node.get("ok") is True,
        "private_head": str(node.get("private_head") or "").lower() == expected_private_sha.lower(),
        "live_disabled": node.get("live_execution_allowed") is False,
        "no_account_state": node.get("account_state_included") is False,
        "no_position_payload": node.get("positions_included") is False,
        "no_order_payload": node.get("orders_included") is False,
        "no_credentials": node.get("credentials_included") is False,
        "operator_publish_accepted": publish.get("status") == "accepted",
        "operator_runtime_count": publish.get("runtime_count") == expected_runtime_count,
        "operator_positions_count_reported": isinstance(publish.get("positions_count"), int)
            and publish.get("positions_count") >= 0,
        "operator_safety": safety_ok,
        "checkpoint_cache_ready": node.get("checkpoint_cache_ready") is True,
        "checkpoint_cache_saved": node.get("checkpoint_cache_saved") is True,
    }
    if require_checkpoint_restored:
        checks["checkpoint_restored"] = node.get("checkpoint_restored") is True

    accepted = all(checks.values())
    return {
        "schema": "mmibkr.cloud_session_acceptance.v1",
        "accepted": accepted,
        "mode": "steady_state" if require_checkpoint_restored else "first_post_fix",
        "run_id": str(node.get("run_id") or ""),
        "private_head": node.get("private_head"),
        "expected_private_head": expected_private_sha,
        "expected_runtime_count": expected_runtime_count,
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
    parser.add_argument("--expected-private-sha", default=CANONICAL_PRIVATE_SHA)
    parser.add_argument("--expected-runtime-count", type=int, default=EXPECTED_RUNTIME_COUNT)
    args = parser.parse_args()

    result = evaluate(
        load_receipt(args.receipt),
        require_checkpoint_restored=args.mode == "steady-state",
        expected_private_sha=args.expected_private_sha,
        expected_runtime_count=args.expected_runtime_count,
    )
    print("MMIBKR_CLOUD_RECEIPT_ACCEPTANCE=" + json.dumps(result, sort_keys=True))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
