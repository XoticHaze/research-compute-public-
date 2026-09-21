from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

SNAPSHOT_SCHEMA = "mmibkr.cloud_operator_snapshot.v1"
OIDC_AUDIENCE = "mmibkr-operator-console"
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


def _object(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def load_snapshot(path: Path) -> dict[str, Any]:
    body = path.read_bytes()
    if not body or len(body) > MAX_SNAPSHOT_BYTES:
        raise RuntimeError("operator_snapshot_size_rejected")
    node = json.loads(body.decode("utf-8"))
    if not isinstance(node, dict):
        raise RuntimeError("operator_snapshot_object_required")
    validate_snapshot(node)
    return node


def validate_snapshot(node: Mapping[str, Any]) -> None:
    privacy = _object(node.get("privacy"))
    authority = _object(node.get("authority"))
    runtimes = node.get("runtimes")
    positions = node.get("positions")
    if node.get("schema") != SNAPSHOT_SCHEMA:
        raise RuntimeError("operator_snapshot_schema_mismatch")
    if node.get("mode") != "paper" or node.get("live_enabled") is not False:
        raise RuntimeError("operator_snapshot_paper_only_required")
    if not isinstance(runtimes, list) or not isinstance(positions, list):
        raise RuntimeError("operator_snapshot_collections_required")
    if len(runtimes) > 100 or len(positions) > 500:
        raise RuntimeError("operator_snapshot_collection_size_rejected")
    if (
        privacy.get("private_operator_state") is not True
        or privacy.get("account_identifiers_included") is not False
        or privacy.get("credentials_included") is not False
        or privacy.get("tokens_included") is not False
        or privacy.get("private_source_included") is not False
        or privacy.get("execution_authority_included") is not False
    ):
        raise RuntimeError("operator_snapshot_privacy_contract_failed")
    if (
        authority.get("presentation_projection_only") is not True
        or authority.get("strategy_authority") is not False
        or authority.get("execution_policy_authority") is not False
        or authority.get("sizing_authority") is not False
        or authority.get("broker_mutation_authority") is not False
        or authority.get("live_execution_allowed") is not False
    ):
        raise RuntimeError("operator_snapshot_authority_contract_failed")


def build_oidc_url(raw_url: str) -> str:
    parsed = urlparse(str(raw_url or ""))
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError("operator_snapshot_oidc_url_invalid")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["audience"] = OIDC_AUDIENCE
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query),
        parsed.fragment,
    ))


def validate_publish_receipt(
    receipt: Mapping[str, Any],
    *,
    runtime_count: int,
    positions_count: int,
) -> dict[str, Any]:
    legacy_runtime_count = receipt.get("runtime_count")
    received_runtime_count = receipt.get("received_runtime_count")
    stored_runtime_count = receipt.get("stored_runtime_count")
    if (
        receipt.get("ok") is not True
        or receipt.get("schema") != "mmibkr.operator_console_publish_receipt.v1"
        or receipt.get("durable_readback_verified") is not True
        or received_runtime_count != runtime_count
        or legacy_runtime_count != runtime_count
        or not isinstance(stored_runtime_count, int)
        or stored_runtime_count < runtime_count
        or stored_runtime_count > 100
        or receipt.get("positions_count") != positions_count
        or receipt.get("credentials_included") is not False
        or receipt.get("tokens_included") is not False
        or receipt.get("broker_mutation_authority") is not False
        or receipt.get("live_execution_allowed") is not False
    ):
        raise RuntimeError("operator_snapshot_publish_receipt_rejected")
    return {
        "status": "accepted",
        "stored_at_utc": receipt.get("stored_at_utc"),
        "source_sha": receipt.get("source_sha"),
        "received_runtime_count": runtime_count,
        "runtime_count": stored_runtime_count,
        "positions_count": positions_count,
        "runtime_merge_applied": receipt.get("runtime_merge_applied") is True,
        "durable_readback_verified": True,
        "account_identifiers_included": False,
        "credentials_included": False,
        "tokens_included": False,
        "private_source_included": False,
        "execution_authority_included": False,
        "broker_mutation_authority": False,
        "live_execution_allowed": False,
    }


