"""Synthetic private-producer -> canonical capsule -> consumer roundtrip.

No private CommandCenter bytes or Cloudflare credentials used. Public output
is ciphertext-only and independent of the project input content.
"""
import base64
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import commandcenter_neutral_gate_canonical_sender_v1 as sender
from scripts import commandcenter_neutral_gate_ephemeral_consumer_v1 as consumer
from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import generate_keypair

SOURCE = "scripts/security/validate_neutral_broker_editor_token_policy.py"
TEST = "tests/test_neutral_broker_editor_token_policy.py"
SRC_BYTES = b"def synthetic_policy_ok():\n    return True\n"
TEST_BYTES = (
    b"import unittest\n"
    b"from scripts.security.validate_neutral_broker_editor_token_policy import synthetic_policy_ok\n"
    b"class SyntheticPolicy(unittest.TestCase):\n"
    b"    def test_fixed(self): self.assertTrue(synthetic_policy_ok())\n"
)


class NeutralCanonicalSenderTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.private_root = self.root / "private"
        self.private_root.mkdir()
        self.fixture = {SOURCE: SRC_BYTES, TEST: TEST_BYTES}
        for name, content in self.fixture.items():
            target = self.private_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.blobs = {name: consumer._git_blob(content) for name, content in self.fixture.items()}
        self.private_key, self.public_key, self.key_id = generate_keypair()
        self.offer = {
            "schema": "commandcenter-ledger-ephemeral-recipient-v1",
            "run_id": "38250000001",
            "recipient_b64": base64.b64encode(b"legacy-public-key").decode(),
            "recipient_key_id": "legacy-sha",
            "canonical_recipient_b64": self.public_key,
            "canonical_recipient_key_id": self.key_id,
        }

    def _produce(self, offer=None):
        with patch.dict(sender.EXPECTED_GIT_BLOBS, self.blobs):
            return sender.produce(self.private_root, offer or self.offer,
                                  run_id="38250000001", suite="policy")

    def test_in_memory_sender_and_original_consumer_execute(self):
        envelope = self._produce()
        self.assertEqual(set(envelope), set(sender.CANONICAL_FIELDS))
        serialized = json.dumps(envelope, sort_keys=True).encode()
        for forbidden in (SRC_BYTES, TEST_BYTES, b"plaintext_sha256", b"authority", b"harness", b"policy_only"):
            self.assertNotIn(forbidden, serialized)
        envelope_file = self.root / "encrypted.json"
        envelope_file.write_text(json.dumps(envelope))
        canonical_key = self.root / "canonical-key"
        canonical_key.write_text(self.private_key)
        with patch.dict(consumer.EXPECTED_GIT_BLOBS, self.blobs):
            result = consumer.consume(envelope_file, self.root / "legacy-unused", "38250000001", canonical_key)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["capsule_profile"], "canonical_p256_aesgcm_v1")
        self.assertEqual(result["checks"], {"single_worker_editor_policy": True})
        self.assertFalse(result["private_plaintext_emitted"])

    def test_wrong_git_blob_is_rejected_before_encryption(self):
        source_path = self.private_root / SOURCE
        source_path.write_bytes(SRC_BYTES + b"# tamper\n")
        with self.assertRaises(sender.ProducerRejected):
            self._produce()

    def test_offer_run_key_identity_validation(self):
        for key, value in (
            ("run_id", "another-run"),
            ("canonical_recipient_key_id", "sha256:" + "0" * 64),
            ("canonical_recipient_b64", "invalid_base64"),
            ("schema", "different"),
        ):
            with self.subTest(field=key), self.assertRaises(Exception):
                self._produce(dict(self.offer, **{key: value}))

    def test_private_source_symlink_rejected(self):
        target = self.private_root / SOURCE
        replacement = self.root / "outside"
        replacement.write_bytes(SRC_BYTES)
        target.unlink()
        target.symlink_to(replacement)
        with self.assertRaises(sender.ProducerRejected):
            self._produce()

    def test_cli_writes_only_exclusive_mode_0600_envelope(self):
        offer_file = self.root / "offer.json"
        offer_file.write_text(json.dumps(self.offer))
        out = self.root / "ciphertext.json"
        argv = ["sender", "--private-root", str(self.private_root),
                "--public-offer", str(offer_file), "--run-id", "38250000001",
                "--encrypted-output", str(out)]
        with patch.dict(sender.EXPECTED_GIT_BLOBS, self.blobs):
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()) as msg:
                self.assertEqual(sender.main(), 0)
            self.assertEqual(msg.getvalue().strip(), "NEUTRAL_CANONICAL_CAPSULE=ENCRYPTED_ONLY")
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
            output = out.read_bytes()
            self.assertNotIn(SRC_BYTES, output)
            self.assertNotIn(b"plaintext_sha256", output)
            with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()) as msg:
                self.assertEqual(sender.main(), 1)
            self.assertEqual(msg.getvalue().strip(), "NEUTRAL_CANONICAL_CAPSULE=FAIL_CLOSED")


if __name__ == "__main__":
    unittest.main()
