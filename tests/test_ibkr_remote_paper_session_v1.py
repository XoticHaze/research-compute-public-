import base64
import hashlib
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ibkr_remote_paper_session_v1 as mod


def runtime():
    return {
        "mode": "session_reconcile",
        "mmibkr_repository": "XoticHaze/mm-IBKR",
        "mmibkr_head": "a" * 40,
        "source_archive_sha256": "b" * 64,
        "paper_only": True,
        "read_only_api": "yes",
        "host_dependency": False,
        "live_trading_change": False,
        "encrypted_return_requested": True,
    }


def open_orders():
    return {
        "ok": True,
        "status": "read_completed",
        "contract_version": "ibkr_paper_open_order_status_refresh_13z36",
        "open_order_count": 1,
        "unresolved_open_order_count": 1,
        "account_identity": {
            "managed_account_count": 1,
            "du_account_count": 1,
            "selected_account_is_paper_du": True,
            "selected_account_redacted": "DU...1234",
        },
        "orders": [{"symbol": "AAA", "status": "Submitted", "action": "BUY", "orderId": 42, "permId": 77, "orderRef": "r1", "unresolved": True}],
    }


def status():
    return {
        "ts": "2026-09-14T05:00:00Z",
        "status_source": {"kind": "detail-cache"},
        "account": {"NetLiquidation": "10000", "TotalCashValue": "2500"},
        "positions": [{
            "symbol": "AAA", "position": 50, "marketPrice": 100, "marketValue": 5000,
            "avgCost": 95, "conId": 1, "secType": "STK", "currency": "USD", "exchange": "SMART",
        }],
    }


def test_ready_requires_one_du_paper_account_and_broker_reads():
    out = mod.build_receipt(
        run_id="123", job="consume", public_head="c" * 40, runtime=runtime(),
        health=(200, {"ok": True}), open_orders=(200, open_orders()), positions=(200, {"ok": True, "position_count": 1}),
    )
    assert out["ok"] is True
    assert out["side_effects"]["broker_order_placed"] is False
    assert out["detailed_account_plaintext_published"] is False
    assert out["secrets_published"] is False


def test_nonpaper_account_fails_closed():
    orders = open_orders()
    orders["account_identity"].update(du_account_count=0, selected_account_is_paper_du=False)
    out = mod.build_receipt(
        run_id="123", job="consume", public_head="c" * 40, runtime=runtime(),
        health=(200, {"ok": True}), open_orders=(200, orders), positions=(200, {"ok": True}),
    )
    assert out["ok"] is False
    assert out["status"] == "REMOTE_PAPER_SESSION_NOT_READY"


def test_account_snapshot_normalizes_canonical_truth_without_submit_authority():
    snap = mod.build_account_snapshot(run_id="123", runtime=runtime(), status=status(), open_orders_body=open_orders())
    assert snap["schema"] == mod.ACCOUNT_SNAPSHOT_SCHEMA
    assert snap["net_liquidation"] == 10000
    assert snap["cash"] == 2500
    assert snap["positions"][0]["quantity"] == 50
    assert snap["open_orders"][0]["order_id"] == 42
    assert snap["paper_session_ready"] is True
    assert snap["open_orders_complete"] is True
    assert snap["boundaries"]["broker_action"] is False
    assert snap["boundaries"]["paper_submit"] is False
    assert snap["boundaries"]["live_submit"] is False


def test_encrypted_account_return_round_trip(tmp_path):
    private = x25519.X25519PrivateKey.generate()
    private_raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    recipient = {
        "schema": mod.RETURN_RECIPIENT_SCHEMA,
        "recipient_b64": base64.b64encode(public_raw).decode("ascii"),
        "recipient_key_id": "sha256:" + hashlib.sha256(public_raw).hexdigest(),
    }
    snap = mod.build_account_snapshot(run_id="123", runtime=runtime(), status=status(), open_orders_body=open_orders())
    envelope = mod.encrypt_account_snapshot(run_id="123", snapshot=snap, recipient=recipient, output_dir=tmp_path)
    payload_b64 = "".join((tmp_path / node["local_name"]).read_text() for node in envelope["chunks"])
    ciphertext = base64.b64decode(payload_b64.encode("ascii"), validate=True)
    sender_public = base64.b64decode(envelope["sender_public_b64"])
    nonce = base64.b64decode(envelope["nonce_b64"])
    aad = mod._return_aad(run_id="123", recipient_key_id=recipient["recipient_key_id"])
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_public))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=hashlib.sha256(aad).digest(), info=mod.RETURN_INFO).derive(shared)
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
    assert hashlib.sha256(plaintext).hexdigest() == envelope["plaintext_sha256"]
    assert json.loads(plaintext) == snap
    assert "net_liquidation" not in json.dumps(mod.build_receipt(
        run_id="123", job="consume", public_head="c" * 40, runtime=runtime(),
        health=(200, {"ok": True}), open_orders=(200, open_orders()), positions=(200, {"ok": True, "position_count": 1}),
    ))
