from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import ibkr_remote_selected_runtime_paper_execute_v1 as mod


class PersistentPaperExecuteTests(unittest.TestCase):
    def runtime(self):
        return {
            "schema": "mmibkr.remote_selected_runtime_materialization.v3",
            "mode": "paper_execute",
            "gateway_auth_source": "fleet_authority_warm_state",
            "gateway_credentials_in_capsule": False,
            "paper_only": True,
            "live_trading_change": False,
            "read_only_api": "no",
            "cleanup": {
                "cancel_open_order": False,
                "flatten_filled_position": False,
                "require_zero_baseline": False,
                "allow_global_cancel": False,
            },
            "mmibkr_head": "a" * 40,
            "source_archive_sha256": "b" * 64,
        }

    def auth(self):
        return {
            "symbol": "MNQ",
            "runtime_id": "mnq-runtime",
            "command_id": "sha256:" + "c" * 64,
            "source_ref": "selected-runtime-candidate:example",
            "strategy_spec_digest": "spec-1",
            "execution_contract": {
                "conId": 793356225,
                "symbol": "MNQ",
                "secType": "FUT",
                "exchange": "CME",
                "currency": "USD",
                "localSymbol": "MNQU6",
                "lastTradeDateOrContractMonth": "202609",
                "multiplier": "2",
            },
            "authority": {
                "runtime_id": "mnq-runtime",
                "strategy_id": "crw_score_multi_mode",
                "timeframe": "12Min",
                "execution_contract": {
                    "conId": 793356225,
                    "symbol": "MNQ",
                    "secType": "FUT",
                    "exchange": "CME",
                    "currency": "USD",
                    "localSymbol": "MNQU6",
                    "lastTradeDateOrContractMonth": "202609",
                    "multiplier": "2",
                },
            },
            "payload": {
                "runtime_id": "mnq-runtime",
                "symbol": "MNQ",
                "action": "BUY",
                "quantity": 1,
                "order_type": "LMT",
                "idempotency_key": "candidate-1",
            },
        }

    def request(self):
        return {
            "command_id": "sha256:" + "c" * 64,
            "source_ref": "selected-runtime-candidate:example",
            "canonical_submit_payload": {
                "runtime_id": "mnq-runtime",
                "symbol": "MNQ",
                "action": "BUY",
                "quantity": 1,
                "order_type": "LMT",
                "idempotency_key": "candidate-1",
            },
            "selected_runtime_authority": {
                "authority_source": "MM-IBKR selected_runtime.execution_policy",
                "paper_submit_enabled": True,
                "live_submit_enabled": False,
                "runtime_id": "mnq-runtime",
                "strategy_id": "crw_score_multi_mode",
                "strategy_spec_digest": "spec-1",
                "symbol": "MNQ",
                "timeframe": "12Min",
                "execution_contract": {
                    "conId": 793356225,
                    "symbol": "MNQ",
                    "secType": "FUT",
                    "exchange": "CME",
                    "currency": "USD",
                    "localSymbol": "MNQU6",
                    "lastTradeDateOrContractMonth": "202609",
                    "multiplier": "2",
                },
            },
        }

    def test_runtime_requires_persistent_no_cleanup_contract(self):
        out = mod.validate_fleet_authority_execute_runtime(self.runtime())
        self.assertEqual(out["mode"], "paper_execute")

        bad = self.runtime()
        bad["cleanup"]["flatten_filled_position"] = True
        with self.assertRaisesRegex(RuntimeError, "cleanup_contract_mismatch"):
            mod.validate_fleet_authority_execute_runtime(bad)

    def test_execute_uses_mode_neutral_selected_runtime_request_validator(self):
        def send(method, path, **kwargs):
            if path == "/healthz":
                return 200, {"ok": True}
            if path == "/strategy/ibkr-paper-open-orders":
                return 200, {"ok": True, "orders": []}
            if path == "/strategy/ibkr-paper-order-submit":
                return 409, {
                    "ok": False,
                    "status": "blocked",
                    "place_order_called": False,
                    "broker_order_placed": False,
                    "guards": {"selected_runtime_id": "mnq-runtime"},
                    "blockers": ["canonical_policy_block"],
                }
            raise AssertionError(path)

        with patch.object(mod.proof_v1, "_candidate_transport_lease", return_value={"requested": False, "ok": None}), \
             patch.object(mod.proof_v1, "_jit_refresh_authorized_lmt_payload", return_value=(self.request()["canonical_submit_payload"], {"requested": False, "performed": False, "ok": None})), \
             patch.object(mod.proof_v1, "_flatten_snapshot", return_value=(200, {"ok": True})), \
             patch.object(mod.proof_v1, "_open_counts", return_value=(0, 0)), \
             patch.object(mod.proof_v1, "_position_for_symbol", return_value=0.0), \
             patch.object(mod.proof_v1, "_extract_order_identity", return_value={}):
            receipt = mod.execute_paper_execute(
                runtime=self.runtime(),
                request=self.request(),
                send=send,
                run_id="123",
                public_head="d" * 40,
            )

        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["status"], "CANONICAL_SUBMIT_BLOCKED")
        self.assertEqual(
            receipt["command"]["execution_contract"],
            self.request()["selected_runtime_authority"]["execution_contract"],
        )
        with self.assertRaisesRegex(RuntimeError, "paper_submit_proof_runtime_required"):
            mod.proof_v1._validate_authorized_request(self.runtime(), self.request())

    def test_existing_position_is_observed_not_zero_baseline_blocked(self):
        calls = []

        def send(method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path == "/healthz":
                return 200, {"ok": True}
            if path == "/strategy/ibkr-paper-open-orders":
                return 200, {"ok": True, "orders": []}
            if path == "/strategy/ibkr-paper-order-submit":
                return 200, {
                    "ok": True,
                    "status": "submitted",
                    "place_order_called": True,
                    "broker_order_placed": True,
                    "guards": {"selected_runtime_id": "mnq-runtime"},
                }
            if path == "/strategy/ibkr-paper-completed-executions":
                return 200, {
                    "ok": True,
                    "read_only": True,
                    "broker_mutation_called": False,
                    "cloud_strategy_authority": False,
                    "cloud_execution_policy_authority": False,
                    "live_execution_allowed": False,
                    "global_cancel_allowed": False,
                    "matched_fill_count": 1,
                    "execution_ids": ["exec-1"],
                }
            raise AssertionError(path)

        with patch.object(mod.proof_v1, "_validate_selected_runtime_request", return_value=self.auth()),              patch.object(mod.proof_v1, "_candidate_transport_lease", return_value={"requested": False, "ok": None}),              patch.object(mod.proof_v1, "_jit_refresh_authorized_lmt_payload", return_value=(self.auth()["payload"], {"requested": True, "performed": True, "ok": True})),              patch.object(mod.proof_v1, "_flatten_snapshot", side_effect=[
                 (200, {"ok": True, "positions": [{"symbol": "MNQ", "position": 2}]}),
                 (200, {"ok": True, "positions": [{"symbol": "MNQ", "position": 3}]}),
             ]),              patch.object(mod.proof_v1, "_open_counts", return_value=(0, 0)),              patch.object(mod.proof_v1, "_position_for_symbol", side_effect=[2.0, 3.0]),              patch.object(mod.proof_v1, "_extract_order_identity", return_value={"order_id": 11, "perm_id": 22, "order_ref": "ref-1"}):
            receipt = mod.execute_paper_execute(
                runtime=self.runtime(),
                request={"command_id": "x"},
                send=send,
                run_id="123",
                public_head="d" * 40,
            )

        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["status"], "PAPER_EXECUTE_RECONCILED")
        self.assertEqual(receipt["preflight"]["target_position"], 2.0)
        self.assertFalse(receipt["preflight"]["zero_baseline_required"])
        self.assertEqual(receipt["post_submit_reconciliation"]["target_position"], 3.0)
        self.assertEqual(receipt["post_submit_reconciliation"]["position_delta"], 1.0)
        self.assertTrue(receipt["post_submit_reconciliation"]["state_retained_for_strategy"])
        self.assertFalse(receipt["cleanup"]["automatic_cleanup"])
        paths = [path for _, path, _ in calls]
        self.assertIn("/strategy/ibkr-paper-order-submit", paths)
        self.assertNotIn("/strategy/ibkr-paper-order-cancel-submit", paths)
        self.assertNotIn("/strategy/ibkr-paper-flatten-submit-suite", paths)

    def test_broker_placement_without_exact_identity_fails_execution_evidence(self):
        def send(method, path, **kwargs):
            if path == "/healthz":
                return 200, {"ok": True}
            if path == "/strategy/ibkr-paper-open-orders":
                return 200, {"ok": True, "orders": []}
            if path == "/strategy/ibkr-paper-order-submit":
                return 200, {
                    "ok": True,
                    "status": "submitted",
                    "place_order_called": True,
                    "broker_order_placed": True,
                    "guards": {"selected_runtime_id": "mnq-runtime"},
                }
            raise AssertionError(path)

        with patch.object(mod.proof_v1, "_validate_selected_runtime_request", return_value=self.auth()), \
             patch.object(mod.proof_v1, "_candidate_transport_lease", return_value={"requested": False, "ok": None}), \
             patch.object(mod.proof_v1, "_jit_refresh_authorized_lmt_payload", return_value=(self.auth()["payload"], {"requested": False, "performed": False, "ok": None})), \
             patch.object(mod.proof_v1, "_flatten_snapshot", side_effect=[(200, {"ok": True}), (200, {"ok": True})]), \
             patch.object(mod.proof_v1, "_open_counts", return_value=(0, 0)), \
             patch.object(mod.proof_v1, "_position_for_symbol", side_effect=[0.0, 1.0]), \
             patch.object(mod.proof_v1, "_extract_order_identity", return_value={}):
            receipt = mod.execute_paper_execute(
                runtime=self.runtime(),
                request=self.request(),
                send=send,
                run_id="123",
                public_head="d" * 40,
            )

        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["status"], "PAPER_EXECUTE_EXECUTION_EVIDENCE_INCOMPLETE")
        evidence = receipt["completed_execution_reconciliation"]
        self.assertTrue(evidence["requested"])
        self.assertFalse(evidence["ok"])
        self.assertIn("identity_missing", evidence["status"])

    def test_canonical_block_is_retained_as_fail_closed_execution_decision(self):
        def send(method, path, **kwargs):
            if path == "/healthz":
                return 200, {"ok": True}
            if path == "/strategy/ibkr-paper-open-orders":
                return 200, {"ok": True, "orders": []}
            if path == "/strategy/ibkr-paper-order-submit":
                return 409, {
                    "ok": False,
                    "status": "blocked",
                    "place_order_called": False,
                    "broker_order_placed": False,
                    "guards": {"selected_runtime_id": "mnq-runtime"},
                    "blockers": ["canonical_policy_block"],
                }
            raise AssertionError(path)

        with patch.object(mod.proof_v1, "_validate_selected_runtime_request", return_value=self.auth()),              patch.object(mod.proof_v1, "_candidate_transport_lease", return_value={"requested": False, "ok": None}),              patch.object(mod.proof_v1, "_jit_refresh_authorized_lmt_payload", return_value=(self.auth()["payload"], {"requested": False, "performed": False, "ok": None})),              patch.object(mod.proof_v1, "_flatten_snapshot", return_value=(200, {"ok": True})),              patch.object(mod.proof_v1, "_open_counts", return_value=(0, 0)),              patch.object(mod.proof_v1, "_position_for_symbol", return_value=0.0),              patch.object(mod.proof_v1, "_extract_order_identity", return_value={}):
            receipt = mod.execute_paper_execute(
                runtime=self.runtime(), request={}, send=send, run_id="123", public_head="d" * 40
            )
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["status"], "CANONICAL_SUBMIT_BLOCKED")
        self.assertFalse(receipt["submit"]["broker_order_placed"])

    def test_executor_source_has_no_direct_broker_or_cleanup_calls(self):
        from pathlib import Path
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("placeOrder(", source)
        self.assertNotIn("cancelOrder(", source)
        self.assertNotIn("reqGlobalCancel", source)
        self.assertNotIn("/strategy/ibkr-paper-order-cancel-submit", source)
        self.assertNotIn("/strategy/ibkr-paper-flatten-submit-suite", source)
        self.assertIn("/strategy/ibkr-paper-order-submit", source)


if __name__ == "__main__":
    unittest.main()
