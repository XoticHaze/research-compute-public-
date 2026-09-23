from __future__ import annotations

"""Maintenance-safe Operator Snapshot refresh for paper-account hygiene.

The selected-runtime owner remains held. This helper obtains a bounded,
encrypted account-only B1 snapshot, requires exact broker-position identity
parity with the already operator-approved snapshot, preserves the frozen
strategy ownership rows exactly, and emits a newly timestamped presentation
projection. It owns no strategy, order, cancel, flatten, or live authority.
"""

import argparse
import base64
import copy
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PUBLIC_REPO = "XoticHaze/research-compute-public-"
B1_WORKFLOW = "ibkr-cloudflare-readonly-b1-r1.yml"
B1_REF = "ibkr-b1-authority-v1"
EXCHANGE_REF = "rendezvous-exchange"
MODE = "paper_account_snapshot"
SNAPSHOT_SCHEMA = "mmibkr.ibkr_account_snapshot.v1"
ENVELOPE_SCHEMA = "ibkr-account-snapshot-return-x25519-v1"
AUTHORITY = "mm_ibkr_paper_runtime"
HARNESS = "mmibkr_b1_account_snapshot_v1"
RETURN_INFO = b"mmibkr-b1-account-snapshot-return-v1"
HOLD_SCHEMA = "mmibkr.selected_runtime_maintenance_hold.v1"
HOLD_REASON = "paper_account_hygiene_679"
OWNERSHIP_SOURCE = "selected_runtime_strategy_inventory_v1"
OPERATOR_SCHEMA = "mmibkr.cloud_operator_snapshot.v1"
ACCOUNT_TAGS = {
    "NetLiquidation": "net_liquidation",
    "AvailableFunds": "available_funds",
    "BuyingPower": "buying_power",
    "GrossPositionValue": "gross_position_value",
    "MaintMarginReq": "maintenance_margin",
    "ExcessLiquidity": "excess_liquidity",
}


def _api_json(url: str, *, token: str, method: str = "GET", payload: Mapping[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
    req = Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mmibkr-maintenance-snapshot-refresh-v1",
        },
    )
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            return int(response.status), json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        raw = exc.read()
        try:
            node = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            node = {"message": raw.decode("utf-8", errors="replace")}
        return int(exc.code), node


def _resolve_b1_head(token: str) -> str:
    status, node = _api_json(
        f"https://api.github.com/repos/{PUBLIC_REPO}/git/ref/heads/{B1_REF}",
        token=token,
    )
    head = str(((node.get("object") or {}).get("sha") or "")).strip().lower()
    if status != 200 or len(head) != 40:
        raise RuntimeError("maintenance snapshot B1 authority head unavailable")
    return head


def _recipient() -> tuple[x25519.X25519PrivateKey, str, str]:
    private = x25519.X25519PrivateKey.generate()
    raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    encoded = base64.b64encode(raw).decode("ascii")
    key_id = "sha256:" + hashlib.sha256(raw).hexdigest()
    return private, encoded, key_id


def _dispatch(token: str, *, nonce: str, recipient_b64: str, recipient_key_id: str) -> tuple[str, datetime]:
    expected_head = _resolve_b1_head(token)
    status, body = _api_json(
        f"https://api.github.com/repos/{PUBLIC_REPO}/actions/workflows/{B1_WORKFLOW}/dispatches",
        token=token,
        method="POST",
        payload={
            "ref": B1_REF,
            "inputs": {
                "mode": MODE,
                "dispatch_nonce": nonce,
                "symbols": "AMAT",
                "contracts_json": "{}",
                "bar_requests_json": "",
                "snapshot_not_before_utc": "",
                "include_quotes": False,
                "read_return_recipient_b64": recipient_b64,
                "read_return_recipient_key_id": recipient_key_id,
            },
        },
    )
    if status != 204:
        raise RuntimeError(f"maintenance snapshot B1 dispatch failed HTTP {status}: {body.get('message','')}")
    return expected_head, datetime.now(timezone.utc)


