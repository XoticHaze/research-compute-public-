import datetime as dt
import unittest
from unittest.mock import patch

from scripts.ibkr_remote_selected_runtime_paper_proof_v1 import (
    _validate_selected_runtime_request,
    execute_paper_proof,
)


class FakeSender:
    def __init__(self, responses):
        self.responses = {key: list(value) for key, value in responses.items()}
        self.calls = []

    def __call__(self, method, route, *, payload=None, params=None, timeout=60.0):
        self.calls.append({"method": method, "route": route, "payload": payload, "params": params})
        key = (method, route)
        queue = self.responses.get(key)
        if not queue:
            raise AssertionError(f"unexpected call {key}")
        return queue.pop(0)


class RemoteSelectedRuntimePaperProofTests(unittest.TestCase):
    def _runtime(self):
        return {
            "mode": "paper_submit_proof",
            "read_only_api": "no",
            "paper_only": True,
            "live_trading_change": False,
            "mmibkr_head": "a" * 40,
            "source_archive_sha256": "b" * 64,
            "cleanup": {
                "cancel_open_order": True,
                "flatten_filled_position": True,
                "require_zero_baseline": True,
                "allow_global_cancel": False,
            },
        }

    def _request(self):
        return {
            "command_id": "sha256:" + "c" * 64,
            "source_ref": "selected-runtime-event:abc",
            "canonical_submit_payload": {
                "runtime_id": "mnq-runtime",
                "symbol": "MNQ",
                "action": "BUY",
                "quantity": 1,
                "order_type": "LMT",
                "limit_price": 22000,
                "session_mode": "FUTURES",
                "idempotency_key": "proof-abc",
            },
            "selected_runtime_authority": {
                "authority_source": "MM-IBKR selected_runtime.execution_policy",
                "runtime_id": "mnq-runtime",
                "strategy_id": "crw_score_multi_mode",
                "strategy_spec_digest": "spec-1",
                "symbol": "MNQ",
                "timeframe": "12Min",
                "paper_submit_enabled": True,
                "live_submit_enabled": False,
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
            "encrypted_return": {"schema": "unused-in-driver"},
        }

    @staticmethod
    def _open(rows=None):
        rows = rows or []
        return 200, {"ok": True, "orders": rows, "open_order_count": len(rows), "unresolved_open_order_count": len(rows)}

    @staticmethod
    def _pos(position=0.0):
        rows = [] if not position else [{"symbol": "MNQ", "position": position}]
        return 200, {"ok": True, "flatten_candidates": rows, "single_previews": []}

    def _base(self):
        return {
            ("GET", "/healthz"): [(200, {"ok": True})],
            ("GET", "/strategy/ibkr-paper-open-orders"): [self._open()],
            ("POST", "/strategy/ibkr-paper-flatten-preview-suite"): [self._pos()],
        }

    def test_selected_runtime_exact_option_contract_is_accepted_without_public_invention(self):
        request = self._request()
        request["canonical_submit_payload"].update({
            "symbol": "SPY",
            "runtime_id": "spy-opt-runtime",
        })
        request["selected_runtime_authority"].update({
            "runtime_id": "spy-opt-runtime",
            "symbol": "SPY",
            "execution_contract": {
                "conId": 999001,
                "symbol": "SPY",
                "secType": "OPT",
                "exchange": "SMART",
                "currency": "USD",
                "lastTradeDateOrContractMonth": "20261016",
                "strike": 600.0,
                "right": "C",
                "multiplier": "100",
                "tradingClass": "SPY",
            },
        })
        out = _validate_selected_runtime_request(request)
        self.assertEqual(out["execution_contract"], request["selected_runtime_authority"]["execution_contract"])

    def test_ambiguous_nonstock_execution_contract_is_rejected(self):
        request = self._request()
        request["selected_runtime_authority"]["execution_contract"] = {
            "symbol": "MNQ",
            "secType": "FUT",
            "exchange": "CME",
            "currency": "USD",
        }
        with self.assertRaisesRegex(RuntimeError, "exact_futures_execution_contract_required"):
            _validate_selected_runtime_request(request)

    def test_preflight_position_snapshot_receives_exact_mm_contract(self):
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (409, {
                "ok": False,
                "status": "blocked",
                "place_order_called": False,
                "broker_order_placed": False,
                "guards": {"selected_runtime_id": "mnq-runtime"},
                "blockers": ["route_currently_active_required_or_explicit_override_13z53"],
            })
        ]
        sender = FakeSender(responses)
        request = self._request()
        execute_paper_proof(
            runtime=self._runtime(),
            request=request,
            send=sender,
            run_id="contract-preflight",
            public_head="p",
        )
        flatten_calls = [
            call for call in sender.calls
            if call["route"] == "/strategy/ibkr-paper-flatten-preview-suite"
        ]
        self.assertGreaterEqual(len(flatten_calls), 1)
        expected = request["selected_runtime_authority"]["execution_contract"]
        for call in flatten_calls:
            self.assertEqual(call["payload"]["contract"], expected)
            self.assertEqual(call["payload"]["execution_contract"], expected)

    def test_existing_open_order_blocks_before_submit(self):
        responses = self._base()
        responses[("GET", "/strategy/ibkr-paper-open-orders")] = [self._open([{"symbol": "MNQ", "unresolved": True, "orderId": 1}])]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=self._request(), send=sender, run_id="1", public_head="p")
        self.assertEqual(receipt["status"], "BLOCKED_PRE_SUBMIT")
        self.assertFalse(receipt["submit"]["called"])
        self.assertNotIn(("POST", "/strategy/ibkr-paper-order-submit"), [(c["method"], c["route"]) for c in sender.calls])

    def test_canonical_submit_block_is_safe_and_no_cleanup_is_invented(self):
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (409, {"ok": False, "status": "blocked", "place_order_called": False, "broker_order_placed": False, "guards": {"selected_runtime_id": "mnq-runtime"}, "blockers": ["route_currently_active_required_or_explicit_override_13z53"]})
        ]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=self._request(), send=sender, run_id="2", public_head="p")
        self.assertEqual(receipt["status"], "CANONICAL_SUBMIT_BLOCKED")
        self.assertTrue(receipt["ok"])
        self.assertFalse(receipt["cleanup"]["exact_cancel_called"])
        self.assertFalse(receipt["cleanup"]["flatten_called"])

    def test_open_order_is_exact_cancelled_then_zero_reconciled(self):
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (200, {"ok": True, "status": "submitted", "place_order_called": True, "broker_order_placed": True, "guards": {"selected_runtime_id": "mnq-runtime"}, "broker_lifecycle": {"symbol": "MNQ", "order_id": 77, "perm_id": 88, "order_ref": "proof-abc", "status": "Submitted"}})
        ]
        responses[("GET", "/strategy/ibkr-paper-open-orders")] = [
            self._open(),
            self._open([{"symbol": "MNQ", "unresolved": True, "orderId": 77, "permId": 88, "orderRef": "proof-abc"}]),
            self._open(),
            self._open(),
        ]
        responses[("POST", "/strategy/ibkr-paper-flatten-preview-suite")] = [self._pos(), self._pos(), self._pos(), self._pos()]
        responses[("POST", "/strategy/ibkr-paper-order-cancel-preview")] = [(200, {"ok": True})]
        responses[("POST", "/strategy/ibkr-paper-order-cancel-submit")] = [(200, {"ok": True, "status": "cancel_reconciled"})]
        responses[("POST", "/strategy/ibkr-paper-completed-executions")] = [(
            200,
            {
                "ok": True,
                "status": "completed_execution_reconciliation_ready",
                "read_only": True,
                "matched_fill_count": 0,
                "fills": [],
                "req_executions_called": True,
                "broker_mutation_called": False,
                "cloud_strategy_authority": False,
                "cloud_execution_policy_authority": False,
                "live_execution_allowed": False,
                "global_cancel_allowed": False,
            },
        )]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=self._request(), send=sender, run_id="3", public_head="p")
        self.assertEqual(receipt["status"], "PAPER_PROOF_RECONCILED")
        self.assertTrue(receipt["ok"])
        self.assertTrue(receipt["cleanup"]["exact_cancel_called"])
        self.assertFalse(receipt["cleanup"]["flatten_called"])
        cancel_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-order-cancel-submit")
        self.assertEqual(cancel_call["payload"]["order_id"], 77)
        self.assertEqual(cancel_call["payload"]["ibkr_paper_order_cancel_ack_13z60"], "IBKR_PAPER_ORDER_CANCEL_ACK_13Z60")
        self.assertNotIn("ibkr_paper_cancel_ack_13z37", cancel_call["payload"])
        self.assertFalse(cancel_call["payload"]["global_cancel_allowed"])
        evidence_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-completed-executions")
        self.assertEqual(evidence_call["payload"]["identities"][0]["role"], "entry")
        self.assertEqual(evidence_call["payload"]["identities"][0]["order_id"], 77)
        self.assertTrue(receipt["completed_execution_reconciliation"]["ok"])
        self.assertFalse(receipt["completed_execution_reconciliation"]["broker_mutation_called"])
        self.assertFalse(any("global-cancel" in c["route"] for c in sender.calls))

    def test_fill_is_flattened_only_through_canonical_flatten_route(self):
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (200, {"ok": True, "status": "filled", "place_order_called": True, "broker_order_placed": True, "guards": {"selected_runtime_id": "mnq-runtime"}, "broker_lifecycle": {"symbol": "MNQ", "order_id": 90, "status": "Filled"}})
        ]
        responses[("GET", "/strategy/ibkr-paper-open-orders")] = [self._open(), self._open(), self._open(), self._open()]
        responses[("POST", "/strategy/ibkr-paper-flatten-preview-suite")] = [self._pos(), self._pos(1), self._pos(1), self._pos()]
        responses[("POST", "/strategy/ibkr-paper-flatten-submit-suite")] = [(
            200,
            {
                "ok": True,
                "status": "flatten_reconciled",
                "flatten_attempts": [
                    {
                        "symbol": "MNQ",
                        "broker_status": {
                            "symbol": "MNQ",
                            "order_id": 91,
                            "perm_id": 901,
                            "order_ref": "MMIBKR_FLATTEN_13Z39",
                            "status": "Filled",
                        },
                    }
                ],
            },
        )]
        responses[("POST", "/strategy/ibkr-paper-completed-executions")] = [(
            200,
            {
                "ok": True,
                "status": "completed_execution_reconciliation_ready",
                "read_only": True,
                "matched_fill_count": 2,
                "execution_ids": ["entry-90", "exit-91"],
                "fills": [
                    {"exec_id": "entry-90", "order_id": 90, "realized_pnl": 0.0},
                    {"exec_id": "exit-91", "order_id": 91, "realized_pnl": 6.0},
                ],
                "total_realized_pnl": 6.0,
                "req_executions_called": True,
                "broker_mutation_called": False,
                "cloud_strategy_authority": False,
                "cloud_execution_policy_authority": False,
                "live_execution_allowed": False,
                "global_cancel_allowed": False,
            },
        )]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=self._request(), send=sender, run_id="4", public_head="p")
        self.assertEqual(receipt["status"], "PAPER_PROOF_RECONCILED")
        self.assertTrue(receipt["cleanup"]["flatten_called"])
        flatten_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-flatten-submit-suite")
        self.assertEqual(flatten_call["payload"]["ibkr_paper_flatten_ack_13z39"], "IBKR_PAPER_FLATTEN_ACK_13Z39")
        self.assertEqual(flatten_call["payload"]["fallback_policy"], "none")
        expected_contract = self._request()["selected_runtime_authority"]["execution_contract"]
        self.assertEqual(flatten_call["payload"]["contract"], expected_contract)
        self.assertEqual(flatten_call["payload"]["execution_contract"], expected_contract)
        evidence_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-completed-executions")
        roles = [row["role"] for row in evidence_call["payload"]["identities"]]
        self.assertEqual(roles, ["entry", "cleanup_exit"])
        self.assertEqual(receipt["completed_execution_reconciliation"]["total_realized_pnl"], 6.0)
        self.assertFalse(receipt["completed_execution_reconciliation"]["broker_mutation_called"])
        self.assertFalse(any("global-cancel" in c["route"] for c in sender.calls))

    def test_completed_execution_evidence_failure_prevents_reconciled_success(self):
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (200, {
                "ok": True,
                "status": "submitted",
                "place_order_called": True,
                "broker_order_placed": True,
                "guards": {"selected_runtime_id": "mnq-runtime"},
                "broker_lifecycle": {
                    "symbol": "MNQ",
                    "order_id": 77,
                    "perm_id": 88,
                    "order_ref": "proof-abc",
                    "status": "Submitted",
                },
            })
        ]
        responses[("GET", "/strategy/ibkr-paper-open-orders")] = [
            self._open(),
            self._open([{"symbol": "MNQ", "unresolved": True, "orderId": 77, "permId": 88, "orderRef": "proof-abc"}]),
            self._open(),
            self._open(),
        ]
        responses[("POST", "/strategy/ibkr-paper-flatten-preview-suite")] = [
            self._pos(), self._pos(), self._pos(), self._pos()
        ]
        responses[("POST", "/strategy/ibkr-paper-order-cancel-preview")] = [(200, {"ok": True})]
        responses[("POST", "/strategy/ibkr-paper-order-cancel-submit")] = [(200, {"ok": True, "status": "cancel_reconciled"})]
        responses[("POST", "/strategy/ibkr-paper-completed-executions")] = [
            (502, {"ok": False, "status": "req_executions_failed", "read_only": True, "broker_mutation_called": False})
        ]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(
            runtime=self._runtime(),
            request=self._request(),
            send=sender,
            run_id="8",
            public_head="p",
        )
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["status"], "PAPER_PROOF_EXECUTION_EVIDENCE_INCOMPLETE")
        self.assertTrue(receipt["final_reconciliation"]["zero_baseline_restored"])
        self.assertFalse(receipt["completed_execution_reconciliation"]["ok"])
        self.assertFalse(receipt["completed_execution_reconciliation"]["broker_mutation_called"])

    def test_jit_quote_refresh_uses_canonical_quote_and_changes_only_price_fields(self):
        request = self._request()
        payload = request["canonical_submit_payload"]
        payload["remote_proof_refresh_limit_price"] = True
        payload["remote_proof_candidate_quote_received_at_utc"] = "2026-09-17T18:00:00Z"
        payload["remote_proof_candidate_quote_max_age_sec"] = 15
        payload["operator_approved"] = True
        payload["ibkr_paper_order_submit_ack_13z53"] = "IBKR_PAPER_ORDER_SUBMIT_ACK_13Z53"
        original_action = payload["action"]
        original_quantity = payload["quantity"]

        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-quote-snapshot")] = [
            (200, {
                "ok": True,
                "status": "ready",
                "executable_quote_available": True,
                "limit_price_policy": {"final_limit_price": 22010.25},
                "blockers": [],
            })
        ]
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (409, {
                "ok": False,
                "status": "blocked",
                "place_order_called": False,
                "broker_order_placed": False,
                "guards": {"selected_runtime_id": "mnq-runtime"},
                "blockers": ["route_currently_active_required_or_explicit_override_13z53"],
            })
        ]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=request, send=sender, run_id="6", public_head="p")
        self.assertEqual(receipt["status"], "CANONICAL_SUBMIT_BLOCKED")
        self.assertTrue(receipt["quote_refresh"]["ok"])
        self.assertEqual(receipt["quote_refresh"]["final_limit_price"], 22010.25)
        submit_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-order-submit")
        self.assertEqual(submit_call["payload"]["action"], original_action)
        self.assertEqual(submit_call["payload"]["quantity"], original_quantity)
        self.assertEqual(submit_call["payload"]["limit_price"], 22010.25)
        self.assertEqual(submit_call["payload"]["lmtPrice"], 22010.25)
        self.assertEqual(submit_call["payload"]["limit_price_source"], "remote_proof_jit_canonical_quote_snapshot")
        self.assertNotIn("remote_proof_refresh_limit_price", submit_call["payload"])
        self.assertTrue(submit_call["payload"]["operator_approved"])
        self.assertEqual(submit_call["payload"]["ibkr_paper_order_submit_ack_13z53"], "IBKR_PAPER_ORDER_SUBMIT_ACK_13Z53")

    def test_candidate_lease_is_rechecked_after_read_only_preflight(self):
        request = self._request()
        now = dt.datetime.now(dt.timezone.utc)
        request["canonical_submit_payload"]["remote_proof_candidate_materialized_at_utc"] = now.isoformat().replace("+00:00", "Z")
        request["canonical_submit_payload"]["remote_proof_candidate_max_age_sec"] = 180
        responses = self._base()
        sender = FakeSender(responses)
        initial = {
            "requested": True,
            "ok": True,
            "materialized_at_utc": request["canonical_submit_payload"]["remote_proof_candidate_materialized_at_utc"],
            "age_sec": 10.0,
            "max_age_sec": 180.0,
            "issues": [],
            "authority_change": False,
        }
        expired = {
            **initial,
            "ok": False,
            "age_sec": 181.0,
            "issues": ["remote_candidate_transport_lease_expired"],
        }
        with patch(
            "scripts.ibkr_remote_selected_runtime_paper_proof_v1._candidate_transport_lease",
            side_effect=[initial, expired],
        ) as lease:
            receipt = execute_paper_proof(
                runtime=self._runtime(),
                request=request,
                send=sender,
                run_id="11",
                public_head="p",
            )
        self.assertEqual(lease.call_count, 2)
        self.assertEqual(receipt["status"], "CANDIDATE_LEASE_BLOCKED")
        self.assertEqual(receipt["candidate_lease"]["age_sec"], 181.0)
        self.assertFalse(any(c["route"] == "/strategy/ibkr-paper-order-submit" for c in sender.calls))

    def test_expired_remote_candidate_lease_blocks_before_submit(self):
        request = self._request()
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=181)
        request["canonical_submit_payload"]["remote_proof_candidate_materialized_at_utc"] = old.isoformat().replace("+00:00", "Z")
        request["canonical_submit_payload"]["remote_proof_candidate_max_age_sec"] = 180
        responses = self._base()
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=request, send=sender, run_id="8", public_head="p")
        self.assertEqual(receipt["status"], "CANDIDATE_LEASE_BLOCKED")
        self.assertFalse(receipt["ok"])
        self.assertTrue(receipt["candidate_lease"]["requested"])
        self.assertFalse(receipt["candidate_lease"]["ok"])
        self.assertIn("remote_candidate_transport_lease_expired", receipt["candidate_lease"]["issues"])
        self.assertFalse(receipt["submit"]["called"])
        self.assertFalse(any(c["route"] == "/strategy/ibkr-paper-order-submit" for c in sender.calls))

    def test_valid_remote_candidate_lease_can_reach_canonical_submit_gate(self):
        request = self._request()
        now = dt.datetime.now(dt.timezone.utc)
        request["canonical_submit_payload"]["remote_proof_candidate_materialized_at_utc"] = now.isoformat().replace("+00:00", "Z")
        request["canonical_submit_payload"]["remote_proof_candidate_max_age_sec"] = 180
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (409, {
                "ok": False,
                "status": "blocked",
                "place_order_called": False,
                "broker_order_placed": False,
                "guards": {"selected_runtime_id": "mnq-runtime"},
                "blockers": ["route_currently_active_required_or_explicit_override_13z53"],
            })
        ]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=request, send=sender, run_id="9", public_head="p")
        self.assertEqual(receipt["status"], "CANONICAL_SUBMIT_BLOCKED")
        self.assertTrue(receipt["candidate_lease"]["ok"])
        self.assertTrue(receipt["submit"]["called"])

    def test_jit_quote_refresh_strips_remote_transport_metadata_before_submit(self):
        request = self._request()
        payload = request["canonical_submit_payload"]
        now = dt.datetime.now(dt.timezone.utc)
        payload["remote_proof_candidate_materialized_at_utc"] = now.isoformat().replace("+00:00", "Z")
        payload["remote_proof_candidate_max_age_sec"] = 180
        payload["remote_proof_refresh_limit_price"] = True
        payload["remote_proof_candidate_quote_received_at_utc"] = now.isoformat().replace("+00:00", "Z")
        payload["remote_proof_candidate_quote_max_age_sec"] = 15
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-quote-snapshot")] = [
            (200, {
                "ok": True,
                "status": "ready",
                "executable_quote_available": True,
                "limit_price_policy": {"final_limit_price": 22011.0},
                "blockers": [],
            })
        ]
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (409, {
                "ok": False,
                "status": "blocked",
                "place_order_called": False,
                "broker_order_placed": False,
                "guards": {"selected_runtime_id": "mnq-runtime"},
                "blockers": ["route_currently_active_required_or_explicit_override_13z53"],
            })
        ]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=request, send=sender, run_id="10", public_head="p")
        self.assertEqual(receipt["status"], "CANONICAL_SUBMIT_BLOCKED")
        submit_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-order-submit")
        self.assertEqual(submit_call["payload"]["limit_price"], 22011.0)
        self.assertNotIn("remote_proof_candidate_materialized_at_utc", submit_call["payload"])
        self.assertNotIn("remote_proof_candidate_max_age_sec", submit_call["payload"])
        self.assertNotIn("remote_proof_refresh_limit_price", submit_call["payload"])

    def test_jit_quote_refresh_failure_blocks_before_submit(self):
        request = self._request()
        request["canonical_submit_payload"]["remote_proof_refresh_limit_price"] = True
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-quote-snapshot")] = [
            (409, {"ok": False, "status": "blocked", "blockers": ["executable_quote_source_missing_13z65"]})
        ]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=request, send=sender, run_id="7", public_head="p")
        self.assertEqual(receipt["status"], "JIT_QUOTE_REFRESH_BLOCKED")
        self.assertFalse(receipt["ok"])
        self.assertFalse(receipt["submit"]["called"])
        self.assertFalse(receipt["quote_refresh"]["ok"])
        self.assertFalse(any(c["route"] == "/strategy/ibkr-paper-order-submit" for c in sender.calls))

    def test_live_authority_in_request_is_rejected(self):
        request = self._request()
        request["canonical_submit_payload"]["nested"] = {"enable_live_trading": True}
        with self.assertRaisesRegex(RuntimeError, "live_authority_rejected"):
            execute_paper_proof(runtime=self._runtime(), request=request, send=FakeSender({}), run_id="5", public_head="p")


if __name__ == "__main__":
    unittest.main()
