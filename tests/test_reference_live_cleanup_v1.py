from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.live_reference_harness_v1 as harness


SENSITIVE_MARKER = b"synthetic-sensitive-marker"


class ReferenceLiveCleanupProofTests(unittest.TestCase):
    def _exercise(self, operation: str) -> tuple[int, list[tuple[str, dict]]]:
        request_payload = {
            "schema": harness.REQUEST_SCHEMA,
            "request_id": "cleanup-proof",
            "operation": operation,
            "payload_b64": base64.b64encode(SENSITIVE_MARKER).decode("ascii"),
            "return_public_b64": "synthetic-return-public",
        }
        captured: list[tuple[str, dict]] = []

        def fake_get(path: str) -> dict | None:
            if path == "proof/live/bootstrap-intent.json":
                return {"schema": "reference-live-intent-v1", "intent": {"schema": "synthetic"}}
            if path.endswith("/request.json"):
                return {"schema": "opaque-request"}
            return None

        def fake_put(path: str, node: dict) -> None:
            captured.append((path, json.loads(json.dumps(node))))

        env = {
            "GITHUB_RUN_ID": "123456789",
            "GITHUB_REPOSITORY": "XoticHaze/research-compute-public-",
            "GITHUB_REF_NAME": "main",
        }
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, env, clear=False):
            old = Path.cwd()
            os.chdir(td)
            try:
                with (
                    patch.object(harness, "generate_keypair", return_value=("synthetic-secret", "synthetic-public", "worker-key-id")),
                    patch.object(harness, "_broker_release", return_value={"schema": "synthetic-ticket"}),
                    patch.object(harness, "_get_json", side_effect=fake_get),
                    patch.object(harness, "_put_json", side_effect=fake_put),
                    patch.object(harness, "open_capsule", return_value=json.dumps(request_payload).encode()),
                    patch.object(harness, "seal", return_value={"schema": "opaque-result", "ciphertext_b64": "Y2lwaGVydGV4dA=="}),
                ):
                    rc = harness._main()

                for path in Path(td).rglob("*"):
                    if path.is_file():
                        self.assertNotIn(SENSITIVE_MARKER, path.read_bytes())
            finally:
                os.chdir(old)

        public_bytes = json.dumps(captured, sort_keys=True).encode()
        self.assertNotIn(SENSITIVE_MARKER, public_bytes)
        self.assertNotIn(b"synthetic-secret", public_bytes)
        return rc, captured

    def test_success_cleanup(self) -> None:
        rc, captured = self._exercise("H1")
        self.assertEqual(0, rc)
        self.assertTrue(any(path.endswith("/result.json") for path, _ in captured))

    def test_forced_operation_failure_cleanup(self) -> None:
        rc, captured = self._exercise("FORCED_FAILURE")
        self.assertEqual(1, rc)
        self.assertTrue(any(path.endswith("/result.json") for path, _ in captured))


if __name__ == "__main__":
    unittest.main()
