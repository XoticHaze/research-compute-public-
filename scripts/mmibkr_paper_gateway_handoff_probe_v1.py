#!/usr/bin/env python3
"""Synthetic, NO-BROKER cross-runner handoff discriminator.

This is NOT an IBKR authentication or Jts-session migration test. It proves
bounded checkpoint integrity, predecessor release, and successor preparation
in distinct GitHub jobs without any account, gateway login, or order actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "mmibkr.synthetic_paper_gateway_handoff.v1"
RECEIPT_SCHEMA = "mmibkr.synthetic_paper_gateway_handoff_receipt.v1"
CHECKPOINT_SCHEMA = "mmibkr.synthetic_paper_gateway_checkpoint.v1"
SHA40 = set("0123456789abcdef")
ALLOWED_PREDECESSOR = {
    "schema", "run_id", "head", "predecessor_job", "checkpoint_sha256",
    "synthetic_only", "account_mode", "read_only_api", "live_orders_enabled",
    "broker_login_attempted", "broker_credentials_used",
    "gateway_authentication_transferred", "predecessor_released",
    "predecessor_gateway_active", "predecessor_execution_owner_active",
    "checkpoint_has_account_data", "checkpoint_has_jts_data",
}
ALLOWED_CHECKPOINT = {"schema", "synthetic_only", "source_sha", "run_id",
                      "strategy_spec_identity", "positions", "open_orders",
                      "broker_session", "account_id", "contains_credentials"}


class GateError(RuntimeError):
    pass


def gate(ok: bool, label: str) -> None:
    if not ok:
        raise GateError(label)


def canonical_bytes(node: dict) -> bytes:
    return (json.dumps(node, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_identity(run_id: str, head: str, job: str) -> None:
    gate(run_id.isdecimal() and 4 <= len(run_id) <= 24, "github_run_id_invalid")
    gate(len(head) == 40 and set(head).issubset(SHA40), "github_head_invalid")
    gate(job in ("predecessor", "successor"), "github_job_not_scoped")


def synthetic_checkpoint(run_id: str, head: str) -> dict:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "synthetic_only": True,
        "source_sha": head,
        "run_id": run_id,
        "strategy_spec_identity": "SYNTHETIC::AMAT::15Min::NO_RUNTIME",
        "positions": [],
        "open_orders": [],
        "broker_session": None,
        "account_id": None,
        "contains_credentials": False,
    }


def validate_checkpoint(node: dict, run_id: str, head: str) -> None:
    gate(isinstance(node, dict) and set(node) == ALLOWED_CHECKPOINT,
         "checkpoint_fields_not_exact")
    gate(node == synthetic_checkpoint(run_id, head),
         "checkpoint_not_exact_synthetic_fixture")


def build_predecessor(run_id: str, head: str, job: str) -> tuple[dict, dict]:
    validate_identity(run_id, head, job)
    gate(job == "predecessor", "predecessor_job_identity_wrong")
    checkpoint = synthetic_checkpoint(run_id, head)
    raw = canonical_bytes(checkpoint)
    receipt = {
        "schema": SCHEMA,
        "run_id": run_id,
        "head": head,
        "predecessor_job": job,
        "checkpoint_sha256": digest(raw),
        "synthetic_only": True,
        "account_mode": "paper",
        "read_only_api": True,
        "live_orders_enabled": False,
        "broker_login_attempted": False,
        "broker_credentials_used": False,
        "gateway_authentication_transferred": False,
        "predecessor_released": True,
        "predecessor_gateway_active": False,
        "predecessor_execution_owner_active": False,
        "checkpoint_has_account_data": False,
        "checkpoint_has_jts_data": False,
    }
    return checkpoint, receipt


def accept_successor(checkpoint_bytes: bytes, receipt: dict,
                     run_id: str, head: str, job: str) -> dict:
    validate_identity(run_id, head, job)
    gate(job == "successor", "successor_job_identity_wrong")
    gate(isinstance(receipt, dict) and set(receipt) == ALLOWED_PREDECESSOR,
         "predecessor_receipt_fields_not_exact")
    gate(receipt.get("schema") == SCHEMA and
         receipt.get("run_id") == run_id and
         receipt.get("head") == head and
         receipt.get("predecessor_job") == "predecessor",
         "predecessor_identity_mismatch")
    gate(receipt.get("checkpoint_sha256") == digest(checkpoint_bytes),
         "predecessor_checkpoint_hash_mismatch")
    checkpoint = json.loads(checkpoint_bytes)
    validate_checkpoint(checkpoint, run_id, head)
    expected_predecessor = build_predecessor(run_id, head, "predecessor")[1]
    gate(receipt == expected_predecessor, "predecessor_not_safely_released")
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "SYNTHETIC_SUCCESSOR_PREPARED",
        "source_head": head,
        "run_id": run_id,
        "predecessor_job": "predecessor",
        "successor_job": job,
        "checkpoint_sha256": digest(checkpoint_bytes),
        "exact_predecessor_checkpoint_restored": True,
        "independent_job_boundary": True,
        "account_mode": "paper",
        "no_broker_credentials": True,
        "broker_login_attempted": False,
        "gateway_authentication_transfer_proven": False,
        "jts_transfer_proven": False,
        "ibc_reauthentication_requirement": "UNTESTED",
        "broker_positions_or_orders_read": False,
        "live_orders_enabled": False,
        "execution_ownership_granted": False,
        "production_handoff_ready": False,
    }


def write_private(path: Path, node: dict) -> None:
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(node))
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("predecessor", "successor"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    a = parser.parse_args()
    try:
        if a.phase == "predecessor":
            cp, receipt = build_predecessor(a.run_id, a.head, a.job)
            write_private(a.checkpoint, cp)
            write_private(a.receipt, receipt)
            print("MMIBKR_SYNTHETIC_PREDECESSOR_RELEASED=1")
            print("GATEWAY_SESSION_TRANSFER_PROVEN=0")
        else:
            gate(a.output is not None, "successor_output_missing")
            result = accept_successor(a.checkpoint.read_bytes(),
                                      json.loads(a.receipt.read_text()),
                                      a.run_id, a.head, a.job)
            write_private(a.output, result)
            print("MMIBKR_CROSS_RUNNER_SYNTHETIC_CHECKPOINT=PASS")
            print("MMIBKR_PREDECESSOR_RELEASE_GUARD=PASS")
            print("MMIBKR_SUCCESSOR_EXECUTION_AUTHORITY=DENIED")
            print("GATEWAY_SESSION_TRANSFER_PROVEN=0")
            print("REAL_PAPER_BROKER_LOGIN_TEST=NOT_ATTEMPTED")
        return 0
    except (GateError, ValueError, OSError, json.JSONDecodeError) as exc:
        label = str(exc) if isinstance(exc, GateError) else "invalid_checkpoint_input"
        print("MMIBKR_HANDOFF_FAIL_CLOSED=" + label)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
