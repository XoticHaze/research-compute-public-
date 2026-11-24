"""Native isolated crypto and fail-closed tests for the private A1 consumer.

Synthetic reference H1, no PHI, no Cloudflare/GitHub credentials, no release
admission, no private GitHub Actions. These tests exercise actual audited
A1 P-256 ECDH + AES-GCM bytes, not an injected mock decryptor.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from scripts.opaque_bidirectional_capsule_p256_aesgcm_v1 import (
    generate_keypair, seal
)
from scripts import reference_private_a1_terminal_v1 as a1

RUN = "42362392538"
REQ = "cc809-reference-private-001"
PAYLOAD = b"synthetic-approved-nonphi-h1-plaintext"


def envelope(*, payload=PAYLOAD, request_id=REQ, ok=True,
             result_fields=None, run_id=RUN, direction="result", public=None):
    node = {
        "schema": "reference-private-result-v1",
        "request_id": request_id,
        "ok": True,
        "output_b64": base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii"),
        "cleanup_contract": "PROCESS_EXIT_NO_PLAINTEXT_ARTIFACT",
    } if ok else {
        "schema": "reference-private-result-v1",
        "request_id": request_id,
        "ok": False,
        "error_type": "SyntheticFailure",
        "error_code": "PRIVATE_SIGNAL_SHOULD_NOT_ESCAPE",
        "cleanup_contract": "PROCESS_EXIT_NO_PLAINTEXT_ARTIFACT",
    }
    if result_fields is not None:
        node.update(result_fields)
    return json.dumps(seal(
        json.dumps(node, sort_keys=True, separators=(",", ":")).encode(),
        recipient_public_b64=public,
        run_id=run_id,
        direction=direction,
    ), sort_keys=True).encode("utf-8")


class PrivateA1TerminalTests(unittest.TestCase):
    def setUp(self):
        self.private, self.public, _ = generate_keypair()
        self.raw = envelope(public=self.public)

    def accept(self, raw=None, **kwargs):
        return a1.accept_reference_h1_result(
            self.raw if raw is None else raw,
            return_private_b64=kwargs.pop("return_private_b64", self.private),
            expected_run_id=kwargs.pop("expected_run_id", RUN),
            expected_request_id=kwargs.pop("expected_request_id", REQ),
            expected_request_payload=kwargs.pop("expected_request_payload", PAYLOAD),
        )

    def test_genuine_p256_aesgcm_proof_private_only(self):
        node = self.accept()
        self.assertEqual(node["status"], "PRIVATE_A1_H1_CRYPTOGRAPHIC_RESULT_VERIFIED")
        self.assertTrue(node["envelope_authenticated"])
        self.assertTrue(node["request_content_match"])
        for denied in ("release_signature_verified", "trusted_placement_admitted",
                       "production_generic_router_admitted", "result_plaintext_published"):
            self.assertIs(node[denied], False)
        self.assertNotIn(PAYLOAD.decode(), json.dumps(node))
        self.assertNotIn(self.private, json.dumps(node))

    def test_reject_wrong_request_run_return_key_or_expected_private_payload(self):
        other_private, _, _ = generate_keypair()
        for changed in (
            {"expected_run_id": RUN + "1"},
            {"expected_request_id": REQ + "x"},
            {"return_private_b64": other_private},
            {"expected_request_payload": b"wrong private request"},
        ):
            with self.subTest(changed=next(iter(changed))):
                with self.assertRaisesRegex(a1.PrivateA1ResultRejected,
                                            "^PRIVATE_A1_RESULT_REJECTED$"):
                    self.accept(**changed)

    def test_reject_wrong_direction_wrong_run_and_non_padded_public_envelope(self):
        for raw in (
            envelope(public=self.public, direction="request"),
            envelope(public=self.public, run_id="9999"),
            json.dumps(dict(json.loads(self.raw), unwanted="meaning")).encode(),
        ):
            with self.assertRaisesRegex(a1.PrivateA1ResultRejected, "PRIVATE_A1_RESULT_REJECTED"):
                self.accept(raw)

    def test_reject_tamper_and_server_rejection_without_leaking_private_error(self):
        changed = json.loads(self.raw)
        changed["ciphertext_sha256"] = "0" * 64
        for raw in (
            json.dumps(changed).encode(),
            envelope(public=self.public, ok=False),
            envelope(public=self.public, result_fields={"diagnostic": "secret"}),
            envelope(public=self.public, result_fields={"cleanup_contract":"missing"}),
        ):
            with self.assertRaisesRegex(a1.PrivateA1ResultRejected,
                                        "^PRIVATE_A1_RESULT_REJECTED$"):
                self.accept(raw)

    def test_duplicate_public_json_and_noncanonical_private_identity_fail_closed(self):
        raw = self.raw.decode()
        duplicate = raw.replace('"schema":', '"schema":"unknown","schema":', 1).encode()
        with self.assertRaisesRegex(a1.PrivateA1ResultRejected, "PRIVATE_A1_RESULT_REJECTED"):
            self.accept(duplicate)
        with self.assertRaisesRegex(a1.PrivateA1ResultRejected, "PRIVATE_A1_RESULT_REJECTED"):
            self.accept(expected_run_id="00" + RUN)

    def test_private_receipt_create_once_and_not_public_status(self):
        receipt = self.accept()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "receipt.json"
            a1.write_private_receipt(receipt, target)
            self.assertTrue(target.is_file())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(target.read_text()), receipt)
            with self.assertRaisesRegex(a1.PrivateA1ResultRejected, "PRIVATE_A1_RESULT_REJECTED"):
                a1.write_private_receipt(receipt, target)

    def test_private_cli_prints_constant_status_only_and_creates_exclusive_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            envelope_file = Path(temp) / "result.json"
            payload_file = Path(temp) / "request.bin"
            receipt_file = Path(temp) / "private.json"
            envelope_file.write_bytes(self.raw)
            payload_file.write_bytes(PAYLOAD)
            argv = ["reference_private_a1_terminal_v1.py",
                    "--envelope", str(envelope_file),
                    "--request-payload", str(payload_file),
                    "--run-id", RUN, "--request-id", REQ,
                    "--private-receipt", str(receipt_file)]
            buf = io.StringIO()
            with patch("sys.argv", argv), patch.dict(os.environ, {
                "REFERENCE_PRIVATE_A1_RETURN_KEY_B64": self.private
            }):
                with redirect_stdout(buf):
                    code = a1.main()
            self.assertEqual(code, 0)
            self.assertEqual(buf.getvalue(), "REFERENCE_PRIVATE_A1_TERMINAL=CRYPTO_VERIFIED_ONLY\n")
            self.assertTrue(receipt_file.is_file())
            self.assertNotIn(REQ, buf.getvalue())
            # Duplicate private receipt must fail with constant output.
            buf = io.StringIO()
            with patch("sys.argv", argv), patch.dict(os.environ, {
                "REFERENCE_PRIVATE_A1_RETURN_KEY_B64": self.private
            }):
                with redirect_stdout(buf):
                    code = a1.main()
            self.assertEqual(code, 1)
            self.assertEqual(buf.getvalue(), "REFERENCE_PRIVATE_A1_TERMINAL=FAIL_CLOSED\n")

    def test_failures_publish_no_receipt_and_no_private_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "never.json"
            envelope_file = Path(temp) / "tampered.json"
            payload_file = Path(temp) / "request.bin"
            envelope_file.write_bytes(b'{"schema":"private-leak-marker"}')
            payload_file.write_bytes(PAYLOAD)
            buf = io.StringIO()
            with patch("sys.argv", ["tool", "--envelope", str(envelope_file),
                    "--request-payload", str(payload_file), "--run-id", RUN,
                    "--request-id", REQ, "--private-receipt", str(out)]), \
                    patch.dict(os.environ, {
                        "REFERENCE_PRIVATE_A1_RETURN_KEY_B64": self.private,
                    }):
                with redirect_stdout(buf):
                    self.assertEqual(a1.main(), 1)
            self.assertFalse(out.exists())
            self.assertEqual(buf.getvalue(), "REFERENCE_PRIVATE_A1_TERMINAL=FAIL_CLOSED\n")


if __name__ == "__main__":
    unittest.main()
