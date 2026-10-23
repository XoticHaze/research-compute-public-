"""Synthetic, offline tests for redacted *observation*, not public storage certification."""
from __future__ import annotations
import base64
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import commandcenter_public_exchange_redacted_inventory_v1 as audit

SHA = "a" * 40
BAD = "b" * 40
TREE = "c" * 40
PRIVATE_MARKER = "SYNTHETIC_PRIVATE_DO_NOT_PUBLISH"


def tree(*entries):
    return {
        "sha": TREE, "truncated": False,
        "tree": [{"path": path, "type": "blob", "sha": sha, "size": size}
                 for path, sha, size in entries],
    }


class PublicExchangeInventoryTests(unittest.TestCase):
    def test_exact_current_tip_counts_without_emitting_paths(self):
        sample = tree(
            ("rendezvous/returns/private-client.json", SHA, 150),
            ("rendezvous/responses/broker-secret.txt", BAD, 201),
            ("rendezvous/recipients/sensitive.json", SHA, 15),
            ("rendezvous/producer-requests/research.json", BAD, 51),
            ("rendezvous/receipts/a.json", SHA, 5),
            ("rendezvous/proof-chunks/chunk.bin", BAD, 2048),
            ("rendezvous/diagnostics/report.txt", BAD, 81),
            ("research/legacy-source.json", SHA, 70),
        )
        result = audit.audit_tree(sample)
        self.assertEqual(result["total_files"], 8)
        for category in ("returns", "responses", "recipients", "producer_requests",
                         "receipts", "proof_chunks", "diagnostics", "other"):
            self.assertEqual(result["buckets"][category]["files"], 1)
        emitted = json.dumps(result)
        for forbidden in ("private-client", "broker-secret", "sensitive.json",
                          "legacy-source", PRIVATE_MARKER):
            self.assertNotIn(forbidden, emitted)
        self.assertFalse(result["history_erased"])
        self.assertFalse(result["storage_privacy_certified"])
        self.assertFalse(result["r2_confidential_execution_proven"])

    def test_bounded_value_redacted_metadata_detection(self):
        fixture = tree(("rendezvous/returns/very-private.json", SHA, 99))
        secret = PRIVATE_MARKER
        content = json.dumps({"ciphertext_b64": "abcdef", "plaintext_sha256": secret,
                              "authority": "secret-business", "harness": "private-job"}).encode()
        result = audit.audit_tree(fixture, fetch_blob=lambda sha: content)
        self.assertEqual(result["samples"]["forbidden_outer_metadata"], 1)
        self.assertEqual(result["samples"]["inspected"], 1)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("secret-business", json.dumps(result))
        self.assertNotIn("very-private", json.dumps(result))

    def test_ciphertext_only_sample_is_not_falsely_certified(self):
        content = json.dumps({"schema": "opaque-capsule-p256-aesgcm-v1",
                              "ciphertext_sha256": PRIVATE_MARKER}).encode()
        result = audit.audit_tree(tree(("rendezvous/responses/a.json", SHA, 61)),
                                  fetch_blob=lambda sha: content)
        self.assertEqual(result["samples"]["forbidden_outer_metadata"], 0)
        self.assertFalse(result["storage_privacy_certified"])
        self.assertFalse(result["private_consumer_ack_proven"])

    def test_nested_metadata_is_detected_without_values_or_false_clean_depth(self):
        secret = PRIVATE_MARKER
        fixture = tree(("rendezvous/returns/private.json", SHA, 150))
        nested = json.dumps({"ciphertext_b64": "ciphertext", "wrapper": {
            "entries": [{"PLAINTEXT_SHA256": secret, "harness": secret}]
        }}).encode()
        result = audit.audit_tree(fixture, fetch_blob=lambda sha: nested)
        self.assertEqual(result["samples"]["forbidden_outer_metadata"], 0)
        self.assertEqual(result["samples"]["forbidden_nested_metadata"], 1)
        self.assertEqual(result["samples"]["nested_scan_incomplete"], 0)
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn("private.json", json.dumps(result))

        too_deep = {"ciphertext_b64": "ciphertext"}
        for _ in range(audit.MAX_NESTED_DEPTH + 2):
            too_deep = {"wrapper": too_deep}
        result = audit.audit_tree(fixture, fetch_blob=lambda sha: json.dumps(too_deep).encode())
        self.assertEqual(result["samples"]["nested_scan_incomplete"], 1)
        self.assertEqual(result["samples"]["forbidden_nested_metadata"], 0)
        self.assertFalse(result["storage_privacy_certified"])

    def test_truncation_and_missing_tree_fail_closed(self):
        for broken in (None, {}, {"sha": TREE, "truncated": True, "tree": []},
                       {"sha": "invalid", "truncated": False, "tree": []},
                       {"sha": TREE, "truncated": False, "tree": "secret"}):
            with self.subTest(broken=type(broken).__name__), self.assertRaises(audit.AuditRejected):
                audit.audit_tree(broken)

    def test_invalid_sha_bad_size_or_path_fail_closed(self):
        for e in (("rendezvous/returns/private", "INVALID", 3),
                  ("rendezvous/returns/private", SHA, -1),
                  ("rendezvous/returns/private", SHA, True),
                  (123, SHA, 1)):
            with self.subTest(e=e), self.assertRaises(audit.AuditRejected):
                audit.audit_tree(tree(e))

    def test_json_parse_failure_classified_without_exposing_blob(self):
        result = audit.audit_tree(
            tree(("rendezvous/responses/note.json", SHA, 55)),
            fetch_blob=lambda sha: PRIVATE_MARKER.encode(),
        )
        self.assertEqual(result["samples"]["json_parse_failed"], 1)
        self.assertNotIn(PRIVATE_MARKER, json.dumps(result))

    def test_non_json_blob_never_misclassified_as_ciphertext(self):
        result = audit.audit_tree(
            tree(("rendezvous/returns/note.txt", SHA, 55)),
            fetch_blob=lambda sha: PRIVATE_MARKER.encode(),
        )
        self.assertEqual(result["samples"]["inspected"], 0)
        self.assertEqual(result["buckets"]["returns"]["other_files"], 1)

    def test_sample_selection_is_bounded_and_deduped(self):
        entries = tuple((f"rendezvous/returns/{i:04d}.json", f"{i:040x}", 150)
                        for i in range(1, 501))
        called = []
        result = audit.audit_tree(tree(*entries), fetch_blob=lambda sha: called.append(sha) or b"{}")
        self.assertLessEqual(result["samples"]["inspected"], audit.MAX_TOTAL_SAMPLES)
        self.assertEqual(len(called), 3)
        self.assertEqual(result["buckets"]["returns"]["files"], 500)

    def test_cli_failure_never_emits_http_response_or_secret(self):
        capture = io.StringIO()
        with patch("sys.argv", ["audit", "--live"]), patch.object(
            audit, "_live_tree", side_effect=RuntimeError(PRIVATE_MARKER)
        ), redirect_stdout(capture):
            self.assertEqual(audit.main(), 1)
        self.assertNotIn(PRIVATE_MARKER, capture.getvalue())
        self.assertEqual(capture.getvalue().strip(),
                         'PUBLIC_EXCHANGE_AUDIT={"status":"FAIL_CLOSED","storage_privacy_certified":false}')

    def test_source_wiring_is_get_only_and_no_credential_echo(self):
        from pathlib import Path
        script = Path(audit.__file__).read_text()
        self.assertIn("urllib.request.Request", script)
        self.assertNotIn('method="POST"', script)
        self.assertNotIn('method="DELETE"', script)
        self.assertNotIn("print(node)", script)
        self.assertNotIn("print(token)", script)


if __name__ == "__main__":
    unittest.main()
