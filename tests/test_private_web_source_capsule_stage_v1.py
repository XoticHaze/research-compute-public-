import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.private_web_source_capsule_stage_v1 import fetch_capsule, stage, ENDPOINT


def b64(x):
    return base64.b64encode(x).decode("ascii")


def mock_capsule():
    opaque = b"only synthetic ciphertext data and AES-GCM tag bytes!"
    return {
        "schema": "commandcenter.private_web_ciphertext_capsule.v1",
        "capsule_id": "private-web-synthetic-stage-abcdef",
        "cipher": "AES-256-GCM+RSA-OAEP-256",
        "key_id": "sha256:" + "a" * 64,
        "nonce_b64": b64(b"0123456789ab"),
        "aad_b64": b64(b"commandcenter.private_web_ciphertext_capsule.v1|"
                       b"private-web-synthetic-stage-abcdef"),
        "sealed_key_b64": b64(b"z" * 256),
        "ciphertext_b64": b64(opaque),
        "ciphertext_sha256": hashlib.sha256(opaque).hexdigest(),
    }


class FakeResponse:
    def __init__(self, node, status=200):
        self.data = json.dumps(node).encode()
        self.status = status
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, n=None):
        return self.data[:n] if n is not None else self.data


class CapsuleStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = []
    def opener(self, req, timeout):
        self.calls.append(req)
        return FakeResponse(mock_capsule())

    def test_exact_authenticated_ciphertext_stage_and_receipt(self):
        row = stage(run_id="123456", capsule_root=self.root / "capsules",
                    receipt_file=self.root / "receipts" / "123456.json",
                    token_factory=lambda: "synthetic-oidc-not-logged",
                    open_url=self.opener)
        self.assertEqual(row["state"], "CIPHERTEXT_STAGED_NOT_DEPLOYED")
        self.assertFalse(row["hosted_deployed"])
        self.assertEqual(self.calls[0].full_url, ENDPOINT)
        self.assertEqual(self.calls[0].get_method(), "POST")
        self.assertIn("synthetic-oidc", self.calls[0].headers["Authorization"])
        saved = json.loads((self.root / "capsules" / (row["capsule_id"] + ".json")).read_text())
        self.assertEqual(saved["ciphertext_sha256"], row["ciphertext_sha256"])
        self.assertNotIn("synthetic-oidc", json.dumps(row))

    def test_refuse_invalid_run_identity(self):
        with self.assertRaisesRegex(ValueError, "run_id_invalid"):
            fetch_capsule("not-a-run", token_factory=lambda: "jwt", open_url=self.opener)
        self.assertEqual(self.calls, [])

    def test_refuse_wrong_server_payload_before_file_write(self):
        def open_tamper(req, timeout):
            c = mock_capsule()
            c["ciphertext_sha256"] = "0" * 64
            return FakeResponse(c)
        with self.assertRaisesRegex(ValueError, "ciphertext_capsule_tampered"):
            stage(run_id="123456", capsule_root=self.root / "capsules",
                  receipt_file=self.root / "receipts" / "123456.json",
                  token_factory=lambda: "fake", open_url=open_tamper)
        self.assertFalse((self.root / "capsules").exists())

    def test_denied_worker_rejected_without_echoing_provider(self):
        def denied(req, timeout):
            raise RuntimeError("private token must never leak")
        with self.assertRaisesRegex(RuntimeError, "^private_web_stage_not_admitted$"):
            fetch_capsule("123456", token_factory=lambda: "fake", open_url=denied)


if __name__ == "__main__":
    unittest.main()
