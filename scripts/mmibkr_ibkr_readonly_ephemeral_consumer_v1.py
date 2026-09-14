from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = "mmibkr-ibkr-readonly-ephemeral-x25519-v1"
PLAINTEXT_SCHEMA = "mmibkr-ibkr-readonly-credentials-v1"
HARNESS = "mmibkr_ibkr_readonly_b1_v1"
AUTHORITY = "ibkr_readonly_data_only"
INFO = b"mmibkr-ibkr-readonly-ephemeral-v1"
IMAGE = "ghcr.io/gnzsnz/ib-gateway:10.49.1c"
CONTAINER = "mmibkr-ibkr-readonly-b1"
HOST = "127.0.0.1"
PORT = 4002
CLIENT_ID = 1944


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _aad(run_id: str, recipient_key_id: str) -> bytes:
    return json.dumps(
        {
            "schema": SCHEMA,
            "run_id": str(run_id),
            "authority": AUTHORITY,
            "harness": HARNESS,
            "recipient_key_id": recipient_key_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive(shared: bytes, aad: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=hashlib.sha256(aad).digest(),
        info=INFO,
    ).derive(shared)


def decrypt_credentials(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict[str, str]:
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    required = {
        "schema",
        "run_id",
        "authority",
        "harness",
        "recipient_key_id",
        "sender_public_b64",
        "nonce_b64",
        "ciphertext_b64",
        "plaintext_sha256",
    }
    if set(envelope) != required:
        raise RuntimeError("IBKR envelope field set mismatch")
    if envelope["schema"] != SCHEMA or str(envelope["run_id"]) != str(expected_run_id):
        raise RuntimeError("IBKR envelope run/schema mismatch")
    if envelope["authority"] != AUTHORITY or envelope["harness"] != HARNESS:
        raise RuntimeError("IBKR envelope authority/harness mismatch")

    private_raw = _b64d(private_key_path.read_text(encoding="ascii").strip())
    if len(private_raw) != 32:
        raise RuntimeError("IBKR recipient private key length invalid")
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    recipient_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    recipient_key_id = "sha256:" + hashlib.sha256(recipient_raw).hexdigest()
    if envelope["recipient_key_id"] != recipient_key_id:
        raise RuntimeError("IBKR recipient fingerprint mismatch")

    sender_raw = _b64d(envelope["sender_public_b64"])
    nonce = _b64d(envelope["nonce_b64"])
    if len(sender_raw) != 32 or len(nonce) != 12:
        raise RuntimeError("IBKR sender key/nonce length invalid")
    aad = _aad(str(expected_run_id), recipient_key_id)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
    plaintext = ChaCha20Poly1305(_derive(shared, aad)).decrypt(
        nonce,
        _b64d(envelope["ciphertext_b64"]),
        aad,
    )
    if hashlib.sha256(plaintext).hexdigest() != envelope["plaintext_sha256"]:
        raise RuntimeError("IBKR decrypted payload digest mismatch")

    payload = json.loads(plaintext.decode("utf-8"))
    if set(payload) != {"schema", "username", "password"}:
        raise RuntimeError("IBKR credential payload field set mismatch")
    if payload["schema"] != PLAINTEXT_SCHEMA:
        raise RuntimeError("IBKR credential payload schema mismatch")
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    if not username or not password:
        raise RuntimeError("IBKR credentials missing")
    if any(ch in username or ch in password for ch in ("\r", "\n", "\x00")):
        raise RuntimeError("IBKR credentials contain unsupported control characters")
    return {"username": username, "password": password}


def _run(args: list[str], *, stdout=None, stderr=None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=stdout, stderr=stderr, check=check, text=True)


def _port_open() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=1.0):
            return True
    except OSError:
        return False


def _start_gateway(env_path: Path) -> None:
    _run(["docker", "rm", "-f", CONTAINER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    _run(["docker", "pull", IMAGE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _run(
        [
            "docker", "run", "-d", "--name", CONTAINER,
            "--env-file", str(env_path),
            "-e", "TRADING_MODE=paper",
            "-e", "READ_ONLY_API=yes",
            "-e", "TWS_ACCEPT_INCOMING=accept",
            "-e", "TWOFA_TIMEOUT_ACTION=exit",
            "-e", "EXISTING_SESSION_DETECTED_ACTION=primary",
            "-e", "BYPASS_WARNING=yes",
            "-p", "127.0.0.1:4002:4004",
            IMAGE,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_for_gateway(timeout_sec: int = 240) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _port_open():
            return
        status = _run(
            ["docker", "inspect", "-f", "{{.State.Status}}", CONTAINER],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if status.returncode == 0 and status.stdout.strip() in {"exited", "dead"}:
            raise RuntimeError("IB Gateway container exited before API port became available")
        time.sleep(3)
    raise RuntimeError("IB Gateway API port did not become available before timeout")


def _broker_probe() -> dict:
    from ib_insync import IB, Stock

    ib = IB()
    try:
        ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=20, readonly=True)
        if not ib.isConnected():
            raise RuntimeError("IBKR API connection did not reach connected state")

        server_time = ib.reqCurrentTime()
        accounts = list(ib.managedAccounts())
        summary = list(ib.accountSummary())
        positions = list(ib.positions())
        details = list(ib.reqContractDetails(Stock("SPY", "SMART", "USD")))

        historical = {"attempted": True, "ok": False, "bar_count": 0}
        try:
            ib.reqMarketDataType(4)
            bars = ib.reqHistoricalData(
                Stock("SPY", "SMART", "USD"),
                endDateTime="",
                durationStr="1 D",
                barSizeSetting="1 hour",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=2,
                keepUpToDate=False,
                timeout=20,
            )
            historical = {"attempted": True, "ok": bool(bars), "bar_count": len(bars)}
        except Exception as exc:
            historical = {
                "attempted": True,
                "ok": False,
                "bar_count": 0,
                "error_class": type(exc).__name__,
            }

        tag_names = sorted({str(item.tag) for item in summary if getattr(item, "tag", None)})
        currencies = sorted({str(item.currency) for item in summary if getattr(item, "currency", None)})
        return {
            "connected": True,
            "readonly_client": True,
            "client_id": CLIENT_ID,
            "server_version": int(ib.client.serverVersion()),
            "server_time_utc": server_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if getattr(server_time, "tzinfo", None) else str(server_time),
            "managed_account_count": len(accounts),
            "account_summary_item_count": len(summary),
            "account_summary_tag_count": len(tag_names),
            "account_summary_currency_count": len(currencies),
            "position_count": len(positions),
            "spy_contract_details_count": len(details),
            "historical_probe": historical,
        }
    finally:
        if ib.isConnected():
            ib.disconnect()


def consume(envelope_path: Path, private_key_path: Path, expected_run_id: str) -> dict:
    credentials = decrypt_credentials(envelope_path, private_key_path, expected_run_id)
    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with tempfile.TemporaryDirectory(prefix="mmibkr-ibkr-") as td:
        env_path = Path(td) / "gateway.env"
        env_path.write_text(
            f"TWS_USERID={credentials['username']}\nTWS_PASSWORD={credentials['password']}\n",
            encoding="utf-8",
        )
        os.chmod(env_path, 0o600)
        try:
            _start_gateway(env_path)
            _wait_for_gateway()
            probe = _broker_probe()
        finally:
            env_path.unlink(missing_ok=True)
            _run(["docker", "rm", "-f", CONTAINER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    broker_data_usable = bool(
        probe.get("connected")
        and probe.get("managed_account_count", 0) >= 1
        and probe.get("account_summary_item_count", 0) >= 1
        and probe.get("spy_contract_details_count", 0) >= 1
    )
    return {
        "schema": "mmibkr-ibkr-readonly-b1-receipt-v1",
        "authority": AUTHORITY,
        "harness": HARNESS,
        "run_id": str(expected_run_id),
        "status": "PASS" if broker_data_usable else "FAIL",
        "started_at_utc": started,
        "completed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "broker_data_usable": broker_data_usable,
        "probe": probe,
        "credential_plaintext_emitted": False,
        "account_identifiers_emitted": False,
        "order_api_used": False,
        "broker_mutation": False,
        "live_trading_change": False,
        "gateway_trading_mode": "paper",
        "gateway_read_only_api": True,
        "gateway_image": IMAGE,
        "teardown_requested": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    receipt = consume(Path(args.envelope), Path(args.private_key), args.run_id)
    print("MMIBKR_IBKR_READONLY_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    raise SystemExit(0 if receipt["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
