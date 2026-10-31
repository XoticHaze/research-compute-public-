"""Brokerless tests for exact original encrypted checkpoint read-only review."""
from __future__ import annotations
import importlib.util
import sys
import types
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/mmibkr_original_live_checkpoint_review_v1.py"


class OriginalReadonlyReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # No network or broker, and no key needed for structural denial cases.
        gateway = types.ModuleType("scripts.mmibkr_live_gateway_state_envelope_v1")
        gateway.read_master = lambda: b"x" * 32
        codec = types.ModuleType("scripts.mmibkr_live_runtime_checkpoint_v1")
        codec.unseal = lambda *args: (_ for _ in ()).throw(AssertionError("unseal_unexpected"))
        sys.modules[gateway.__name__] = gateway
        sys.modules[codec.__name__] = codec
        spec = importlib.util.spec_from_file_location("original_readonly_review", SCRIPT)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_exact_immutable_source_digest(self):
        m = self.mod
        self.assertEqual(m.EXPECTED_CONTEXT_SOURCE, "46fcdf26cf84603b305a3ea20bcd3cf28c67bc0b")
        self.assertEqual(m.EXPECTED_CIPHER_BYTES, 33560349)
        self.assertEqual(m.EXPECTED_CIPHER_SHA256, "7fa732e25dbb9044ba66c8fb9e3f7da4e269434ee7b2708d635f58c7d914bc66")
        self.assertEqual(m.EXPECTED_RAW_SHA256, "7e08dfbe6202968a6ff4ff5c83d1f634ba6ee2b83d06e0e3f1f9c143918b5238")

    def test_tampered_ciphertext_held_before_unseal(self):
        with self.assertRaisesRegex(ValueError, "historical_ciphertext_identity_invalid"):
            self.mod.inspect_exact(b"bad", b"{}", b"x" * 32, "41159917178")

    def test_manifest_producer_mismatch_held(self):
        with self.assertRaisesRegex(ValueError, "historical_producer_identity_mismatch"):
            self.mod._validate_exact_context({"context":{"run_id":"other"}})

    def test_manifest_never_confers_order_authority(self):
        c={"run_id":"39499524894","source_sha":self.mod.EXPECTED_CONTEXT_SOURCE,
           "scope":["AMAT","APH","MNQ"],"order_authority":"live"}
        node={"context":c,"archive_sha256":self.mod.EXPECTED_RAW_SHA256,
              "ciphertext_sha256":self.mod.EXPECTED_CIPHER_SHA256,
              "ciphertext_bytes":self.mod.EXPECTED_CIPHER_BYTES}
        with self.assertRaisesRegex(ValueError, "historical_order_authority_invalid"):
            self.mod._validate_exact_context(node)

    def test_workflow_has_no_owner_or_broker_start(self):
        workflow=(ROOT / ".github/workflows/mmibkr-original-live-checkpoint-review-r1.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("secrets.MMIBKR_LIVE_GATEWAY_WARM_KEY_B64",workflow)
        self.assertNotIn("placeOrder",workflow)
        self.assertNotIn("docker run",workflow)
        self.assertNotIn("pi.release",workflow)
        self.assertNotIn("mmibkr-selected-runtime-live-owner-r1.yml",workflow)
        self.assertNotIn("private-source-token",workflow)
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.confirm_readonly_checkpoint_review }}",workflow)

    def test_no_broker_or_secret_in_main(self):
        src=SCRIPT.read_text()
        self.assertIn("decrypted_plaintext_artifact_published",src)
        self.assertIn("live_order_submit_allowed",src)
        self.assertNotIn("placeOrder",src)
        self.assertNotIn("reqOpenOrders",src)
        self.assertNotIn("docker",src.lower().split('def main')[1])


if __name__ == "__main__":
    unittest.main()
