import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

SRC = Path(__file__).parents[1] / "scripts/cloudflare_worker_status_readonly_r1.py"
spec = importlib.util.spec_from_file_location("cloudflare_status", SRC)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ACCOUNT = "a" * 32
TOKEN = "secret-token-not-for-logs"
REQUEST = {"schema": module.REQUEST_SCHEMA, "request_id": "MW-20261103072526405-cf-1",
           "operation": "cloudflare.worker_status", "worker": "mmibkr-operator-console"}
DID = "182bd5e5-6e1a-4fe4-a799-aa6d9a6ab26e"
VID = "023e105f-2a42-4f8b-a1c1-73f6a2a30c0f"

class FakeResponse:
    status = 200
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, *_): return json.dumps(self.value).encode()

class CloudflareReadOnlyContract(unittest.TestCase):
    def test_valid_status_sanitizes_secrets_and_unknown_binding(self):
        raw = {"success": True, "result": {"bindings": [
            {"name": "ACCESS_AUD", "type": "secret_text", "text": "VERY-SENSITIVE"},
            {"name": "UNKNOWN_KEY", "type": "secret_text", "text": "hidden"}
        ]}}
        with patch.object(module, "urlopen", return_value=FakeResponse(raw)) as open_fn:
            receipt, success = module.execute(REQUEST, {"CF_ACCOUNT_ID": ACCOUNT,"CF_READ_TOKEN": TOKEN})
        self.assertTrue(success)
        self.assertEqual(open_fn.call_args.args[0].method, "GET")
        self.assertIn("/workers/scripts/mmibkr-operator-console/settings", open_fn.call_args.args[0].full_url)
        self.assertEqual(receipt["result"]["unreported_binding_count"], 1)
        self.assertTrue(receipt["result"]["approved_binding_presence"]["ACCESS_AUD"])
        for raw_value in (ACCOUNT, TOKEN, "VERY-SENSITIVE", "hidden", "UNKNOWN_KEY"):
            self.assertNotIn(raw_value, json.dumps(receipt))

    def test_release_status_active_version_sanitized(self):
        doc = {"success": True, "result": {"deployments": [{"id": DID,
            "created_on": "2026-11-03T06:00:00Z", "versions": [{"version_id": VID, "percentage": 100}],
            "author_email": "secret@example.com", "annotations": {"workers/message": "private"}}]}}
        req = dict(REQUEST, operation="cloudflare.release_status")
        with patch.object(module, "urlopen", return_value=FakeResponse(doc)):
            receipt, success = module.execute(req, {"CF_ACCOUNT_ID": ACCOUNT, "CF_READ_TOKEN": TOKEN})
        self.assertTrue(success)
        self.assertEqual(receipt["result"]["status"], "ACTIVE_DEPLOYMENT_OBSERVED_NOT_SOURCE_ATTESTED")
        self.assertTrue(receipt["result"]["single_version_100_percent"])
        for raw_value in (DID, VID, ACCOUNT, TOKEN, "secret@example.com", "private"):
            self.assertNotIn(raw_value, json.dumps(receipt))

    def test_foreign_account_worker_and_operation_rejected_before_network(self):
        cases = [dict(REQUEST, worker="reference-release-broker-v1"),
                 dict(REQUEST, operation="cloudflare.worker_deploy"),
                 dict(REQUEST, request_id="../../bad"),
                 dict(REQUEST, additional="hello"),
                 dict(REQUEST, schema="different")]
        with patch.object(module, "urlopen") as open_fn:
            for bad in cases:
                with self.assertRaises(ValueError): module.execute(bad, {"CF_ACCOUNT_ID":ACCOUNT,"CF_READ_TOKEN":TOKEN})
            open_fn.assert_not_called()

    def test_bad_deployment_weights_fail_closed(self):
        req = dict(REQUEST, operation="cloudflare.release_status")
        doc = {"success": True, "result": {"deployments": [{"id": DID,
            "created_on": "2026-11-03T06:00:00Z", "versions": [{"version_id": VID,"percentage": 99}]}]}}
        with patch.object(module, "urlopen", return_value=FakeResponse(doc)):
            receipt, success = module.execute(req, {"CF_ACCOUNT_ID": ACCOUNT,"CF_READ_TOKEN": TOKEN})
        self.assertFalse(success)
        self.assertEqual(receipt["result"]["status"], "DEPLOYMENT_PERCENTAGE_REJECTED")

    def test_cloudflare_denial_never_leaks_error_response(self):
        exc = HTTPError("https://api.cloudflare.com/secret", 403, "sensitive-text", None, None)
        with patch.object(module, "urlopen", side_effect=exc):
            receipt, success = module.execute(REQUEST,{"CF_ACCOUNT_ID":ACCOUNT,"CF_READ_TOKEN":TOKEN})
        self.assertFalse(success)
        self.assertEqual(receipt["result"]["status"], "CLOUDFLARE_SCOPE_DENIED")
        self.assertNotIn("sensitive", json.dumps(receipt))

    def test_missing_credentials_fail_closed(self):
        with patch.object(module, "urlopen") as open_fn:
            receipt, success = module.execute(REQUEST, {})
            open_fn.assert_not_called()
        self.assertFalse(success)
        self.assertEqual(receipt["result"]["status"], "EXISTING_READ_CREDENTIAL_UNAVAILABLE")

    def test_empty_deployments_not_source_attested(self):
        doc = {"success": True, "result": {"deployments": []}}
        with patch.object(module, "urlopen", return_value=FakeResponse(doc)):
            receipt, success = module.execute(dict(REQUEST, operation="cloudflare.release_status"),
                                               {"CF_ACCOUNT_ID":ACCOUNT,"CF_READ_TOKEN":TOKEN})
        self.assertFalse(success)
        self.assertEqual(receipt["result"]["status"], "ACTIVE_DEPLOYMENT_NOT_OBSERVED")

    def test_non_200_success_false_fails_closed(self):
        with patch.object(module, "urlopen", return_value=FakeResponse({"success":False,"errors":[{"message":"token"}]})):
            receipt, success = module.execute(REQUEST,{"CF_ACCOUNT_ID":ACCOUNT,"CF_READ_TOKEN":TOKEN})
        self.assertFalse(success)
        self.assertEqual(receipt["result"]["status"], "CLOUDFLARE_RESPONSE_REJECTED")

if __name__ == "__main__": unittest.main()
