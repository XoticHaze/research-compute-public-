from __future__ import annotations

"""Credential-free Fleet Authority gate for the selected-runtime paper proof.

V2 is the only executor entrypoint intended for the promoted cloud workflow. It
accepts only the command-capsule-v2 materialization, proves Gateway credentials
are absent from the capsule, then delegates broker work to the already-validated
HTTP-only v1 executor. Strategy and execution-policy authority remain MM-IBKR.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import ibkr_remote_selected_runtime_paper_proof_v1 as v1

RUNTIME_SCHEMA = "mmibkr.remote_selected_runtime_materialization.v3"
GATEWAY_AUTH_SOURCE = "fleet_authority_warm_state"


def validate_fleet_authority_runtime(runtime: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(runtime, Mapping):
        raise RuntimeError("fleet_authority_runtime_object_required")
    if runtime.get("schema") != RUNTIME_SCHEMA:
        raise RuntimeError("credential_free_command_materialization_v3_required")
    if runtime.get("mode") != v1.MODE:
        raise RuntimeError("paper_submit_proof_runtime_required")
    if runtime.get("gateway_auth_source") != GATEWAY_AUTH_SOURCE:
        raise RuntimeError("fleet_authority_warm_state_required")
    if runtime.get("gateway_credentials_in_capsule") is not False:
        raise RuntimeError("gateway_credentials_in_capsule_must_be_false")
    if runtime.get("paper_only") is not True or runtime.get("live_trading_change") is not False:
        raise RuntimeError("paper_only_runtime_boundary_required")
    if runtime.get("read_only_api") != "no":
        raise RuntimeError("paper_submit_proof_requires_read_only_api_no")
    for forbidden in ("gateway_env_path", "ibkr", "username", "password", "tws_userid", "tws_password"):
        if forbidden in runtime:
            raise RuntimeError(f"legacy_gateway_credential_material_rejected:{forbidden}")
    return dict(runtime)


def execute_paper_proof_v2(
    *,
    runtime: Mapping[str, Any],
    request: Mapping[str, Any],
    send,
    run_id: str,
    public_head: str,
    executor: Callable[..., dict[str, Any]] = v1.execute_paper_proof,
) -> dict[str, Any]:
    validated = validate_fleet_authority_runtime(runtime)
    receipt = executor(
        runtime=validated,
        request=request,
        send=send,
        run_id=run_id,
        public_head=public_head,
    )
    if not isinstance(receipt, dict):
        raise RuntimeError("paper_proof_executor_receipt_object_required")
    authority = receipt.get("authority") if isinstance(receipt.get("authority"), dict) else {}
    authority.update({
        "gateway_auth_source": GATEWAY_AUTH_SOURCE,
        "gateway_credentials_in_capsule": False,
        "credential_free_command_capsule_required": True,
        "legacy_credential_capsule_allowed": False,
    })
    receipt["authority"] = authority
    receipt["executor_contract"] = "mmibkr.remote_selected_runtime_paper_proof_executor.v2"
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--public-head", required=True)
    args = parser.parse_args()

    runtime = json.loads(Path(args.runtime).read_text(encoding="utf-8"))
    validate_fleet_authority_runtime(runtime)
    request = json.loads(Path(runtime["request_path"]).read_text(encoding="utf-8"))
    receipt = execute_paper_proof_v2(
        runtime=runtime,
        request=request,
        send=v1._request_sender(args.base_url),
        run_id=args.run_id,
        public_head=args.public_head,
    )
    Path(args.receipt).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("IBKR_REMOTE_SELECTED_RUNTIME_PAPER_PROOF_V2=" + json.dumps({
        "ok": receipt.get("ok"),
        "status": receipt.get("status"),
        "run_id": args.run_id,
        "gateway_auth_source": GATEWAY_AUTH_SOURCE,
        "gateway_credentials_in_capsule": False,
        "command_id": (receipt.get("command") or {}).get("command_id"),
        "runtime_id": (receipt.get("command") or {}).get("runtime_id"),
        "symbol": (receipt.get("command") or {}).get("symbol"),
        "global_cancel_called": False,
        "live_execution_allowed": False,
    }, sort_keys=True))
    raise SystemExit(0 if receipt.get("ok") else 2)


if __name__ == "__main__":
    main()
