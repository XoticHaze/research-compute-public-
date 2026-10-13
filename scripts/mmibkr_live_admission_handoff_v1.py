#!/usr/bin/env python3
"""Sanitized live Gateway admission-only handoff. No Jts or credential transport.

Predecessor must actually authenticate and read the account/positions/orders;
successor may validate the prior receipt, but never receives order authority.
This is a conservative, fail-closed cross-VM seam for the existing Fleet seal.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path

SCHEMA = "mmibkr.live_readonly_admission_handoff.v1"
EXPECTED_IMAGE = "ghcr.io/code-hustler-ft3d/ibg-controller@sha256:5db4074ec952d130937afc3bb926ee97f115d09f7f46676eb16d98c2805572b5"
SOURCE = "46fcdf26cf84603b305a3ea20bcd3cf28c67bc0b"
ALLOWED = {"schema", "run_id", "head", "source_sha", "image", "mode",
           "account_read_verified", "positions_read_verified",
           "open_orders_read_verified", "execution_owner_started",
           "order_mutation", "gateway_released", "gateway_session_persisted",
           "jts_included", "credentials_included", "ready_for_order_ownership"}
HEX40 = set("0123456789abcdef")


class HandoffError(Exception):
    pass


def require(ok: bool, label: str):
    if not ok:
        raise HandoffError(label)


def validate_run(run_id: str, head: str):
    require(run_id.isdecimal() and 4 <= len(run_id) <= 24, "github_run_invalid")
    require(len(head) == 40 and set(head).issubset(HEX40), "github_head_invalid")


def record(run_id: str, head: str) -> dict:
    validate_run(run_id, head)
    return {
        "schema": SCHEMA, "run_id": run_id, "head": head,
        "source_sha": SOURCE, "image": EXPECTED_IMAGE,
        "mode": "production_live_readonly_admission",
        "account_read_verified": True,
        "positions_read_verified": True,
        "open_orders_read_verified": True,
        "execution_owner_started": False,
        "order_mutation": False,
        "gateway_released": True,
        "gateway_session_persisted": False,
        "jts_included": False,
        "credentials_included": False,
        "ready_for_order_ownership": False,
    }


def accept(previous: dict, *, current_run: str, current_head: str):
    validate_run(current_run, current_head)
    require(isinstance(previous, dict) and set(previous) == ALLOWED,
            "predecessor_receipt_not_exact")
    run_id, head = previous.get("run_id"), previous.get("head")
    require(isinstance(run_id, str) and isinstance(head, str),
            "predecessor_id_missing")
    validate_run(run_id, head)
    require(run_id != current_run, "predecessor_run_not_distinct")
    require(previous == record(run_id, head), "predecessor_not_readonly_released")
    return {
        "schema": SCHEMA,
        "predecessor_run": run_id,
        "current_run": current_run,
        "predecessor_receipt_sha256": hashlib.sha256(
            (json.dumps(previous,sort_keys=True,separators=(",",":"))+"\n").encode()
        ).hexdigest(),
        "safe_for_new_readonly_gateway": True,
        "gateway_authentication_migration_proven": False,
        "live_order_ownership_granted": False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("write","accept"))
    p.add_argument("--run-id",required=True)
    p.add_argument("--head",required=True)
    p.add_argument("--path",required=True,type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    try:
        if args.action=="write":
            node=record(args.run_id,args.head)
            args.path.parent.mkdir(parents=True,exist_ok=True)
            args.path.write_text(json.dumps(node,sort_keys=True)+"\n")
            os.chmod(args.path,0o600)
            print("MMIBKR_LIVE_ADMISSION_HANDOFF_RELEASED=1")
            print("MMIBKR_LIVE_JTS_EXPORTED=0")
            print("MMIBKR_LIVE_ORDERS_SUBMITTED=0")
        else:
            require(args.output is not None,"output_required")
            node=json.loads(args.path.read_text())
            accepted=accept(node,current_run=args.run_id,current_head=args.head)
            args.output.write_text(json.dumps(accepted,sort_keys=True)+"\n")
            os.chmod(args.output,0o600)
            print("MMIBKR_LIVE_ADMISSION_PREDECESSOR_ACCEPTED=1")
            print("MMIBKR_LIVE_ORDER_AUTHORITY=DENIED")
        return 0
    except (HandoffError,ValueError,OSError,TypeError) as exc:
        reason=str(exc) if isinstance(exc,HandoffError) else "invalid_receipt_input"
        print("MMIBKR_LIVE_ADMISSION_HANDOFF_FAIL_CLOSED="+reason)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
