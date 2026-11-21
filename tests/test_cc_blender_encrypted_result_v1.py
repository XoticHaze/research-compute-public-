"""Real crypto round-trip tests for existing public P-256/AES-GCM module, no Blender binary."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import generate_keypair
from scripts.creative.blender_result_envelope_v1 import encrypt_artifacts, open_artifacts


class BlenderEncryptedResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "render"
        self.work.mkdir()
        self.out = self.root / "sealed"
        self.private, self.public, self.key_id = generate_keypair()
        self.run_id = "blender-job-test-001"
        self.files = {
            "arm.blend": b"BLENDER" + b"demo" * 50000,
            "arm.glb": b"glTF" + b"demo" * 55000,
            "preview.png": b"\x89PNG\r\n\x1a\n" + b"pixels" * 50000,
        }
        receipt = {"schema": "commandcenter.blender_probe_result.v1",
                   "status": "SUCCESS", "job_sha256": "a" * 64, "blender_version": "5.2.4",
                   "files": {n: {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}
                             for n, raw in self.files.items()}}
        self.files["receipt.json"] = json.dumps(receipt).encode()
        for name, raw in self.files.items():
            (self.work / name).write_bytes(raw)

    def test_round_trip_with_real_existing_crypto(self):
        report = encrypt_artifacts(self.work, self.out, run_id=self.run_id, recipient_public_b64=self.public)
        self.assertEqual(report["status"], "SEALED")
        self.assertFalse(report["public_plaintext_artifacts"])
        self.assertGreater(report["part_count"], 0)
        self.assertFalse((self.out / "arm.blend").exists())
        self.assertFalse((self.out / "preview.png").exists())
        result = open_artifacts(self.out, recipient_private_b64=self.private, run_id=self.run_id)
        self.assertEqual(result, self.files)
        manifest = (self.out / "manifest.json").read_text()
        self.assertNotIn("arm.blend", manifest)
        self.assertNotIn("preview.png", manifest)

    def test_run_binding_and_ciphertext_tampering_fail(self):
        encrypt_artifacts(self.work, self.out, run_id=self.run_id, recipient_public_b64=self.public)
        with self.assertRaises(Exception):
            open_artifacts(self.out, recipient_private_b64=self.private, run_id="blender-job-test-002")
        part = self.out / "part-0000.json"
        item = json.loads(part.read_text())
        item["ciphertext_sha256"] = "0" * 64
        part.write_text(json.dumps(item))
        with self.assertRaises(Exception):
            open_artifacts(self.out, recipient_private_b64=self.private, run_id=self.run_id)

    def test_no_extra_private_artifact_egress(self):
        (self.work / "secret.env").write_text("DO_NOT_RETURN", encoding="utf-8")
        encrypt_artifacts(self.work, self.out, run_id=self.run_id, recipient_public_b64=self.public)
        result = open_artifacts(self.out, recipient_private_b64=self.private, run_id=self.run_id)
        self.assertEqual(set(result), set(self.files))
        self.assertNotIn(b"DO_NOT_RETURN", b"".join(result.values()))


if __name__ == "__main__":
    unittest.main()