def publish_snapshot(
    *,
    snapshot_path: Path,
    operator_url: str,
    caller_run_id: str,
    output_path: Path | None = None,
    marker_mode: str = "final",
) -> dict[str, Any]:
    if not str(caller_run_id).isdigit():
        raise RuntimeError("operator_snapshot_caller_run_id_invalid")
    base = str(operator_url or "").rstrip("/")
    parsed_base = urlparse(base)
    if parsed_base.scheme != "https" or not parsed_base.netloc:
        raise RuntimeError("operator_snapshot_operator_url_invalid")

    node = load_snapshot(snapshot_path)
    body = snapshot_path.read_bytes()
    runtime_count = len(node["runtimes"])
    positions_count = len(node["positions"])

    oidc_url = build_oidc_url(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", ""))
    request_token = str(os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN") or "")
    if not request_token:
        raise RuntimeError("operator_snapshot_oidc_request_token_missing")

    oidc_req = Request(
        oidc_url,
        headers={
            "Authorization": "Bearer " + request_token,
            "Accept": "application/json",
        },
    )
    with urlopen(oidc_req, timeout=20) as response:
        oidc = json.load(response)
    token = str(oidc.get("value") or "")
    if token.count(".") != 2:
        raise RuntimeError("operator_snapshot_oidc_token_invalid")

    req = Request(
        base + "/v1/operator-snapshot",
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-MMIBKR-Caller-Run-Id": caller_run_id,
            "User-Agent": "mmibkr-cloud-operator-publisher-v1",
        },
    )
    with urlopen(req, timeout=30) as response:
        status = int(response.status)
        receipt = json.load(response)
    if status != 201:
        raise RuntimeError("operator_snapshot_publish_http_rejected")

    result = validate_publish_receipt(
        receipt,
        runtime_count=runtime_count,
        positions_count=positions_count,
    )
    result["snapshot_sha256"] = hashlib.sha256(body).hexdigest()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp = output_path.with_suffix(output_path.suffix + ".tmp")
        temp.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(output_path)
        try:
            output_path.chmod(0o600)
        except OSError:
            pass

    stored_runtime_count = int(result["runtime_count"])
    if marker_mode == "stream":
        print("MMIBKR_OPERATOR_SNAPSHOT_STREAM_PUBLISH=accepted")
        print("MMIBKR_OPERATOR_SNAPSHOT_STREAM_RECEIVED_RUNTIME_COUNT=" + str(runtime_count))
        print("MMIBKR_OPERATOR_SNAPSHOT_STREAM_RUNTIME_COUNT=" + str(stored_runtime_count))
        print(
            "MMIBKR_OPERATOR_SNAPSHOT_STREAM_RUNTIME_MERGE_APPLIED="
            + ("1" if result["runtime_merge_applied"] else "0")
        )
        print("MMIBKR_OPERATOR_SNAPSHOT_STREAM_POSITIONS_COUNT=" + str(positions_count))
        print("MMIBKR_OPERATOR_SNAPSHOT_STREAM_DURABLE_READBACK_VERIFIED=1")
    else:
        print("MMIBKR_OPERATOR_SNAPSHOT_PUBLISH=accepted")
        print("MMIBKR_OPERATOR_SNAPSHOT_RECEIVED_RUNTIME_COUNT=" + str(runtime_count))
        print("MMIBKR_OPERATOR_SNAPSHOT_RUNTIME_COUNT=" + str(stored_runtime_count))
        print(
            "MMIBKR_OPERATOR_SNAPSHOT_RUNTIME_MERGE_APPLIED="
            + ("1" if result["runtime_merge_applied"] else "0")
        )
        print("MMIBKR_OPERATOR_SNAPSHOT_POSITIONS_COUNT=" + str(positions_count))
        print("MMIBKR_OPERATOR_SNAPSHOT_DURABLE_READBACK_VERIFIED=1")
        print("MMIBKR_OPERATOR_SNAPSHOT_ACCOUNT_IDENTIFIERS_INCLUDED=0")
        print("MMIBKR_OPERATOR_SNAPSHOT_CREDENTIALS_INCLUDED=0")
        print("MMIBKR_OPERATOR_SNAPSHOT_TOKENS_INCLUDED=0")
        print("MMIBKR_OPERATOR_SNAPSHOT_PRIVATE_SOURCE_INCLUDED=0")
        print("MMIBKR_OPERATOR_SNAPSHOT_EXECUTION_AUTHORITY_INCLUDED=0")
        print("MMIBKR_OPERATOR_SNAPSHOT_BROKER_MUTATION_AUTHORITY=0")
        print("MMIBKR_OPERATOR_SNAPSHOT_LIVE_EXECUTION_ALLOWED=0")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--operator-url", required=True)
    parser.add_argument("--caller-run-id", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=("final", "stream"), default="final")
    args = parser.parse_args()

    publish_snapshot(
        snapshot_path=args.snapshot,
        operator_url=args.operator_url,
        caller_run_id=args.caller_run_id,
        output_path=args.output,
        marker_mode=args.mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
