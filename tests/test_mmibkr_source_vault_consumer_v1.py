from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts import mmibkr_source_vault_consumer_v1 as mod


def _archive() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, raw in [
            ("github-root/Dockerfile.bot", b"FROM scratch\n"),
            ("github-root/main.py", b"print('ok')\n"),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(raw))
    return buf.getvalue()


def _snapshot(source_sha: str):
    archive = _archive()
    key = b"k" * 32
    nonce = b"n" * 12
    aad = b"mmibkr-source-vault-test"
    ciphertext = AESGCM(key).encrypt(nonce, archive, aad)
    encoded = base64.b64encode(ciphertext)
    chunk_path = f"source-vault/{source_sha}/chunk-0000.txt"
    manifest = {
        "schema": mod.MANIFEST_SCHEMA,
        "source_ref": source_sha,
        "source_sha": source_sha,
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "archive_bytes": len(archive),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "ciphertext_bytes": len(ciphertext),
        "cipher": "AES-256-GCM",
        "key_wrap": "RSA-OAEP-256",
        "encoding": "base64",
        "key_id": "sha256:" + "1" * 64,
        "sealed_key_b64": base64.b64encode(b"sealed").decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "aad_b64": base64.b64encode(aad).decode("ascii"),
        "public_plaintext_included": False,
        "private_repository_token_used": False,
        "live_execution_authority": False,
        "chunks": [{
            "index": 0,
            "path": chunk_path,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "chars": len(encoded),
        }],
    }
    manifest_raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return archive, key, manifest, manifest_raw, chunk_path, encoded


class ReusableSourceVaultConsumerTests(unittest.TestCase):
    def test_defaults_point_to_runtime_ciphertext_vault(self):
        self.assertEqual(mod.DEFAULT_PUBLIC_REPO, "XoticHaze/mm-ibkr-runtime")
        self.assertEqual(mod.DEFAULT_PUBLIC_BRANCH, "mmibkr-source-vault")

    def test_materializes_exact_snapshot_without_private_repo_token(self):
        source = "a" * 40
        archive, key, manifest, manifest_raw, chunk_path, encoded = _snapshot(source)
        stored = {
            f"source-vault/{source}/manifest.json": manifest_raw,
            chunk_path: encoded,
        }

        def fetch(url: str) -> bytes:
            for path, raw in stored.items():
                if url.endswith("/" + path):
                    return raw
            raise AssertionError(url)

        def unwrap(_base, _run_id, _token, payload):
            self.assertEqual(payload["source_sha"], source)
            self.assertEqual(payload["archive_sha256"], manifest["archive_sha256"])
            return {
                "ok": True,
                "approved": True,
                "source_sha": source,
                "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "archive_sha256": manifest["archive_sha256"],
                "archive_bytes": len(archive),
                "master_key_b64": base64.b64encode(key).decode("ascii"),
                "reusable_attestation_stored": True,
            }

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = mod.materialize(
                source_sha=source,
                destination=root / "out",
                archive_output=root / "source.tar.gz",
                output=root / "materialization.json",
                run_id="12345",
                fetch=fetch,
                token_factory=lambda: "oidc",
                unwrap_api=unwrap,
            )
            self.assertTrue((Path(result["source_root"]) / "Dockerfile.bot").is_file())
            self.assertEqual(
                result["source_transport"],
                "fleet_authority_exact_sha_encrypted_snapshot_vault",
            )
            self.assertEqual(result["source_archive_sha256"], manifest["archive_sha256"])
            self.assertTrue(result["vault_attestation_verified"])
            self.assertFalse(result["private_repository_token_used"])
            self.assertFalse(result["plaintext_emitted"])
            self.assertFalse(result["live_execution_allowed"])

    def test_tampered_ciphertext_chunk_fails_before_unwrap(self):
        source = "b" * 40
        _, _, _, manifest_raw, chunk_path, encoded = _snapshot(source)
        stored = {
            f"source-vault/{source}/manifest.json": manifest_raw,
            chunk_path: (b"A" if encoded[:1] != b"A" else b"B") + encoded[1:],
        }

        def fetch(url: str) -> bytes:
            for path, raw in stored.items():
                if url.endswith("/" + path):
                    return raw
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "chunk_integrity"):
                mod.materialize(
                    source_sha=source,
                    destination=Path(td) / "out",
                    archive_output=Path(td) / "source.tar.gz",
                    output=Path(td) / "materialization.json",
                    run_id="12345",
                    fetch=fetch,
                    token_factory=lambda: "oidc",
                    unwrap_api=lambda *a, **k: self.fail("unwrap must not be called"),
                )


if __name__ == "__main__":
    unittest.main()
