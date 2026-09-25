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

    def test_accepts_exact_fleet_stream_attestation(self):
        _, _, manifest, _, ticket = self.build_exchange()
        manifest["private_attestation"] = {
            "schema": "mmibkr-cloud-source-fleet-stream-attestation-v1",
            "source_ref": ticket["head"],
            "source_sha": ticket["head"],
            "plaintext_sha256": ticket["archive_sha256"],
            "archive_bytes": ticket["archive_bytes"],
            "producer_identity": {
                "repository": "XoticHaze/mm-ibkr-runtime",
                "ref": "refs/heads/main",
                "workflow_ref": (
                    "XoticHaze/mm-ibkr-runtime/.github/workflows/"
                    "mmibkr-source-vault-bootstrap-r1.yml@refs/heads/main"
                ),
                "event_name": "workflow_dispatch",
                "run_id": "88888",
                "run_attempt": "1",
            },
            "stream_id": "123e4567-e89b-12d3-a456-426614174000",
            "attested_at": "2026-09-23T18:00:00Z",
            "source_transport": "fleet_authority_oidc_private_archive_stream",
        }

        verified = mod._producer_attestation(
            manifest["private_attestation"],
            ticket=ticket,
        )

        self.assertEqual(
            verified["schema"],
            "mmibkr-cloud-source-fleet-stream-attestation-v1",
        )
        self.assertEqual(verified["source_sha"], ticket["head"])
        self.assertEqual(verified["plaintext_sha256"], ticket["archive_sha256"])

    def test_fleet_stream_attestation_rejects_wrong_bootstrap_workflow(self):
        _, _, manifest, _, ticket = self.build_exchange()
        manifest["private_attestation"] = {
            "schema": "mmibkr-cloud-source-fleet-stream-attestation-v1",
            "source_ref": ticket["head"],
            "source_sha": ticket["head"],
            "plaintext_sha256": ticket["archive_sha256"],
            "archive_bytes": ticket["archive_bytes"],
            "producer_identity": {
                "repository": "XoticHaze/mm-ibkr-runtime",
                "ref": "refs/heads/main",
                "workflow_ref": (
                    "XoticHaze/mm-ibkr-runtime/.github/workflows/"
                    "unexpected.yml@refs/heads/main"
                ),
                "event_name": "workflow_dispatch",
                "run_id": "88888",
                "run_attempt": "1",
            },
            "stream_id": "123e4567-e89b-12d3-a456-426614174000",
            "attested_at": "2026-09-23T18:00:00Z",
            "source_transport": "fleet_authority_oidc_private_archive_stream",
        }

        with self.assertRaisesRegex(
            RuntimeError,
            "fleet_stream_producer_workflow_rejected",
        ):
            mod._producer_attestation(
                manifest["private_attestation"],
                ticket=ticket,
            )

    def test_fleet_stream_attestation_rejects_transport_drift(self):
        _, _, manifest, _, ticket = self.build_exchange()
        manifest["private_attestation"] = {
            "schema": "mmibkr-cloud-source-fleet-stream-attestation-v1",
            "source_ref": ticket["head"],
            "source_sha": ticket["head"],
            "plaintext_sha256": ticket["archive_sha256"],
            "archive_bytes": ticket["archive_bytes"],
            "producer_identity": {
                "repository": "XoticHaze/mm-ibkr-runtime",
                "ref": "refs/heads/main",
                "workflow_ref": (
                    "XoticHaze/mm-ibkr-runtime/.github/workflows/"
                    "mmibkr-source-vault-bootstrap-r1.yml@refs/heads/main"
                ),
                "event_name": "push",
                "run_id": "88888",
                "run_attempt": "1",
            },
            "stream_id": "123e4567-e89b-12d3-a456-426614174000",
            "attested_at": "2026-09-23T18:00:00Z",
            "source_transport": "unexpected_transport",
        }

        with self.assertRaisesRegex(
            RuntimeError,
            "fleet_stream_attestation_transport_rejected",
        ):
            mod._producer_attestation(
                manifest["private_attestation"],
                ticket=ticket,
            )

    def test_accepts_exact_hygiene_vault_attestation(self):
        _, _, manifest, _, ticket = self.build_exchange()
        manifest["private_attestation"] = {
            "schema": "mmibkr-cloud-source-vault-attestation-v1",
            "source_ref": ticket["head"],
            "source_sha": ticket["head"],
            "plaintext_sha256": ticket["archive_sha256"],
            "archive_bytes": ticket["archive_bytes"],
            "manifest_sha256": "c" * 64,
            "producer_identity": {
                "repository": "XoticHaze/research-compute-public-",
                "ref": "refs/heads/main",
                "workflow_ref": (
                    "XoticHaze/research-compute-public-/.github/workflows/"
                    "mmibkr-paper-account-hygiene-coordinator-r1.yml@refs/heads/main"
                ),
                "event_name": "push",
                "run_id": "99999",
                "run_attempt": "1",
            },
            "attested_at": "2026-09-23T20:44:00Z",
            "source_transport": "fleet_authority_exact_sha_encrypted_snapshot_vault",
            "snapshot_approval_mode": "static_code_pin",
        }

        verified = mod._producer_attestation(
            manifest["private_attestation"],
            ticket=ticket,
        )

        self.assertEqual(
            verified["schema"],
            "mmibkr-cloud-source-vault-attestation-v1",
        )
        self.assertEqual(verified["source_sha"], ticket["head"])
        self.assertEqual(verified["plaintext_sha256"], ticket["archive_sha256"])

    def test_vault_attestation_rejects_non_hygiene_workflow(self):
        _, _, manifest, _, ticket = self.build_exchange()
        manifest["private_attestation"] = {
            "schema": "mmibkr-cloud-source-vault-attestation-v1",
            "source_ref": ticket["head"],
            "source_sha": ticket["head"],
            "plaintext_sha256": ticket["archive_sha256"],
            "archive_bytes": ticket["archive_bytes"],
            "manifest_sha256": "c" * 64,
            "producer_identity": {
                "repository": "XoticHaze/research-compute-public-",
                "ref": "refs/heads/main",
                "workflow_ref": (
                    "XoticHaze/research-compute-public-/.github/workflows/"
                    "unexpected.yml@refs/heads/main"
                ),
                "event_name": "workflow_dispatch",
                "run_id": "99999",
                "run_attempt": "1",
            },
            "attested_at": "2026-09-23T20:44:00Z",
            "source_transport": "fleet_authority_exact_sha_encrypted_snapshot_vault",
            "snapshot_approval_mode": "static_code_pin",
        }

        with self.assertRaisesRegex(RuntimeError, "vault_producer_workflow_rejected"):
            mod._producer_attestation(
                manifest["private_attestation"],
                ticket=ticket,
            )

    def test_vault_attestation_rejects_transport_or_approval_drift(self):
        _, _, manifest, _, ticket = self.build_exchange()
        base = {
            "schema": "mmibkr-cloud-source-vault-attestation-v1",
            "source_ref": ticket["head"],
            "source_sha": ticket["head"],
            "plaintext_sha256": ticket["archive_sha256"],
            "archive_bytes": ticket["archive_bytes"],
            "manifest_sha256": "c" * 64,
            "producer_identity": {
                "repository": "XoticHaze/research-compute-public-",
                "ref": "refs/heads/main",
                "workflow_ref": (
                    "XoticHaze/research-compute-public-/.github/workflows/"
                    "mmibkr-paper-account-hygiene-coordinator-r1.yml@refs/heads/main"
                ),
                "event_name": "push",
                "run_id": "99999",
                "run_attempt": "1",
            },
            "attested_at": "2026-09-23T20:44:00Z",
            "source_transport": "fleet_authority_exact_sha_encrypted_snapshot_vault",
            "snapshot_approval_mode": "static_code_pin",
        }
        drift = dict(base)
        drift["source_transport"] = "unexpected_transport"
        with self.assertRaisesRegex(RuntimeError, "vault_attestation_transport_rejected"):
            mod._producer_attestation(drift, ticket=ticket)

        drift = dict(base)
        drift["snapshot_approval_mode"] = "unreviewed"
        with self.assertRaisesRegex(RuntimeError, "vault_attestation_approval_mode_rejected"):
            mod._producer_attestation(drift, ticket=ticket)

    def test_unknown_private_attestation_schema_still_fails_closed(self):
        _, _, manifest, _, ticket = self.build_exchange()
        manifest["private_attestation"]["schema"] = "mmibkr-untrusted-attestation-v999"

        with self.assertRaisesRegex(
            RuntimeError,
            "private_source_attestation_schema_rejected",
        ):
            mod._producer_attestation(
                manifest["private_attestation"],
                ticket=ticket,
            )

    def test_chunk_401_refreshes_oidc_and_retries_same_chunk_once(self):
        private_raw, archive, manifest, chunks, ticket = self.build_exchange()
        token_values = iter(["oidc-initial", "oidc-refreshed"])
        token_calls = []
        chunk_calls = []

        def token_factory():
            value = next(token_values)
            token_calls.append(value)
            return value

        with tempfile.TemporaryDirectory() as td:
            key_path = Path(td) / "key.b64"
            key_path.write_text(base64.b64encode(private_raw).decode("ascii"))

            def api(authority_base, path, **kwargs):
                token = kwargs["token"]
                if path == "/v1/source-exchange/b1/response/12345":
                    self.assertEqual(token, "oidc-initial")
                    return 200, json.dumps({
                        "ok": True,
                        "response": manifest,
                    }).encode(), {}
                if "/chunk/" in path:
                    chunk_calls.append((path, token))
                    if token == "oidc-initial":
                        return 401, b'{"ok":false}', {}
                    index = int(path.rsplit("/", 1)[1])
                    raw = chunks[index].encode("ascii")
                    return 200, raw, {
                        "X-MMIBKR-Chunk-SHA256": hashlib.sha256(raw).hexdigest()
                    }
                if path == "/v1/source-exchange/b1/cleanup/12345":
                    self.assertEqual(token, "oidc-refreshed")
                    return 200, b'{"ok":true}', {}
                raise AssertionError(path)

            result = mod.consume_attested_source(
                authority_base="https://fleet.example",
                run_id="12345",
                source_ticket=ticket,
                private_key_path=key_path,
                token_factory=token_factory,
                api=api,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["archive"], archive)
        self.assertEqual(token_calls, ["oidc-initial", "oidc-refreshed"])
        self.assertEqual(
            chunk_calls,
            [
                ("/v1/source-exchange/b1/response/12345/chunk/0", "oidc-initial"),
                ("/v1/source-exchange/b1/response/12345/chunk/0", "oidc-refreshed"),
            ],
        )

    def test_chunk_401_retry_fails_closed_after_one_refresh(self):
        private_raw, _, manifest, _, ticket = self.build_exchange()
        token_values = iter(["oidc-initial", "oidc-refreshed"])
        token_calls = []
        chunk_calls = []

        def token_factory():
            value = next(token_values)
            token_calls.append(value)
            return value

        with tempfile.TemporaryDirectory() as td:
            key_path = Path(td) / "key.b64"
            key_path.write_text(base64.b64encode(private_raw).decode("ascii"))

            def api(authority_base, path, **kwargs):
                token = kwargs["token"]
                if path == "/v1/source-exchange/b1/response/12345":
                    return 200, json.dumps({
                        "ok": True,
                        "response": manifest,
                    }).encode(), {}
                if "/chunk/" in path:
                    chunk_calls.append((path, token))
                    return 401, b'{"ok":false}', {}
                raise AssertionError(path)

            with self.assertRaisesRegex(
                RuntimeError,
                "b1_attested_source_chunk_http_401:0",
            ):
                mod.consume_attested_source(
                    authority_base="https://fleet.example",
                    run_id="12345",
                    source_ticket=ticket,
                    private_key_path=key_path,
                    token_factory=token_factory,
                    api=api,
                )

        self.assertEqual(token_calls, ["oidc-initial", "oidc-refreshed"])
        self.assertEqual(
            chunk_calls,
            [
                ("/v1/source-exchange/b1/response/12345/chunk/0", "oidc-initial"),
                ("/v1/source-exchange/b1/response/12345/chunk/0", "oidc-refreshed"),
            ],
        )

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
