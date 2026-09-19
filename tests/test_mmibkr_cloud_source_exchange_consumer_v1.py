from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts import mmibkr_cloud_source_exchange_consumer_v1 as mod


class MmibkrCloudSourceExchangeConsumerTests(unittest.TestCase):
    def archive(self) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            payloads = {
                "mm-ibkr/Dockerfile.bot": b"FROM python:3.11\n",
                "mm-ibkr/main.py": b"print('ok')\n",
                "mm-ibkr/scripts/operator/example.py": b"x=1\n",
            }
            for name, raw in payloads.items():
                info = tarfile.TarInfo(name)
                info.mode = 0o644
                info.size = len(raw)
                tf.addfile(info, io.BytesIO(raw))
        return buf.getvalue()

    def envelope(self, archive: bytes):
        private = x25519.X25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        key_id = "sha256:" + hashlib.sha256(public).hexdigest()

        sender = x25519.X25519PrivateKey.generate()
        sender_public = sender.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        salt = b"s" * 32
        nonce = b"n" * 12
        source_sha = "a" * 40
        aad = mod._aad(
            run_id="12345",
            source_ref="assistant/cloud-signal-history-split-20260918",
            source_sha=source_sha,
            recipient_key_id=key_id,
        )
        shared = sender.exchange(x25519.X25519PublicKey.from_public_bytes(public))
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=mod.INFO,
        ).derive(shared)
        ciphertext = ChaCha20Poly1305(key).encrypt(nonce, archive, aad)
        encoded = base64.b64encode(ciphertext).decode("ascii")
        chunks = [encoded[i:i + 80] for i in range(0, len(encoded), 80)]
        desc = [
            {
                "index": i,
                "chars": len(text),
                "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
            }
            for i, text in enumerate(chunks)
        ]
        manifest = {
            "schema": mod.RESPONSE_SCHEMA,
            "run_id": "12345",
            "harness": mod.HARNESS,
            "source_ref": "assistant/cloud-signal-history-split-20260918",
            "source_sha": source_sha,
            "recipient_key_id": key_id,
            "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
            "salt_b64": base64.b64encode(salt).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "plaintext_sha256": hashlib.sha256(archive).hexdigest(),
            "archive_bytes": len(archive),
            "ciphertext_bytes": len(ciphertext),
            "chunk_count": len(chunks),
            "chunks": desc,
            "producer_identity": {
                "repository": "XoticHaze/mm-IBKR",
                "repository_visibility": "private",
                "ref": "refs/heads/assistant/cloud-signal-history-split-20260918",
                "workflow_ref": (
                    "XoticHaze/mm-IBKR/.github/workflows/"
                    "mmibkr-cloud-source-producer-r1.yml@"
                    "refs/heads/assistant/cloud-signal-history-split-20260918"
                ),
                "event_name": "push",
                "run_id": "88888",
                "run_attempt": "1",
            },
            "finalized_at": "2026-09-19T09:00:00Z",
        }
        return private, key_id, manifest, chunks

    def test_decrypt_and_extract_exact_private_archive(self):
        archive = self.archive()
        private, key_id, manifest, chunks = self.envelope(archive)
        plain = mod.decrypt_archive(
            manifest,
            chunks,
            private_key=private,
            run_id="12345",
            source_ref="assistant/cloud-signal-history-split-20260918",
            recipient_key_id=key_id,
        )
        self.assertEqual(plain, archive)

        with tempfile.TemporaryDirectory() as td:
            root = mod.extract_archive(plain, Path(td))
            self.assertEqual(root.name, "mm-ibkr")
            self.assertTrue((root / "Dockerfile.bot").is_file())
            self.assertEqual((root / "main.py").read_text(), "print('ok')\n")

    def test_producer_identity_is_pinned(self):
        archive = self.archive()
        private, key_id, manifest, chunks = self.envelope(archive)
        manifest["producer_identity"]["repository"] = "attacker/repo"
        with self.assertRaisesRegex(RuntimeError, "producer_repository_rejected"):
            mod.decrypt_archive(
                manifest,
                chunks,
                private_key=private,
                run_id="12345",
                source_ref="assistant/cloud-signal-history-split-20260918",
                recipient_key_id=key_id,
            )

    def test_chunk_tamper_is_rejected_before_decrypt(self):
        archive = self.archive()
        private, key_id, manifest, chunks = self.envelope(archive)
        chunks[0] = "A" + chunks[0][1:]
        with self.assertRaisesRegex(RuntimeError, "chunk_integrity_rejected"):
            mod.decrypt_archive(
                manifest,
                chunks,
                private_key=private,
                run_id="12345",
                source_ref="assistant/cloud-signal-history-split-20260918",
                recipient_key_id=key_id,
            )

    def test_archive_path_escape_is_rejected(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            raw = b"bad"
            info = tarfile.TarInfo("../escape")
            info.size = len(raw)
            tf.addfile(info, io.BytesIO(raw))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "archive_path_rejected"):
                mod.extract_archive(buf.getvalue(), Path(td))


if __name__ == "__main__":
    unittest.main()
