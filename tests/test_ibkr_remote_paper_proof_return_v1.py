import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from scripts import ibkr_remote_paper_proof_return_v1 as mod


class RemotePaperProofReturnTests(unittest.TestCase):
    def recipient(self):
        private = x25519.X25519PrivateKey.generate()
        raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return private, {
            "schema": mod.RETURN_RECIPIENT_SCHEMA,
            "recipient_b64": base64.b64encode(raw).decode("ascii"),
            "recipient_key_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
        }

    def runtime(self):
        return {"mode": "paper_submit_proof", "command_id": "sha256:" + "c" * 64}

    def receipt(self):
        return {
            "schema": mod.RECEIPT_SCHEMA,
            "ok": True,
            "status": "PAPER_PROOF_RECONCILED",
            "github": {"run_id": "12345", "public_head": "abc"},
            "command": {"command_id": "sha256:" + "c" * 64, "runtime_id": "mnq-runtime", "symbol": "MNQ"},
            "cleanup": {"global_cancel_called": False},
            "authority": {
                "cloud_strategy_authority": False,
                "cloud_execution_policy_authority": False,
                "direct_broker_client_used": False,
                "global_cancel_allowed": False,
                "live_execution_allowed": False,
            },
        }

    def test_encrypts_only_identity_bound_proof_receipt(self):
        _, recipient = self.recipient()
        with tempfile.TemporaryDirectory() as td:
            envelope = mod.encrypt_receipt(
                receipt=self.receipt(),
                runtime=self.runtime(),
                recipient=recipient,
                run_id="12345",
                output_dir=Path(td),
            )
            self.assertEqual(envelope["schema"], mod.RETURN_ENVELOPE_SCHEMA)
            self.assertEqual(envelope["run_id"], "12345")
            self.assertGreaterEqual(len(envelope["chunks"]), 1)
            self.assertTrue((Path(td) / "ibkr-paper-proof-envelope.json").is_file())
            self.assertFalse(any("receipt" in p.name for p in Path(td).iterdir()))

    def test_command_or_run_mismatch_fails_closed(self):
        _, recipient = self.recipient()
        with tempfile.TemporaryDirectory() as td:
            runtime = self.runtime()
            runtime["command_id"] = "sha256:" + "d" * 64
            with self.assertRaisesRegex(RuntimeError, "command id mismatch"):
                mod.encrypt_receipt(receipt=self.receipt(), runtime=runtime, recipient=recipient, run_id="12345", output_dir=Path(td))
            receipt = self.receipt()
            receipt["github"]["run_id"] = "other"
            with self.assertRaisesRegex(RuntimeError, "run id mismatch"):
                mod.encrypt_receipt(receipt=receipt, runtime=self.runtime(), recipient=recipient, run_id="12345", output_dir=Path(td))

    def test_authority_or_global_cancel_violation_fails_closed(self):
        _, recipient = self.recipient()
        with tempfile.TemporaryDirectory() as td:
            receipt = self.receipt()
            receipt["authority"]["live_execution_allowed"] = True
            with self.assertRaisesRegex(RuntimeError, "live execution boundary"):
                mod.encrypt_receipt(receipt=receipt, runtime=self.runtime(), recipient=recipient, run_id="12345", output_dir=Path(td))
            receipt = self.receipt()
            receipt["cleanup"]["global_cancel_called"] = True
            with self.assertRaisesRegex(RuntimeError, "global cancel was called"):
                mod.encrypt_receipt(receipt=receipt, runtime=self.runtime(), recipient=recipient, run_id="12345", output_dir=Path(td))

    def test_persistent_execute_receipt_uses_same_encrypted_return_transport(self):
        runtime = self.runtime()
        runtime["mode"] = "paper_execute"
        receipt = self.receipt()
        receipt["schema"] = mod.EXECUTE_RECEIPT_SCHEMA
        receipt["status"] = "PAPER_EXECUTE_RECONCILED"
        receipt["cleanup"] = {
            "automatic_cleanup": False,
            "exact_cancel_called": False,
            "flatten_called": False,
            "global_cancel_called": False,
        }
        out = mod.validate_receipt(receipt, runtime, run_id="12345")
        self.assertEqual(out["schema"], mod.EXECUTE_RECEIPT_SCHEMA)

        with self.assertRaisesRegex(RuntimeError, "mode/receipt schema mismatch"):
            mod.validate_receipt(self.receipt(), runtime, run_id="12345")

    def test_recipient_fingerprint_is_verified(self):
        _, recipient = self.recipient()
        recipient["recipient_key_id"] = "sha256:" + "0" * 64
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "fingerprint mismatch"):
                mod.encrypt_receipt(receipt=self.receipt(), runtime=self.runtime(), recipient=recipient, run_id="12345", output_dir=Path(td))


if __name__ == "__main__":
    unittest.main()