def _discover(token: str, *, nonce: str, expected_head: str, started: datetime, timeout_sec: int = 240) -> str:
    target = f"IBKR B1 {MODE} {nonce}"
    deadline = time.monotonic() + max(1, int(timeout_sec))
    while time.monotonic() < deadline:
        status, node = _api_json(
            f"https://api.github.com/repos/{PUBLIC_REPO}/actions/workflows/{B1_WORKFLOW}/runs?event=workflow_dispatch&branch={quote(B1_REF,safe='')}&per_page=20",
            token=token,
        )
        if status != 200:
            raise RuntimeError("maintenance snapshot B1 run discovery failed")
        matches = []
        for run in node.get("workflow_runs") or []:
            if not isinstance(run, Mapping):
                continue
            if str(run.get("head_sha") or "").lower() != expected_head:
                continue
            if str(run.get("display_title") or run.get("name") or "") != target:
                continue
            created = datetime.fromisoformat(str(run.get("created_at") or "").replace("Z", "+00:00"))
            if created >= started.replace(microsecond=0):
                matches.append(str(run.get("id") or ""))
        matches = [value for value in matches if value.isdigit()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError("maintenance snapshot B1 nonce collision")
        time.sleep(2)
    raise RuntimeError("maintenance snapshot B1 run not discoverable")


def _content_bytes(token: str, path: str) -> bytes | None:
    status, node = _api_json(
        f"https://api.github.com/repos/{PUBLIC_REPO}/contents/{quote(path)}?ref={quote(EXCHANGE_REF,safe='')}",
        token=token,
    )
    if status == 404:
        return None
    if status != 200 or node.get("encoding") != "base64":
        raise RuntimeError(f"maintenance snapshot return read failed:{status}:{path}")
    return base64.b64decode(str(node.get("content") or "").replace("\n", ""))


def _aad(*, run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": ENVELOPE_SCHEMA,
            "run_id": str(run_id),
            "authority": AUTHORITY,
            "harness": HARNESS,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fetch_decrypt(token: str, *, run_id: str, private_key: x25519.X25519PrivateKey, recipient_key_id: str, expected_head: str, timeout_sec: int = 900) -> dict[str, Any]:
    envelope_path = f"rendezvous/returns/{run_id}/ibkr-account-snapshot-envelope.json"
    deadline = time.monotonic() + max(1, int(timeout_sec))
    envelope = None
    while time.monotonic() < deadline:
        raw = _content_bytes(token, envelope_path)
        if raw:
            envelope = json.loads(raw.decode("utf-8"))
            break
        status, run = _api_json(
            f"https://api.github.com/repos/{PUBLIC_REPO}/actions/runs/{run_id}",
            token=token,
        )
        if status == 200 and run.get("status") == "completed":
            raise RuntimeError(
                "maintenance snapshot B1 terminated before encrypted return:"
                + str(run.get("conclusion") or "")
            )
        time.sleep(3)
    if not isinstance(envelope, Mapping):
        raise RuntimeError("maintenance snapshot encrypted return did not arrive")
    if envelope.get("schema") != ENVELOPE_SCHEMA or str(envelope.get("run_id")) != str(run_id):
        raise RuntimeError("maintenance snapshot envelope identity mismatch")
    if envelope.get("authority") != AUTHORITY or envelope.get("harness") != HARNESS:
        raise RuntimeError("maintenance snapshot envelope authority mismatch")
    if envelope.get("recipient_key_id") != recipient_key_id:
        raise RuntimeError("maintenance snapshot recipient mismatch")

    parts = []
    for node in envelope.get("chunks") or []:
        if not isinstance(node, Mapping):
            raise RuntimeError("maintenance snapshot chunk manifest invalid")
        path = str(node.get("path") or "")
        if not path.startswith(f"rendezvous/returns/{run_id}/"):
            raise RuntimeError("maintenance snapshot chunk path rejected")
        raw = _content_bytes(token, path)
        if raw is None:
            raise RuntimeError("maintenance snapshot chunk missing")
        text = raw.decode("ascii")
        if hashlib.sha256(text.encode("ascii")).hexdigest() != str(node.get("sha256") or ""):
            raise RuntimeError("maintenance snapshot chunk digest mismatch")
        parts.append(text)
    ciphertext = base64.b64decode("".join(parts).encode("ascii"), validate=True)
    if hashlib.sha256(ciphertext).hexdigest() != str(envelope.get("ciphertext_sha256") or ""):
        raise RuntimeError("maintenance snapshot ciphertext digest mismatch")
    sender_public = base64.b64decode(str(envelope.get("sender_public_b64") or "").encode("ascii"), validate=True)
    nonce = base64.b64decode(str(envelope.get("nonce_b64") or "").encode("ascii"), validate=True)
    aad = _aad(run_id=run_id, recipient_key_id=recipient_key_id)
    shared = private_key.exchange(x25519.X25519PublicKey.from_public_bytes(sender_public))
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=RETURN_INFO,
    ).derive(shared)
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    if hashlib.sha256(plaintext).hexdigest() != str(envelope.get("plaintext_sha256") or ""):
        raise RuntimeError("maintenance snapshot plaintext digest mismatch")
    snapshot = json.loads(plaintext.decode("utf-8"))
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise RuntimeError("maintenance account snapshot schema mismatch")
    if str(snapshot.get("run_id") or "") != str(run_id):
        raise RuntimeError("maintenance account snapshot run mismatch")
    if str(snapshot.get("public_head") or "").lower() != expected_head:
        raise RuntimeError("maintenance account snapshot authority head mismatch")
    if snapshot.get("trading_mode") != "paper" or snapshot.get("read_only") is not True:
        raise RuntimeError("maintenance account snapshot paper/read-only boundary violated")
    if snapshot.get("account_identifiers_included") is not False:
        raise RuntimeError("maintenance account snapshot identifier boundary violated")
    caps = snapshot.get("capabilities") if isinstance(snapshot.get("capabilities"), Mapping) else {}
    for required in ("account_state", "positions", "open_orders"):
        if caps.get(required) is not True:
            raise RuntimeError("maintenance account snapshot capability missing:" + required)
    for forbidden in ("historical_market_data","quotes","completed_executions","order_submission","order_cancel","global_cancel","live_execution"):
        if caps.get(forbidden) is not False:
            raise RuntimeError("maintenance account snapshot forbidden capability:" + forbidden)
    return dict(snapshot)


def _position_index(rows: Any) -> dict[str, tuple[int, str, float]]:
    out: dict[str, tuple[int, str, float]] = {}
    if not isinstance(rows, list):
        raise RuntimeError("maintenance snapshot position rows missing")
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise RuntimeError("maintenance snapshot position row invalid")
        contract = raw.get("contract") if isinstance(raw.get("contract"), Mapping) else {}
        symbol = str(contract.get("symbol") or contract.get("localSymbol") or raw.get("symbol") or "").strip().upper()
        con_id = int(contract.get("conId") or raw.get("conId") or 0)
        sec_type = str(contract.get("secType") or raw.get("secType") or "").strip().upper()
        qty = float(raw.get("position"))
        if not symbol or con_id <= 0 or sec_type not in {"STK","ETF"} or abs(qty) <= 1e-12:
            raise RuntimeError("maintenance snapshot position identity invalid")
        if symbol in out:
            raise RuntimeError("maintenance snapshot duplicate position symbol:" + symbol)
        out[symbol] = (con_id, sec_type, qty)
    return out


def _validate_hold(path: Path) -> None:
    node = json.loads(path.read_text(encoding="utf-8"))
    if node.get("schema") != HOLD_SCHEMA or node.get("enabled") is not True:
        raise RuntimeError("selected-runtime maintenance hold is not enabled")
    if str(node.get("reason") or "") != HOLD_REASON:
        raise RuntimeError("selected-runtime maintenance hold reason mismatch")
    if (
        node.get("broker_mutation_authority") is not False
        or node.get("live_execution_allowed") is not False
    ):
        raise RuntimeError("selected-runtime maintenance hold authority boundary violated")


def _account_summary(rows: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    currencies: dict[str, str] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        label = ACCOUNT_TAGS.get(str(row.get("tag") or ""))
        if not label:
            continue
        raw = row.get("value")
        try:
            parsed = float(raw)
            values[label] = parsed
        except (TypeError, ValueError):
            values[label] = str(raw or "")
        currency = str(row.get("currency") or "").strip()
        if currency:
            currencies[label] = currency
    if currencies:
        values["currencies"] = currencies
    return values


def refresh_snapshot(stale: Mapping[str, Any], fresh: Mapping[str, Any], *, expected_source_sha: str, stale_sha256: str) -> dict[str, Any]:
    if stale.get("schema") != OPERATOR_SCHEMA or stale.get("mode") != "paper" or stale.get("live_enabled") is not False:
        raise RuntimeError("maintenance refresh stale Operator Snapshot rejected")
    runtime = stale.get("runtime") if isinstance(stale.get("runtime"), Mapping) else {}
    if str(runtime.get("source_sha") or runtime.get("source_ref") or "").lower() != expected_source_sha.lower():
        raise RuntimeError("maintenance refresh runtime source mismatch")
    account = stale.get("account") if isinstance(stale.get("account"), Mapping) else {}
    if int(account.get("open_orders_count") or 0) != 0:
        raise RuntimeError("maintenance refresh stale snapshot has open orders")

    runtimes = [row for row in stale.get("runtimes") or [] if isinstance(row, Mapping)]
    if not runtimes:
        raise RuntimeError("maintenance refresh selected-runtime rows missing")
    for row in runtimes:
        runtime_id = str(row.get("runtime_id") or "unknown")
        position = row.get("position") if isinstance(row.get("position"), Mapping) else {}
        if position.get("ownership_attributed") is not True:
            raise RuntimeError("maintenance refresh ownership attribution incomplete:" + runtime_id)
        if str(position.get("ownership_source") or "") != OWNERSHIP_SOURCE:
            raise RuntimeError("maintenance refresh ownership source mismatch:" + runtime_id)
        if abs(float(position.get("position") or 0.0)) > 1e-12:
            raise RuntimeError("maintenance refresh refuses non-flat strategy inventory:" + runtime_id)

    try:
        fresh_open_order_count = int(fresh.get("open_order_count"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("maintenance refresh fresh broker open order count invalid") from exc
    if fresh_open_order_count != 0:
        raise RuntimeError("maintenance refresh fresh broker snapshot has open orders")
    stale_positions = _position_index(stale.get("positions"))
    fresh_positions = _position_index(fresh.get("positions"))
    if stale_positions != fresh_positions:
        raise RuntimeError("maintenance refresh broker position identity changed during hold")
    if int(fresh.get("position_count") or -1) != len(fresh_positions):
        raise RuntimeError("maintenance refresh fresh broker position count mismatch")

    generated = str(fresh.get("generated_at_utc") or "")
    instant = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise RuntimeError("maintenance refresh generated_at_utc invalid")
    age = (datetime.now(timezone.utc) - instant.astimezone(timezone.utc)).total_seconds()
    if age < -120 or age > 300:
        raise RuntimeError("maintenance refresh broker snapshot freshness rejected")

    out = copy.deepcopy(dict(stale))
    out["generated_at_utc"] = instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    out["positions"] = copy.deepcopy(list(fresh.get("positions") or []))
    out["account"] = {
        **_account_summary(fresh.get("account_summary")),
        "positions_count": len(fresh_positions),
        "open_orders_count": 0,
    }
    execution = dict(out.get("execution") or {})
    execution["open_orders_count"] = 0
    execution["live_trading_enabled"] = False
    out["execution"] = execution
    runtime_out = dict(runtime)
    runtime_out["cloud_owner"] = "maintenance_hold"
    runtime_out["broker"] = "connected"
    runtime_out["boundary_run_id"] = str(fresh.get("run_id") or "")
    runtime_out["public_authority_head"] = str(fresh.get("public_head") or "")
    runtime_out["data_continuity"] = "maintenance_hold"
    out["runtime"] = runtime_out
    out["maintenance_refresh"] = {
        "schema": "mmibkr.operator_snapshot_maintenance_refresh.v1",
        "reason": HOLD_REASON,
        "broker_snapshot_run_id": str(fresh.get("run_id") or ""),
        "broker_snapshot_public_head": str(fresh.get("public_head") or ""),
        "previous_operator_snapshot_sha256": stale_sha256,
        "previous_generated_at_utc": stale.get("generated_at_utc"),
        "runtime_source_sha": expected_source_sha.lower(),
        "exact_broker_position_identity_match": True,
        "strategy_inventory_frozen_flat": True,
        "open_orders_clean": True,
        "broker_mutation": False,
        "live_execution_allowed": False,
    }
    return out


def execute_refresh(*, token: str, stale_path: Path, hold_path: Path, expected_source_sha: str, output: Path) -> dict[str, Any]:
    _validate_hold(hold_path)
    raw = stale_path.read_bytes()
    stale = json.loads(raw.decode("utf-8"))
    private, recipient_b64, recipient_key_id = _recipient()
    nonce = secrets.token_hex(8)
    expected_head, started = _dispatch(
        token,
        nonce=nonce,
        recipient_b64=recipient_b64,
        recipient_key_id=recipient_key_id,
    )
    run_id = _discover(
        token,
        nonce=nonce,
        expected_head=expected_head,
        started=started,
    )
    fresh = _fetch_decrypt(
        token,
        run_id=run_id,
        private_key=private,
        recipient_key_id=recipient_key_id,
        expected_head=expected_head,
    )
    refreshed = refresh_snapshot(
        stale,
        fresh,
        expected_source_sha=expected_source_sha,
        stale_sha256=hashlib.sha256(raw).hexdigest(),
    )
    output.write_text(json.dumps(refreshed, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return {
        "schema": "mmibkr.operator_snapshot_maintenance_refresh_receipt.v1",
        "ok": True,
        "b1_run_id": run_id,
        "b1_public_head": expected_head,
        "position_count": len(refreshed.get("positions") or []),
        "open_order_count": int((refreshed.get("account") or {}).get("open_orders_count") or 0),
        "runtime_count": len(refreshed.get("runtimes") or []),
        "generated_at_utc": refreshed.get("generated_at_utc"),
        "strategy_inventory_frozen_flat": True,
        "exact_broker_position_identity_match": True,
        "broker_mutation": False,
        "live_execution_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--maintenance-hold", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    token = str(os.environ.get("GH_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("GH_TOKEN required")
    receipt = execute_refresh(
        token=token,
        stale_path=args.snapshot,
        hold_path=args.maintenance_hold,
        expected_source_sha=str(args.expected_source_sha).strip().lower(),
        output=args.output,
    )
    print("MMIBKR_MAINTENANCE_SNAPSHOT_REFRESH=" + json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
