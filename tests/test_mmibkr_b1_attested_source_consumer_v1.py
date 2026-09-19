from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts import mmibkr_b1_attested_source_consumer_v1 as mod


class B1AttestedSourceConsumerTests(unittest.TestCase):
    def build_exchange(self):
        recipient = x25519.X25519PrivateKey.generate()
        recipient_private = recipient.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        recipient_public = recipient.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        key_id = "sha256:" + hashlib.sha256(recipient_public).hexdigest()

        archive = b"exact-private-mm-archive"
        source_sha = "a" * 40
        archive_sha = hashlib.sha256(archive).hexdigest()
        source_ref = "assistant/cloud-signal-history-split-20260918"

        sender = x25519.X25519PrivateKey.generate()
        sender_public = sender.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        salt = b"s" * 32
        nonce = b"n" * 12
        aad = mod._aad(
            run_id="12345",
            source_ref=source_ref,
            source_sha=source_sha,
            recipient_key_id=key_id,
        )
        shared = sender.exchange(
            x25519.X25519PublicKey.from_public_bytes(recipient_public)
        )
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=mod.INFO,
        ).derive(shared)
        ciphertext = ChaCha20Poly1305(key).encrypt(nonce, archive, aad)
        encoded = base64.b64encode(ciphertext).decode("ascii")
        chunks = [encoded[i:i + 64] for i in range(0, len(encoded), 64)]
        descriptors = [
            {
                "index": i,
                "chars": len(text),
                "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
            }
            for i, text in enumerate(chunks)
        ]
        producer_identity = {
            "repository": "XoticHaze/mm-IBKR",
            "repository_visibility": "private",
            "ref": "refs/heads/assistant/cloud-signal-history-split-20260918",
            "workflow_ref": (
                "XoticHaze/mm-IBKR/.github/workflows/"
                "mmibkr-cloud-source-producer-r1.yml@"
                "refs/heads/assistant/cloud-signal-history-split-20260918"
            ),
            "event_name": "workflow_dispatch",
            "run_id": "77777",
            "run_attempt": "1",
        }
        attestation = {
            "schema": "mmibkr-cloud-source-private-attestation-v1",
            "source_ref": source_ref,
            "source_sha": source_sha,
            "plaintext_sha256": archive_sha,
            "archive_bytes": len(archive),
            "producer_identity": producer_identity,
            "attested_at": "2026-09-19T19:00:00Z",
        }
        manifest = {
            "schema": mod.RESPONSE_SCHEMA,
            "run_id": "12345",
            "harness": mod.HARNESS,
            "source_ref": source_ref,
            "source_sha": source_sha,
            "recipient_key_id": key_id,
            "sender_public_b64": base64.b64encode(sender_public).decode("ascii"),
            "salt_b64": base64.b64encode(salt).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
            "plaintext_sha256": archive_sha,
            "archive_bytes": len(archive),
            "ciphertext_bytes": len(ciphertext),
            "chunk_count": len(chunks),
            "chunks": descriptors,
            "private_attestation": attestation,
            "relay_identity": {
                "repository": "XoticHaze/research-compute-public-",
                "ref": "refs/heads/main",
                "workflow_ref": (
                    "XoticHaze/research-compute-public-/.github/workflows/"
                    "mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main"
                ),
                "event_name": "workflow_dispatch",
                "run_id": "99999",
                "run_attempt": "1",
            },
            "finalized_at": "2026-09-19T19:01:00Z",
        }
        ticket = {
            "repository": "XoticHaze/mm-IBKR",
            "head": source_sha,
            "archive_sha256": archive_sha,
            "archive_bytes": len(archive),
            "transport": "fleet_private_attested_source_v1",
        }
        return recipient_private, archive, manifest, chunks, ticket

    def test_consumes_only_exact_private_attested_archive(self):
        private_raw, archive, manifest, chunks, ticket = self.build_exchange()
        with tempfile.TemporaryDirectory() as td:
            key_path = Path(td) / "key.b64"
            key_path.write_text(base64.b64encode(private_raw).decode("ascii"))

            def api(authority_base, path, **kwargs):
                if path == "/v1/source-exchange/b1/response/12345":
                    return 200, json.dumps({
                        "ok": True,
                        "response": manifest,
                    }).encode(), {}
                if "/chunk/" in path:
                    index = int(path.rsplit("/", 1)[1])
                    raw = chunks[index].encode("ascii")
                    return 200, raw, {
                        "X-MMIBKR-Chunk-SHA256": hashlib.sha256(raw).hexdigest()
                    }
                if path == "/v1/source-exchange/b1/cleanup/12345":
                    return 200, b'{"ok":true}', {}
                raise AssertionError(path)

            result = mod.consume_attested_source(
                authority_base="https://fleet.example",
                run_id="12345",
                source_ticket=ticket,
                private_key_path=key_path,
                token_factory=lambda: "oidc",
                api=api,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["archive"], archive)
        self.assertTrue(result["private_attestation_verified"])
        self.assertFalse(result["private_repository_token_used"])

    def test_private_attestation_digest_mismatch_fails_closed(self):
        private_raw, archive, manifest, chunks, ticket = self.build_exchange()
        manifest["private_attestation"]["plaintext_sha256"] = "b" * 64
        with tempfile.TemporaryDirectory() as td:
            key_path = Path(td) / "key.b64"
            key_path.write_text(base64.b64encode(private_raw).decode("ascii"))

            def api(authority_base, path, **kwargs):
                return 200, json.dumps({
                    "ok": True,
                    "response": manifest,
                }).encode(), {}

            with self.assertRaisesRegex(
                RuntimeError,
                "attestation_digest_mismatch",
            ):
                mod.consume_attested_source(
                    authority_base="https://fleet.example",
                    run_id="12345",
                    source_ticket=ticket,
                    private_key_path=key_path,
                    token_factory=lambda: "oidc",
                    api=api,
                )


if __name__ == "__main__":
    unittest.main()
