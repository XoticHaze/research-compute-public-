import unittest

from scripts.ibkr_remote_selected_runtime_paper_proof_v1 import execute_paper_proof


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
        responses[("POST", "/strategy/ibkr-paper-cancel-preview")] = [(200, {"ok": True})]
        responses[("POST", "/strategy/ibkr-paper-cancel-submit")] = [(200, {"ok": True, "status": "cancel_reconciled"})]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=self._request(), send=sender, run_id="3", public_head="p")
        self.assertEqual(receipt["status"], "PAPER_PROOF_RECONCILED")
        self.assertTrue(receipt["ok"])
        self.assertTrue(receipt["cleanup"]["exact_cancel_called"])
        self.assertFalse(receipt["cleanup"]["flatten_called"])
        cancel_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-cancel-submit")
        self.assertEqual(cancel_call["payload"]["order_id"], 77)
        self.assertFalse(cancel_call["payload"]["global_cancel_allowed"])
        self.assertFalse(any("global-cancel" in c["route"] for c in sender.calls))

    def test_fill_is_flattened_only_through_canonical_flatten_route(self):
        responses = self._base()
        responses[("POST", "/strategy/ibkr-paper-order-submit")] = [
            (200, {"ok": True, "status": "filled", "place_order_called": True, "broker_order_placed": True, "guards": {"selected_runtime_id": "mnq-runtime"}, "broker_lifecycle": {"symbol": "MNQ", "order_id": 90, "status": "Filled"}})
        ]
        responses[("GET", "/strategy/ibkr-paper-open-orders")] = [self._open(), self._open(), self._open(), self._open()]
        responses[("POST", "/strategy/ibkr-paper-flatten-preview-suite")] = [self._pos(), self._pos(1), self._pos(1), self._pos()]
        responses[("POST", "/strategy/ibkr-paper-flatten-submit-suite")] = [(200, {"ok": True, "status": "flatten_reconciled"})]
        sender = FakeSender(responses)
        receipt = execute_paper_proof(runtime=self._runtime(), request=self._request(), send=sender, run_id="4", public_head="p")
        self.assertEqual(receipt["status"], "PAPER_PROOF_RECONCILED")
        self.assertTrue(receipt["cleanup"]["flatten_called"])
        flatten_call = next(c for c in sender.calls if c["route"] == "/strategy/ibkr-paper-flatten-submit-suite")
        self.assertEqual(flatten_call["payload"]["ibkr_paper_flatten_ack_13z39"], "IBKR_PAPER_FLATTEN_ACK_13Z39")
        self.assertEqual(flatten_call["payload"]["fallback_policy"], "none")
        self.assertFalse(any("global-cancel" in c["route"] for c in sender.calls))

    def test_live_authority_in_request_is_rejected(self):
        request = self._request()
        request["canonical_submit_payload"]["nested"] = {"enable_live_trading": True}
        with self.assertRaisesRegex(RuntimeError, "live_authority_rejected"):
            execute_paper_proof(runtime=self._runtime(), request=request, send=FakeSender({}), run_id="5", public_head="p")


if __name__ == "__main__":
    unittest.main()
