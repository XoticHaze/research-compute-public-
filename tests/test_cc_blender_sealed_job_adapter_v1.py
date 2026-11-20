"""Real sealed request -> fixed-worker mock -> encrypted result round trip.

No Blender binary, Cloudflare admin action or network needed. Mock replaces
only the scene render, not the EXISTING P-256 crypto.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import generate_keypair, seal
from scripts.creative.blender_fixed_worker_v1 import digest
from scripts.creative.blender_result_envelope_v1 import open_artifacts
from scripts.creative.blender_sealed_job_adapter_v1 import execute_sealed_job

JOB = {
    "schema": "commandcenter.blender_job.v1",
    "job_id": "blender-sealed-demo-r0",
    "recipe_id": "industrial_arm_v1",
    "source": {"repository": "XoticHaze/research-compute-public-", "commit": "a" * 40},
    "upstream_commit": "d5e8889eef0b33e0bbe62ddca6f713f94b154b68",
    "revision": 0, "parent_job_sha256": None,
    "parameters": {"camera_azimuth_deg": 30, "preview_frame": 45, "preview_samples": 12},
    "classification": "public_demo_no_private_inputs",
}


class SealedBlenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.sealed = self.root / "sealed"
        self.source = self.root / "pinned-source"
        self.source.mkdir()
        self.worker_private, self.worker_public, _ = generate_keypair()
        self.owner_private, self.owner_public, _ = generate_keypair()
        self.run_id = "sealed-blender-roundtrip-001"

    def request_envelope(self):
        node = {"schema": "commandcenter.blender_sealed_request.v1", "job": JOB,
                "result_recipient_public_b64": self.owner_public}
        return seal(json.dumps(node).encode(), recipient_public_b64=self.worker_public,
                    run_id=self.run_id, direction="request")

    def fake_blender(self, job, *, source_root, output_root, blender_binary):
        out = output_root / job["job_id"]
        out.mkdir()
        files = {
            "arm.blend": b"BLENDER" + b"scene" * 1000,
            "arm.glb": b"glTF" + b"animation" * 1000,
            "preview.png": b"\x89PNG\r\n\x1a\n" + b"preview" * 1000,
        }
        receipt = {"schema": "commandcenter.blender_probe_result.v1",
                   "status": "SUCCESS", "job_sha256": digest(job),
                   "blender_version": "5.2.4",
                   "files": {k: {"bytes": len(v), "sha256": sha256(v).hexdigest()}
                             for k,v in files.items()}}
        for key, data in files.items():
            (out / key).write_bytes(data)
        (out / "receipt.json").write_text(json.dumps(receipt))
        return receipt

    def test_original_crypto_sealed_roundtrip_and_cleanup(self):
        with patch("scripts.creative.blender_sealed_job_adapter_v1.run", side_effect=self.fake_blender):
            result = execute_sealed_job(
                self.request_envelope(), run_id=self.run_id,
                worker_private_b64=self.worker_private, source_root=self.source,
                work_root=self.work, ciphertext_root=self.sealed, blender_binary="trusted")
        self.assertEqual(result["status"], "CIPHERTEXT_READY")
        self.assertFalse(result["public_plaintext_artifacts"])
        self.assertFalse((self.work / JOB["job_id"]).exists())
        decrypted = open_artifacts(self.sealed / JOB["job_id"],
                                   recipient_private_b64=self.owner_private, run_id=self.run_id)
        self.assertEqual(set(decrypted), {"arm.blend", "arm.glb", "preview.png", "receipt.json"})
        self.assertEqual(json.loads(decrypted["receipt.json"])["job_sha256"], digest(JOB))

    def test_wrong_run_is_rejected_before_render(self):
        with patch("scripts.creative.blender_sealed_job_adapter_v1.run") as fake:
            with self.assertRaises(Exception):
                execute_sealed_job(
                    self.request_envelope(), run_id="another-run-id",
                    worker_private_b64=self.worker_private, source_root=self.source,
                    work_root=self.work, ciphertext_root=self.sealed, blender_binary="trusted")
            fake.assert_not_called()


if __name__ == "__main__":
    unittest.main()
