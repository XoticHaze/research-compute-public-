"""Offline contract tests; no IBKR login, credentials, Cloudflare or orders."""
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "scripts/mmibkr_paper_gateway_handoff_probe_v1.py"
spec = importlib.util.spec_from_file_location("handoff", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
RUN = "38390000000"
HEAD = "a" * 40


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.checkpoint, self.predecessor = m.build_predecessor(RUN, HEAD, "predecessor")
        self.raw = m.canonical_bytes(self.checkpoint)

    def accept(self, receipt=None, raw=None, run=RUN, head=HEAD, job="successor"):
        return m.accept_successor(self.raw if raw is None else raw,
                                  self.predecessor if receipt is None else receipt,
                                  run, head, job)

    def test_valid_cross_job_synthetic_preparation_is_not_broker_login(self):
        result = self.accept()
        self.assertEqual(result["status"], "SYNTHETIC_SUCCESSOR_PREPARED")
        self.assertTrue(result["exact_predecessor_checkpoint_restored"])
        self.assertTrue(result["independent_job_boundary"])
        self.assertFalse(result["gateway_authentication_transfer_proven"])
        self.assertFalse(result["jts_transfer_proven"])
        self.assertFalse(result["execution_ownership_granted"])
        self.assertFalse(result["production_handoff_ready"])
        self.assertFalse(result["broker_login_attempted"])
        self.assertEqual(result["ibc_reauthentication_requirement"], "UNTESTED")

    def test_predecessor_receipt_denies_secrets_live_and_authenticated_claims(self):
        self.assertFalse(self.predecessor["broker_credentials_used"])
        self.assertFalse(self.predecessor["gateway_authentication_transferred"])
        self.assertFalse(self.predecessor["live_orders_enabled"])
        self.assertFalse(self.predecessor["predecessor_gateway_active"])
        self.assertFalse(self.predecessor["predecessor_execution_owner_active"])
        self.assertTrue(self.predecessor["predecessor_released"])
        self.assertIsNone(self.checkpoint["broker_session"])
        self.assertIsNone(self.checkpoint["account_id"])

    def test_tampered_checkpoint_fails(self):
        with self.assertRaisesRegex(m.GateError, "hash_mismatch"):
            self.accept(raw=self.raw + b" ")

    def test_checkpoint_contains_broker_identity_fails_even_with_matching_digest(self):
        tampered = dict(self.checkpoint, account_id="DU_PAPER_ACCOUNT")
        raw = m.canonical_bytes(tampered)
        receipt = dict(self.predecessor, checkpoint_sha256=m.digest(raw))
        with self.assertRaisesRegex(m.GateError, "checkpoint_not_exact_synthetic_fixture"):
            self.accept(receipt=receipt, raw=raw)

    def test_checkpoint_contains_jts_session_fails(self):
        tampered = dict(self.checkpoint, broker_session="Jts_state")
        raw = m.canonical_bytes(tampered)
        receipt = dict(self.predecessor, checkpoint_sha256=m.digest(raw))
        with self.assertRaises(m.GateError):
            self.accept(receipt=receipt, raw=raw)

    def test_checkpoint_contains_unknown_secret_field_fails(self):
        tampered = dict(self.checkpoint, access_token="PRIVATE")
        raw = m.canonical_bytes(tampered)
        receipt = dict(self.predecessor, checkpoint_sha256=m.digest(raw))
        with self.assertRaisesRegex(m.GateError, "checkpoint_fields_not_exact"):
            self.accept(receipt=receipt, raw=raw)

    def test_stale_predecessor_run_fails(self):
        with self.assertRaisesRegex(m.GateError, "predecessor_identity_mismatch"):
            self.accept(run="38390000001")

    def test_mismatched_private_source_head_fails(self):
        with self.assertRaisesRegex(m.GateError, "predecessor_identity_mismatch"):
            self.accept(head="b" * 40)

    def test_same_predecessor_and_successor_job_identity_fails(self):
        with self.assertRaisesRegex(m.GateError, "successor_job_identity_wrong"):
            self.accept(job="predecessor")

    def test_unreleased_owner_fails(self):
        for key,value in (
            ("predecessor_released", False),
            ("predecessor_gateway_active", True),
            ("predecessor_execution_owner_active", True),
        ):
            with self.subTest(field=key):
                bad = dict(self.predecessor, **{key:value})
                with self.assertRaisesRegex(m.GateError, "predecessor_not_safely_released"):
                    self.accept(receipt=bad)

    def test_live_order_or_paper_broker_side_effect_claim_fails(self):
        for key in ("live_orders_enabled", "broker_login_attempted",
                    "broker_credentials_used", "gateway_authentication_transferred",
                    "checkpoint_has_account_data", "checkpoint_has_jts_data"):
            with self.subTest(field=key):
                bad = dict(self.predecessor, **{key:True})
                with self.assertRaisesRegex(m.GateError, "predecessor_not_safely_released"):
                    self.accept(receipt=bad)

    def test_receipt_extra_field_fails(self):
        bad=dict(self.predecessor, unexpected="ignored?")
        with self.assertRaisesRegex(m.GateError, "predecessor_receipt_fields_not_exact"):
            self.accept(receipt=bad)

    def test_no_live_account_identity_accepted(self):
        bad=dict(self.predecessor, account_mode="live")
        with self.assertRaises(m.GateError):
            self.accept(receipt=bad)

    def test_cli_same_run_synthetic_handoff(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            checkpoint=root/"checkpoint.json"
            receipt=root/"pred.json"
            output=root/"succ.json"
            with unittest.mock.patch("sys.argv",[
                "probe", "predecessor", "--run-id", RUN, "--head", HEAD,
                "--job", "predecessor", "--checkpoint", str(checkpoint),
                "--receipt", str(receipt),
            ]), redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(),0)
            with unittest.mock.patch("sys.argv",[
                "probe", "successor", "--run-id", RUN, "--head", HEAD,
                "--job", "successor", "--checkpoint", str(checkpoint),
                "--receipt", str(receipt), "--output", str(output)
            ]), redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(),0)
            body=json.loads(output.read_text())
            self.assertFalse(body["gateway_authentication_transfer_proven"])
            self.assertFalse(body["execution_ownership_granted"])

    def test_invalid_runtime_identity_rejected(self):
        for bad in ["0", "stolen", "", "55"*30]:
            with self.subTest(id=bad):
                with self.assertRaises(m.GateError):
                    m.build_predecessor(bad,HEAD,"predecessor")
        with self.assertRaises(m.GateError):
            m.build_predecessor(RUN,"badsha","predecessor")


if __name__ == "__main__":
    unittest.main()
