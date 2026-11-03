"""Offline security/readiness regressions for the existing neutral broker probe."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "reference_broker_state_probe_receipt_v1.py"
spec = importlib.util.spec_from_file_location("reference_broker_probe", SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def synthetic_key() -> dict:
    # Structurally valid uncompressed encoding; the probe is not an EC validator.
    point = b"\x04" + bytes(range(1, 65))
    return {"public_b64": base64.b64encode(point).decode("ascii"),
            "key_id": "sha256:" + hashlib.sha256(point).hexdigest()}


class BrokerProbeTests(unittest.TestCase):
    def test_neutral_live_200_503_is_not_readiness(self):
        r = probe.receipt_from_observation({"ok": True}, {"error": "unavailable"}, 200, 503, "123")
        self.assertTrue(r["health_ok"])
        self.assertFalse(r["broker_signer_configured"])
        self.assertIsNone(r["broker_key_id"])
        self.assertEqual(r["readiness_observation"], "HEALTH_ONLY_KEY_UNVERIFIED_SOURCE_UNKNOWN")
        self.assertFalse(r["mutation_performed"])
        self.assertFalse(r["secrets_included"])
        self.assertFalse(r["deployed_source_identity_verified"])
        self.assertFalse(r["independent_signing_admission_verified"])

    def test_public_bytes_and_label_match(self):
        key = synthetic_key()
        r = probe.receipt_from_observation({"ok": True}, key, 200, 200, "123")
        self.assertTrue(r["broker_signer_configured"])
        self.assertEqual(r["broker_key_id"], key["key_id"])
        self.assertEqual(r["readiness_observation"], "HEALTH_AND_KEY_MATCH_NOT_SIGNED_ADMISSION")
        self.assertNotIn("public_b64", r)

    def test_forged_or_malformed_keys_fail(self):
        valid = synthetic_key()
        for bad in [
            {**valid, "key_id": "sha256:" + "f" * 64},
            {**valid, "public_b64": "%%%"},
            {**valid, "public_b64": base64.b64encode(b"\x02" * 33).decode()},
            {**valid, "public_b64": base64.b64encode(b"\x04" + bytes(63)).decode()},
            {"key_id": valid["key_id"]}, {}, [],
        ]:
            with self.subTest(bad=bad):
                r = probe.receipt_from_observation({"ok": True}, bad, 200, 200, "123")
                self.assertFalse(r["broker_signer_configured"])
                self.assertIsNone(r["broker_key_id"])

    def test_key_without_health_is_inconsistent(self):
        r = probe.receipt_from_observation({"ok": False}, synthetic_key(), 503, 200, "123")
        self.assertTrue(r["broker_signer_configured"])
        self.assertEqual(r["readiness_observation"], "KEY_ONLY_HEALTH_UNVERIFIED_SOURCE_UNKNOWN")

    def test_http_alone_never_attests_source_or_admission(self):
        key = synthetic_key()
        for h_status, k_status in ((200, 200), (200, 503), (503, 200), (503, 503)):
            with self.subTest(health=h_status, key=k_status):
                node = probe.receipt_from_observation(
                    {"ok": True}, key, h_status, k_status, "123"
                )
                self.assertFalse(node["deployed_source_identity_verified"])
                self.assertFalse(node["independent_signing_admission_verified"])

    def test_bad_and_oversized_json_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "body"
            for payload in [b"{secret", b"x" * (probe.MAX_RESPONSE_BYTES + 1)]:
                p.write_bytes(payload)
                self.assertEqual(probe._read_json(str(p)), {})


if __name__ == "__main__":
    unittest.main()
