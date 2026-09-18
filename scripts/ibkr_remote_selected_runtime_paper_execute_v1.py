from __future__ import annotations

"""Persistent selected-runtime paper execution through canonical MM-IBKR routes.

This public worker owns no strategy intent or execution policy. It receives one
MM-authorized selected-runtime command, observes broker state, rechecks the
bounded candidate lease, optionally refreshes only LMT price fields through the
canonical MM quote route, calls the canonical paper submit route once, and then
records post-submit broker truth. Unlike paper_submit_proof it never
automatically cancels or flattens the resulting broker state.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from scripts import ibkr_remote_selected_runtime_paper_proof_v1 as proof_v1

SCHEMA = "mmibkr.remote_selected_runtime_paper_execute_receipt.v1"
GATEWAY_AUTH_SOURCE = "fleet_authority_warm_state"
MODE = "paper_execute"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def validate_fleet_authority_execute_runtime(runtime: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(runtime, Mapping) or runtime.get("schema") != "mmibkr.remote_selected_runtime_materialization.v3":
        raise RuntimeError("selected_runtime_materialization_v3_required")
    if runtime.get("mode") != MODE:
        raise RuntimeError("paper_execute_mode_required")
    if runtime.get("gateway_auth_source") != GATEWAY_AUTH_SOURCE:
        raise RuntimeError("fleet_authority_warm_state_required")
    if runtime.get("gateway_credentials_in_capsule") is not False:
        raise RuntimeError("gateway_credentials_in_capsule_must_be_false")
    if runtime.get("paper_only") is not True or runtime.get("live_trading_change") is not False:
        raise RuntimeError("paper_only_runtime_boundary_required")
    if runtime.get("read_only_api") != "no":
        raise RuntimeError("paper_execute_requires_read_only_api_no")
    cleanup = _mapping(runtime.get("cleanup"))
    expected_cleanup = {
        "cancel_open_order": False,
        "flatten_filled_position": False,
        "require_zero_baseline": False,
        "allow_global_cancel": False,
    }
    if cleanup != expected_cleanup:
        raise RuntimeError("paper_execute_cleanup_contract_mismatch")
    for forbidden in ("gateway_env_path", "ibkr", "username", "password", "tws_userid", "tws_password"):
        if forbidden in runtime:
            raise RuntimeError(f"legacy_gateway_credential_material_rejected:{forbidden}")
    return dict(runtime)


def execute_paper_execute(
    *,
    runtime: Mapping[str, Any],
    request: Mapping[str, Any],
    send,
    run_id: str,
    public_head: str,
) -> dict[str, Any]:
    validated = validate_fleet_authority_execute_runtime(runtime)
    auth = proof_v1._validate_authorized_request(validated, request)
    symbol = auth["symbol"]

    health_status, health = send("GET", "/healthz", timeout=15.0)
    open_status, open_before = send(
        "GET", "/strategy/ibkr-paper-open-orders", params={"symbol": symbol}, timeout=45.0
    )
    pos_status, position_before = proof_v1._flatten_snapshot(send, symbol)
    global_open_before, target_open_before = proof_v1._open_counts(open_before, symbol)
    target_position_before = proof_v1._position_for_symbol(position_before, symbol)

    blockers: list[str] = []
    if health_status != 200 or health.get("ok") is False:
        blockers.append("canonical_runtime_not_healthy")
    if open_status != 200 or open_before.get("ok") is not True:
        blockers.append("open_order_truth_unavailable")
    if pos_status != 200 or position_before.get("ok") is not True:
        blockers.append("position_truth_unavailable")

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "ok": False,
        "status": "BLOCKED_PRE_SUBMIT" if blockers else "SUBMIT_PENDING",
        "github": {"run_id": str(run_id), "public_head": str(public_head)},
        "mmibkr": {
            "head": validated.get("mmibkr_head"),
            "source_archive_sha256": validated.get("source_archive_sha256"),
        },
        "command": {
            "command_id": auth["command_id"],
            "source_ref": auth["source_ref"],
            "runtime_id": auth["runtime_id"],
            "strategy_id": auth["authority"].get("strategy_id"),
            "strategy_spec_digest": auth["strategy_spec_digest"],
            "symbol": symbol,
            "timeframe": auth["authority"].get("timeframe"),
        },
        "preflight": {
            "health_http_status": health_status,
            "open_orders_http_status": open_status,
            "positions_http_status": pos_status,
            "global_open_order_count": global_open_before,
            "target_open_order_count": target_open_before,
            "target_position": target_position_before,
            "zero_baseline_required": False,
            "blockers": blockers,
        },
        "candidate_lease": proof_v1._candidate_transport_lease(auth["payload"]),
        "quote_refresh": {"requested": False, "performed": False, "ok": None},
        "submit": {
            "called": False,
            "http_status": None,
            "ok": False,
            "place_order_called": False,
            "broker_order_placed": False,
            "order_identity": {},
        },
        "post_submit_reconciliation": {},
        "completed_execution_reconciliation": {
            "requested": False,
            "ok": None,
            "read_only": True,
            "broker_mutation_called": False,
        },
        "cleanup": {
            "automatic_cleanup": False,
            "exact_cancel_called": False,
            "flatten_called": False,
            "global_cancel_called": False,
        },
        "authority": {
            "canonical_submit_route": "/strategy/ibkr-paper-order-submit",
            "cloud_strategy_authority": False,
            "cloud_execution_policy_authority": False,
            "direct_broker_client_used": False,
            "automatic_cleanup_authority": False,
            "global_cancel_allowed": False,
            "live_execution_allowed": False,
            "gateway_auth_source": GATEWAY_AUTH_SOURCE,
            "gateway_credentials_in_capsule": False,
        },
    }
    if blockers:
        return receipt

    lease = proof_v1._candidate_transport_lease(auth["payload"])
    receipt["candidate_lease"] = lease
    if lease.get("requested") is True and lease.get("ok") is not True:
        receipt["status"] = "CANDIDATE_LEASE_BLOCKED"
        return receipt

    submit_payload, quote_refresh = proof_v1._jit_refresh_authorized_lmt_payload(
        send=send, payload=auth["payload"]
    )
    receipt["quote_refresh"] = quote_refresh
    if submit_payload is None:
        receipt["status"] = "JIT_QUOTE_REFRESH_BLOCKED"
        return receipt

    submit_status, submit = send(
        "POST", "/strategy/ibkr-paper-order-submit", payload=submit_payload, timeout=120.0
    )
    identity = proof_v1._extract_order_identity(submit, symbol)
    guards = _mapping(submit.get("guards"))
    canonical_runtime_id = str(guards.get("selected_runtime_id") or "").strip()
    authority_mismatch = bool(canonical_runtime_id and canonical_runtime_id != auth["runtime_id"])
    receipt["submit"] = {
        "called": True,
        "http_status": submit_status,
        "ok": submit.get("ok") is True,
        "status": submit.get("status"),
        "place_order_called": bool(submit.get("place_order_called")),
        "broker_order_placed": bool(submit.get("broker_order_placed")),
        "order_identity": identity,
        "canonical_selected_runtime_id": canonical_runtime_id or None,
        "authority_match": not authority_mismatch,
        "blockers": list(submit.get("blockers") or []),
    }
    if authority_mismatch:
        receipt["status"] = "CANONICAL_AUTHORITY_MISMATCH"
        return receipt

    if not bool(submit.get("place_order_called") or submit.get("broker_order_placed")):
        receipt["ok"] = submit_status in {200, 409}
        receipt["status"] = "CANONICAL_SUBMIT_BLOCKED"
        return receipt

    post_open_status, open_after = send(
        "GET", "/strategy/ibkr-paper-open-orders", params={"symbol": symbol}, timeout=45.0
    )
    post_pos_status, position_after = proof_v1._flatten_snapshot(send, symbol)
    global_open_after, target_open_after = proof_v1._open_counts(open_after, symbol)
    target_position_after = proof_v1._position_for_symbol(position_after, symbol)
    post_ok = bool(
        post_open_status == 200
        and open_after.get("ok") is True
        and post_pos_status == 200
        and position_after.get("ok") is True
    )
    receipt["post_submit_reconciliation"] = {
        "open_orders_http_status": post_open_status,
        "positions_http_status": post_pos_status,
        "global_open_order_count": global_open_after,
        "target_open_order_count": target_open_after,
        "target_position": target_position_after,
        "broker_truth_available": post_ok,
        "position_delta": target_position_after - target_position_before,
        "state_retained_for_strategy": True,
    }

    evidence_ok = True
    if receipt["submit"].get("broker_order_placed") is True and identity:
        evidence_status, evidence = send(
            "POST",
            "/strategy/ibkr-paper-completed-executions",
            payload={
                "runtime_id": auth["runtime_id"],
                "symbol": symbol,
                "identities": [{
                    "role": "persistent_submit",
                    "order_id": identity.get("order_id"),
                    "perm_id": identity.get("perm_id"),
                    "order_ref": identity.get("order_ref"),
                }],
            },
            timeout=90.0,
        )
        evidence_ok = bool(
            evidence_status == 200
            and evidence.get("ok") is True
            and evidence.get("read_only") is True
            and evidence.get("broker_mutation_called") is False
            and evidence.get("cloud_strategy_authority") is False
            and evidence.get("cloud_execution_policy_authority") is False
            and evidence.get("live_execution_allowed") is False
            and evidence.get("global_cancel_allowed") is False
        )
        receipt["completed_execution_reconciliation"] = {
            **dict(evidence),
            "requested": True,
            "http_status": evidence_status,
            "ok": evidence_ok,
            "read_only": evidence.get("read_only") is True,
            "broker_mutation_called": evidence.get("broker_mutation_called") is True,
        }

    receipt["ok"] = bool(post_ok and evidence_ok)
    if not post_ok:
        receipt["status"] = "PAPER_EXECUTE_POST_SUBMIT_TRUTH_INCOMPLETE"
    elif not evidence_ok:
        receipt["status"] = "PAPER_EXECUTE_EXECUTION_EVIDENCE_INCOMPLETE"
    else:
        receipt["status"] = "PAPER_EXECUTE_RECONCILED"
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
    request = json.loads(Path(runtime["request_path"]).read_text(encoding="utf-8"))
    receipt = execute_paper_execute(
        runtime=runtime,
        request=request,
        send=proof_v1._request_sender(args.base_url),
        run_id=args.run_id,
        public_head=args.public_head,
    )
    Path(args.receipt).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("IBKR_REMOTE_SELECTED_RUNTIME_PAPER_EXECUTE=" + json.dumps({
        "ok": receipt.get("ok"),
        "status": receipt.get("status"),
        "run_id": args.run_id,
        "command_id": (receipt.get("command") or {}).get("command_id"),
        "runtime_id": (receipt.get("command") or {}).get("runtime_id"),
        "symbol": (receipt.get("command") or {}).get("symbol"),
        "broker_order_placed": (receipt.get("submit") or {}).get("broker_order_placed"),
        "automatic_cleanup": False,
        "global_cancel_called": False,
        "live_execution_allowed": False,
    }, sort_keys=True))
    raise SystemExit(0 if receipt.get("ok") else 2)


if __name__ == "__main__":
    main()
