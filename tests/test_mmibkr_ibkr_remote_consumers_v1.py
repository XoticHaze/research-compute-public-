from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

import mmibkr_ephemeral_scoped_v1 as transport
import mmibkr_ibkr_history_ephemeral_consumer_v1 as history
import mmibkr_ibkr_paper_ephemeral_consumer_v1 as paper


class ScopedTransportTests(unittest.TestCase):
    def test_history_authority_round_trip(self) -> None:
        recipient_private = x25519.X25519PrivateKey.generate()
        recipient_public = recipient_private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        recipient_key_id = "sha256:" + hashlib.sha256(recipient_public).hexdigest()
        sender = x25519.X25519PrivateKey.generate()
        sender_public = sender.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        run_id = "12345"
        response_root = f"rendezvous/responses/{run_id}"
        plaintext = b'{"safe":"private"}'
        aad = transport.aad_bytes(
            schema=history.ENVELOPE_SCHEMA,
            run_id=run_id,
            authority=history.AUTHORITY,
            harness=history.HARNESS,
            recipient_key_id=recipient_key_id,
        )
        shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(recipient_public))
        key = transport.derive_key(shared, aad)
        nonce = os.urandom(12)
        ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)
        b64 = base64.b64encode(ciphertext).decode("ascii")
        chunk_path = f"{response_root}/history-000.txt"
        chunk_raw = b64.encode("ascii")
        envelope = {
            "schema": history.ENVELOPE_SCHEMA,
            "run_id": run_id,
            "authority": history.AUTHORITY,
            "harness": history.HARNESS,
            "recipient_key_id": recipient_key_id,
            "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
            "chunks": [{"path": chunk_path, "sha256": hashlib.sha256(chunk_raw).hexdigest(), "chars": len(chunk_raw)}],
        }
        with tempfile.TemporaryDirectory() as td:
            key_path = Path(td) / "private.b64"
            private_raw = recipient_private.private_bytes(
                serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
            )
            key_path.write_text(base64.b64encode(private_raw).decode("ascii"))
            got = transport.decrypt_assembled_ciphertext(
                envelope=envelope,
                ciphertext=ciphertext,
                private_key_path=key_path,
                expected_schema=history.ENVELOPE_SCHEMA,
                expected_run_id=run_id,
                expected_authority=history.AUTHORITY,
                expected_harness=history.HARNESS,
                response_root=response_root,
            )
        self.assertEqual(got, plaintext)

    def test_wrong_authority_fails_closed(self) -> None:
        env = {
            "schema": "x", "run_id": "1", "authority": "paper_execution_only", "harness": "h",
            "recipient_key_id": "sha256:" + "0" * 64, "sender_public_b64": "", "nonce_b64": "",
            "ciphertext_sha256": "0" * 64, "plaintext_sha256": "0" * 64,
            "chunks": [{"path": "r/1/a", "sha256": "0" * 64, "chars": 1}],
        }
        with self.assertRaisesRegex(RuntimeError, "authority/harness"):
            transport.validate_envelope(
                env,
                expected_schema="x",
                expected_run_id="1",
                expected_authority="history_acquisition_only",
                expected_harness="h",
                response_root="r/1",
            )


class HistoryContractTests(unittest.TestCase):
    def test_history_private_input_is_exact_and_has_no_order_authority(self) -> None:
        payload = {
            "schema": history.PRIVATE_SCHEMA,
            "source_read_token": "token",
            "tws_userid": "paper-user",
            "tws_password": "secret",
            "tws_userid_paper": "",
            "tws_password_paper": "",
        }
        got = history._load_private(json.dumps(payload).encode())
        self.assertEqual(got["source_read_token"], "token")
        bad = dict(payload, order_request={})
        with self.assertRaisesRegex(RuntimeError, "field set"):
            history._load_private(json.dumps(bad).encode())
        self.assertEqual(history.CLIENT_ID, 1971)
        self.assertEqual(history.AUTHORITY, "history_acquisition_only")


class PaperContractTests(unittest.TestCase):
    def _order(self) -> dict:
        return {
            "schema": paper.ORDER_SCHEMA,
            "idempotency_key": "proof-20260913-001",
            "symbol": "MNQ",
            "action": "BUY",
            "quantity": 1,
            "limit_price": 1.0,
            "tif": "DAY",
            "reason": "remote paper proof",
            "operator_approved": True,
            "ibkr_paper_order_submit_ack_13z53": "IBKR_PAPER_ORDER_SUBMIT_ACK_13Z53",
        }

    def test_first_proof_order_bounds(self) -> None:
        paper._validate_order(self._order())
        for field, value in (("quantity", 2), ("symbol", "SPY"), ("operator_approved", False)):
            node = self._order()
            node[field] = value
            with self.assertRaises(RuntimeError):
                paper._validate_order(node)

    def test_canonical_payload_forces_limit_session_and_no_short_override(self) -> None:
        payload = paper._canonical_payload(self._order())
        self.assertEqual(payload["order_type"], "LMT")
        self.assertFalse(payload["allow_market_order"])
        self.assertFalse(payload["allow_inactive_session"])
        self.assertFalse(payload["allow_short_sell_13z53"])
        self.assertTrue(payload["operator_approved"])
        self.assertTrue(payload["order_ref"].startswith("MMIBKR_GH_"))

    def test_remote_override_disables_autonomous_execution_and_live(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = paper._write_override(Path(td))
            text = path.read_text()
        self.assertIn("ENABLE_LIVE_TRADING: '0'", text)
        self.assertIn("STRATEGY_AUTO_START_LOOPS_ENABLED: 'false'", text)
        self.assertIn("BOT_SELECTED_RUNTIME_NATURAL_CANDIDATE_14TH31BV_ENABLED: '0'", text)
        self.assertIn("STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53: '1'", text)


if __name__ == "__main__":
    unittest.main()
