from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import ibkr_b1_warm_state_fleet_v1 as mod


class B1WarmStateFleetTests(unittest.TestCase):
    def test_publish_chunks_only_encrypted_envelope_and_finalizes(self):
        calls = []

        def api(authority_base, path, **kwargs):
            calls.append((path, kwargs))
            if "/chunk/" in path:
                raw = kwargs["raw"]
                self.assertIsInstance(raw, bytes)
                self.assertNotIn(b"plaintext-gateway-state", raw)
                return 200, b'{"ok":true}', {}
            return 200, json.dumps({
                "ok": True,
                "status": "finalized",
            }).encode(), {}

        with tempfile.TemporaryDirectory() as td:
            envelope = Path(td) / "ibkr-b1-warm-state.tgz.enc"
            envelope.write_bytes(
                b"MMIBKRWS1" + b"x" * 200_000
            )
            result = mod.publish(
                authority_base="https://fleet.example",
                run_id="12345",
                envelope_path=envelope,
                token_factory=lambda: "oidc",
                api=api,
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["fleet_stores_encrypted_state_only"])
        self.assertGreater(result["chunk_count"], 1)
        self.assertTrue(calls[-1][0].endswith("/manifest"))

    def test_fetch_reassembles_and_verifies_exact_encrypted_envelope(self):
        blob = b"MMIBKRWS1" + b"z" * 150_000
        import base64
        encoded = base64.b64encode(blob).decode("ascii")
        chunks = [
            encoded[i:i + mod.CHUNK_CHARS]
            for i in range(0, len(encoded), mod.CHUNK_CHARS)
        ]
        descriptors = [
            {
                "index": i,
                "chars": len(text),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
            for i, text in enumerate(chunks)
        ]
        manifest = {
            "schema": mod.MANIFEST_SCHEMA,
            "run_id": "77777",
            "generation": "77777",
            "envelope_sha256": hashlib.sha256(blob).hexdigest(),
            "envelope_bytes": len(blob),
            "chunk_count": len(chunks),
            "chunks": descriptors,
            "producer_identity": {},
            "finalized_at": "2026-09-19T00:00:00Z",
            "encrypted_state_only": True,
            "broker_credentials_included": False,
        }

        def api(authority_base, path, **kwargs):
            if path == "/v1/b1-warm-state/latest":
                return 200, json.dumps({
                    "ok": True,
                    "manifest": manifest,
                }).encode(), {}
            index = int(path.rsplit("/", 1)[1])
            raw = chunks[index].encode("ascii")
            return 200, raw, {
                "X-MMIBKR-Chunk-SHA256": hashlib.sha256(raw).hexdigest(),
            }

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "warm.enc"
            result = mod.fetch_latest(
                authority_base="https://fleet.example",
                run_id="12345",
                output=output,
                token_factory=lambda: "oidc",
                api=api,
            )
            self.assertEqual(output.read_bytes(), blob)

        self.assertTrue(result["restored"])
        self.assertEqual(result["generation"], "77777")

    def test_fetch_not_found_is_clean_cold_signal(self):
        result = mod.fetch_latest(
            authority_base="https://fleet.example",
            run_id="12345",
            output="/unused",
            token_factory=lambda: "oidc",
            api=lambda *a, **k: (404, b'{"error":"warm_state_not_found"}', {}),
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["restored"])
        self.assertEqual(result["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
