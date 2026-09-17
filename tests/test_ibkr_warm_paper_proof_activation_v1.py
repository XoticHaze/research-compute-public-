from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ibkr_warm_paper_proof_activation_v1 as mod


class WarmPaperProofActivationTests(unittest.TestCase):
    def test_run_bound_recipient_matches_existing_transport_authority(self):
        with tempfile.TemporaryDirectory() as td:
            key_path = Path(td) / "recipient.key"
            node = mod.generate_command_recipient(run_id="123456", private_key_path=key_path)
            self.assertEqual(node["schema"], "ibkr-remote-paper-recipient-v1")
            self.assertEqual(node["run_id"], "123456")
            self.assertEqual(node["authority"], mod.command_capsule.AUTHORITY)
            self.assertEqual(node["harness"], mod.command_capsule.HARNESS)
            public_raw = base64.b64decode(node["recipient_b64"], validate=True)
            self.assertEqual(len(public_raw), 32)
            self.assertEqual(node["recipient_key_id"], "sha256:" + hashlib.sha256(public_raw).hexdigest())
            self.assertEqual(len(base64.b64decode(key_path.read_text().strip(), validate=True)), 32)

    def test_prepare_publishes_only_run_bound_public_recipient(self):
        published = []

        def fake_publish(token, repository, path, text, *, branch, message):
            published.append((repository, path, json.loads(text), branch, message))

        with tempfile.TemporaryDirectory() as td, patch.object(mod, "_publish_new_text", side_effect=fake_publish):
            out = mod.prepare_command_exchange(
                token="token",
                repository="XoticHaze/research-compute-public-",
                run_id="98765",
                runner_temp=Path(td),
            )
        self.assertFalse(out["broker_action"])
        self.assertEqual(out["gateway_auth_source"], "fleet_authority_warm_state")
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0][1], "rendezvous/recipients/98765-ibkr-remote-paper.json")
        self.assertNotIn("password", json.dumps(published[0][2]).lower())
        self.assertNotIn("username", json.dumps(published[0][2]).lower())

    def test_canonical_bot_environment_is_paper_only_and_uses_internal_gateway_port(self):
        env = mod.canonical_bot_environment()
        self.assertEqual(env["IB_HOST"], "127.0.0.1")
        self.assertEqual(env["IB_PORT"], "4004")
        self.assertEqual(env["ENABLE_LIVE_TRADING"], "0")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_ORDER_SUBMIT_ENABLED_13Z53"], "1")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_CANCEL_ENABLED_13Z37"], "1")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_FLATTEN_ENABLED_13Z39"], "1")
        self.assertEqual(env["STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D"], "0")
        # Operator approvals/acks are authority inputs and must not be synthesized by cloud runtime env.
        self.assertFalse(any("ACK" in key or "APPROVED" in key for key in env))

    def test_encrypted_return_publishes_only_manifested_ciphertext_and_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chunk = root / "ibkr-paper-proof-000.txt"
            chunk.write_text("YWJj", encoding="ascii")
            envelope = {
                "chunks": [
                    {
                        "path": "rendezvous/returns/42/ibkr-paper-proof-000.txt",
                        "local_name": chunk.name,
                        "sha256": hashlib.sha256(b"YWJj").hexdigest(),
                        "chars": 4,
                    }
                ]
            }
            published = []

            def fake_publish(token, repository, path, text, *, branch, message):
                published.append((path, text, message))

            with patch.object(mod, "_publish_new_text", side_effect=fake_publish):
                mod._publish_encrypted_return(
                    token="token",
                    repository="XoticHaze/research-compute-public-",
                    run_id="42",
                    envelope=envelope,
                    output_dir=root,
                    exchange_ref=mod.EXCHANGE_REF,
                )
            self.assertEqual([row[0] for row in published], [
                "rendezvous/returns/42/ibkr-paper-proof-000.txt",
                "rendezvous/returns/42/ibkr-paper-proof-envelope.json",
            ])
            self.assertNotIn("receipt", published[0][0])

    def test_encrypted_return_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "x.txt").write_text("YWJj", encoding="ascii")
            envelope = {
                "chunks": [{
                    "path": "rendezvous/returns/43/../leak.txt",
                    "local_name": "x.txt",
                    "sha256": hashlib.sha256(b"YWJj").hexdigest(),
                    "chars": 4,
                }]
            }
            with self.assertRaisesRegex(RuntimeError, "path rejected"):
                mod._publish_encrypted_return(
                    token="token",
                    repository="XoticHaze/research-compute-public-",
                    run_id="43",
                    envelope=envelope,
                    output_dir=root,
                    exchange_ref=mod.EXCHANGE_REF,
                )

    def test_orchestrator_has_no_direct_broker_order_client(self):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("ib_insync", source)
        self.assertNotIn("placeOrder(", source)
        self.assertNotIn("cancelOrder(", source)
        self.assertNotIn("reqGlobalCancel", source)
        self.assertIn("proof_v2.execute_paper_proof_v2", source)


if __name__ == "__main__":
    unittest.main()
