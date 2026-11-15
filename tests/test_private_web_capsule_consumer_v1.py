"""Synthetic, bounded proof for the encrypted private-web overlay consumer.

No real applicant data, private source or Cloudflare credentials are used.
"""
import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from scripts.private_web_capsule_consumer_v1 import (
    CAPSULE_SCHEMA, PLAIN_SCHEMA, capsule_input, materialize, cloudflare_key_release,
)


def enc(raw):
    return base64.b64encode(raw).decode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class PrivateWebCapsuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "overlay"
        self.receipt = self.root / "receipt.json"
        self.key = AESGCM.generate_key(bit_length=256)
        self.files = {
            "assets/demo/index.html": b"<!doctype html><title>demo</title>",
            "assets/demo/app.js": b"console.log('synthetic only')",
        }
        self.plain = {
            "schema": PLAIN_SCHEMA, "app_slug": "demo", "source_sha": "a" * 40,
            "source_pin_verified": True,
            "files": {k: {"sha256": digest(v), "data_b64": enc(v)} for k, v in self.files.items()},
        }
        self.capsule_id = "synthetic-only-capsule-20261115"
        self.nonce = b"0123456789ab"
        self.aad = (CAPSULE_SCHEMA + "|" + self.capsule_id).encode()

    def make_capsule(self):
        body = json.dumps(self.plain, sort_keys=True, separators=(",", ":")).encode()
        ct = AESGCM(self.key).encrypt(self.nonce, body, self.aad)
        c = {
            "schema": CAPSULE_SCHEMA, "capsule_id": self.capsule_id,
            "cipher": "AES-256-GCM+RSA-OAEP-256", "key_id": "sha256:" + "a" * 64,
            "nonce_b64": enc(self.nonce), "aad_b64": enc(self.aad),
            "sealed_key_b64": enc(b"z" * 256),
            "ciphertext_b64": enc(ct), "ciphertext_sha256": digest(ct),
        }
        return c, ct

    def parse(self, c):
        return capsule_input(json.dumps(c, sort_keys=True).encode())

    def grant(self):
        return {"master_key_b64": enc(self.key)}

    def test_decrypted_overlay_preserves_exact_assets_and_private_source_ref(self):
        c, ct = self.make_capsule()
        parsed, cipher = self.parse(c)
        self.assertEqual(cipher, ct)
        result = materialize(parsed, cipher, self.grant(), destination=self.output,
                             receipt=self.receipt)
        self.assertEqual(result["state"], "MATERIALIZED_NOT_DEPLOYED")
        self.assertEqual(result["asset_count"], 2)
        self.assertFalse(result["access_served_verified"])
        for rel, raw in self.files.items():
            self.assertEqual((self.output / rel).read_bytes(), raw)
        manifest = json.loads((self.root / "overlay.manifest.json").read_text())
        self.assertEqual(manifest["schema"], "commandcenter.private_web_static_overlay.v1")
        self.assertEqual(manifest["source_sha_claim"], "a" * 40)
        self.assertIs(manifest["oidc_release_grant_verified"], True)
        self.assertIs(manifest["access_served_verified"], False)

    def test_modified_ciphertext_is_rejected_before_key_release(self):
        c, _ = self.make_capsule()
        c["ciphertext_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "ciphertext_capsule_tampered"):
            self.parse(c)

    def test_malformed_envelope_refused(self):
        c, _ = self.make_capsule()
        c["source_sha"] = "a" * 40
        with self.assertRaisesRegex(ValueError, "ciphertext_capsule_contract_rejected"):
            self.parse(c)

    def test_bad_nonce_refused(self):
        c, _ = self.make_capsule()
        c["nonce_b64"] = enc(b"short")
        with self.assertRaisesRegex(ValueError, "ciphertext_capsule_crypto_fields_rejected"):
            self.parse(c)

    def test_not_git_pinned_source_refused(self):
        self.plain["source_pin_verified"] = False
        c, _ = self.make_capsule()
        c, cipher = self.parse(c)
        with self.assertRaisesRegex(RuntimeError, "private_web_plain_contract_rejected"):
            materialize(c, cipher, self.grant(), destination=self.output, receipt=self.receipt)
        self.assertFalse(self.output.exists())

    def test_out_of_scope_path_refused_before_writes(self):
        self.plain["files"] = {
            "assets/other/index.html": {
                "sha256": digest(b"bad"), "data_b64": enc(b"bad"),
            },
        }
        c, _ = self.make_capsule()
        c, cipher = self.parse(c)
        with self.assertRaisesRegex(RuntimeError, "private_web_asset_path_rejected"):
            materialize(c, cipher, self.grant(), destination=self.output, receipt=self.receipt)
        self.assertFalse(self.output.exists())

    def test_file_hash_mismatch_refused(self):
        self.plain["files"]["assets/demo/index.html"]["sha256"] = "0" * 64
        c, _ = self.make_capsule()
        c, cipher = self.parse(c)
        with self.assertRaisesRegex(RuntimeError, "private_web_asset_digest_rejected"):
            materialize(c, cipher, self.grant(), destination=self.output, receipt=self.receipt)

    def test_wrong_aes_key_fails_closed(self):
        c, _ = self.make_capsule()
        c, cipher = self.parse(c)
        with self.assertRaisesRegex(RuntimeError, "private_web_capsule_decrypt_rejected"):
            materialize(c, cipher, {"master_key_b64": enc(b"x" * 32)},
                        destination=self.output, receipt=self.receipt)

    def test_cannot_overwrite_existing_destination(self):
        c, _ = self.make_capsule()
        c, cipher = self.parse(c)
        self.output.mkdir()
        with self.assertRaisesRegex(RuntimeError, "private_web_output_must_be_new"):
            materialize(c, cipher, self.grant(), destination=self.output, receipt=self.receipt)

    def test_reject_non_https_authority_before_network(self):
        c, _ = self.make_capsule()
        with self.assertRaisesRegex(ValueError, "authority_origin_invalid"):
            cloudflare_key_release(c, base="http://not-secure.local", run_id="123456", token="fake")


if __name__ == "__main__":
    unittest.main()
