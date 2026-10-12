"""Canonical P-256 encrypted neutral gate regression using synthetic source only.

Exercises the current consumer's real bounded archive/test path with no Cloudflare
credentials, private project source, job metadata or plaintext digests in public.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

# The production consumer is a fixed scripts/ entrypoint and uses sibling imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import commandcenter_neutral_gate_ephemeral_consumer_v1 as consumer
from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import (
    generate_keypair, seal,
)

SOURCE = "scripts/security/validate_neutral_broker_editor_token_policy.py"
TEST = "tests/test_neutral_broker_editor_token_policy.py"
PRIVATE_SYNTHETIC = b"def synthetic_policy_ok():\n    return True\n"
SYNTHETIC_TEST = (
    b"import unittest\n"
    b"from scripts.security.validate_neutral_broker_editor_token_policy import synthetic_policy_ok\n"
    b"class SyntheticGate(unittest.TestCase):\n"
    b"    def test_policy(self):\n"
    b"        self.assertTrue(synthetic_policy_ok())\n"
)


def _bundle() -> tuple[bytes, dict[str, str]]:
    members = {SOURCE: PRIVATE_SYNTHETIC, TEST: SYNTHETIC_TEST}
    inner = {
        "schema": consumer.MANIFEST_SCHEMA,
        "harness": consumer.HARNESS,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in members.items()},
    }
    members["payload-manifest.json"] = json.dumps(inner, sort_keys=True).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            info.mode = 0o600
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue(), {
        SOURCE: consumer._git_blob(PRIVATE_SYNTHETIC),
        TEST: consumer._git_blob(SYNTHETIC_TEST),
    }


class NeutralCanonicalCapsuleTests(unittest.TestCase):
    RUN_ID = "38242000001"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        private, public, _ = generate_keypair()
        self.root.joinpath("canonical-private.b64").write_text(private)
        self.root.joinpath("legacy-unused.b64").write_text("not a legacy private key")
        self.private_path = self.root / "canonical-private.b64"
        self.legacy_path = self.root / "legacy-unused.b64"
        bundle, self.git_blobs = _bundle()
        self.envelope = seal(bundle, recipient_public_b64=public, run_id=self.RUN_ID, direction="request")
        self.envelope_path = self.root / "envelope.json"
        self._write_envelope()

    def _write_envelope(self):
        self.envelope_path.write_text(json.dumps(self.envelope, sort_keys=True))

    def _consume(self, *, run_id=None, key=None):
        with patch.dict(consumer.EXPECTED_GIT_BLOBS, self.git_blobs):
            return consumer.consume(
                self.envelope_path, self.legacy_path, run_id or self.RUN_ID,
                self.private_path if key is None else key,
            )

    def test_real_canonical_decrypt_extract_execute_passes(self):
        result = self._consume()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["capsule_profile"], "canonical_p256_aesgcm_v1")
        self.assertEqual(result["checks"], {"single_worker_editor_policy": True})
        self.assertEqual(result["pinned_source_member_count"], 2)
        self.assertTrue(result["encrypted_input"])
        self.assertFalse(result["private_plaintext_emitted"])
        self.assertFalse(result["cloudflare_mutations"])

    def test_public_envelope_excludes_sensitive_metadata(self):
        encoded = json.dumps(self.envelope, sort_keys=True).encode()
        for forbidden in (b"plaintext_sha256", b"authority", b"harness", b"source_git_blob", PRIVATE_SYNTHETIC, SYNTHETIC_TEST):
            with self.subTest(forbidden=forbidden[:30]):
                self.assertNotIn(forbidden, encoded)
        self.assertEqual(
            set(self.envelope),
            {"schema", "run_id", "direction", "recipient_key_id",
             "sender_public_b64", "nonce_b64", "ciphertext_b64", "ciphertext_sha256"},
        )

    def test_wrong_run_rejected(self):
        with self.assertRaises(Exception):
            self._consume(run_id="9999")

    def test_wrong_recipient_rejected(self):
        wrong, _, _ = generate_keypair()
        bad_key = self.root / "wrong-key.b64"
        bad_key.write_text(wrong)
        with self.assertRaises(Exception):
            self._consume(key=bad_key)

    def test_ciphertext_tamper_rejected(self):
        self.envelope["ciphertext_b64"] = base64.b64encode(b"bad" * 100).decode()
        self._write_envelope()
        with self.assertRaises(Exception):
            self._consume()

    def test_extra_plaintext_digest_rejected(self):
        self.envelope["plaintext_sha256"] = hashlib.sha256(PRIVATE_SYNTHETIC).hexdigest()
        self._write_envelope()
        with self.assertRaises(Exception):
            self._consume()

    def test_wrong_direction_rejected(self):
        self.envelope["direction"] = "result"
        self._write_envelope()
        with self.assertRaises(Exception):
            self._consume()

    def test_canonical_private_key_is_required(self):
        with self.assertRaises(Exception):
            self._consume(key=self.root / "not-present-key")


if __name__ == "__main__":
    unittest.main()
