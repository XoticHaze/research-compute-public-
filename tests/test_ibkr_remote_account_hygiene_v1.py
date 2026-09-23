from __future__ import annotations

import unittest

from scripts import ibkr_remote_account_hygiene_v1 as mod
from scripts import ibkr_remote_selected_runtime_command_capsule_v2 as capsule_v2


class RemoteAccountHygieneTests(unittest.TestCase):
    def request(self, *, execute=False):
        return {
            "command_id": "sha256:" + "c" * 64,
            "source_ref": "operator-snapshot:test",
            "expected_positions": [
                {"symbol": "AMAT", "conId": 101, "secType": "STK", "position": 325.0},
                {"symbol": "APH", "conId": 102, "secType": "STK", "position": 46.0},
            ],
            "ownership_authority": {
                "schema": capsule_v2.HYGIENE_OWNERSHIP_SCHEMA,
                "operator_snapshot_sha256": "d" * 64,
                "snapshot_generated_at_utc": "2026-09-23T10:30:34Z",
                "runtime_source_sha": "a" * 40,
                "ownership_source": "selected_runtime_strategy_inventory_v1",
                "strategy_owned_positions": [],
                "account_position_count": 2,
                "operator_approved": True,
                "operator_ack": capsule_v2.HYGIENE_OPERATOR_ACK,
            },
            "execute": execute,
            "batch_size": 2,
        }

    def runtime(self):
        return {
            "mode": capsule_v2.HYGIENE_MODE,
            "paper_only": True,
            "live_trading_change": False,
            "mmibkr_head": "a" * 40,
            "source_archive_sha256": "b" * 64,
        }

    def initial_preview(self, *, extra=False):
        rows = [
            {
                "symbol": "AMAT",
                "conId": 101,
                "position": 325.0,
                "contract": {"conId": 101, "secType": "STK"},
            },
            {
                "symbol": "APH",
                "conId": 102,
                "position": 46.0,
                "contract": {"conId": 102, "secType": "STK"},
            },
        ]
        if extra:
            rows.append({
                "symbol": "NVDA",
                "conId": 103,
                "position": 1.0,
                "contract": {"conId": 103, "secType": "STK"},
            })
        return {
            "ok": True,
            "position_count": len(rows),
            "open_order_count": 0,
            "flatten_candidates": rows,
        }

    def guard_result(self, symbols, *, market_state="regular"):
        return {
            "ok": False,
            "status": "blocked",
            "blockers": sorted(mod.PREFLIGHT_ONLY_BLOCKERS),
            "place_order_called": False,
            "broker_order_placed": False,
            "preview_items": [
                {
                    "symbol": symbol,
                    "blockers": [],
                    "session_policy_blockers": [],
                    "execution_session": {
                        "market_state": market_state,
                        "submit_allowed": True,
                    },
                    "resolved_order": {
                        "order_type": "MKT" if market_state == "regular" else "LMT",
                    },
                }
                for symbol in symbols
            ],
        }

    def test_read_only_preflight_requires_exact_broker_truth_and_regular_session(self):
        calls = []

        def send(method, path, *, payload=None, timeout=None, **kwargs):
            calls.append((path, dict(payload or {})))
            if path == mod.PREVIEW_ROUTE:
                return 200, self.initial_preview()
            if path == mod.FLATTEN_ROUTE:
                return 409, self.guard_result(payload["symbols"])
            self.fail(path)

        receipt = mod.execute_account_hygiene(
            runtime=self.runtime(),
            request=self.request(execute=False),
            send=send,
            run_id="123",
            public_head="e" * 40,
        )
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["status"], "PREFLIGHT_READY")
        self.assertTrue(receipt["preflight"]["broker_truth_match"])
        self.assertTrue(receipt["preflight"]["open_orders_clean"])
        self.assertTrue(receipt["preflight"]["regular_session_ready"])
        self.assertFalse(receipt["execution"]["called"])
        self.assertTrue(all(
            call[1].get("operator_approved") is not True
            for call in calls
            if call[0] == mod.FLATTEN_ROUTE
        ))

    def test_unexpected_broker_position_fails_before_any_approved_submit(self):
        approved_calls = []

        def send(method, path, *, payload=None, timeout=None, **kwargs):
            if path == mod.PREVIEW_ROUTE:
                return 200, self.initial_preview(extra=True)
            if path == mod.FLATTEN_ROUTE:
                if payload.get("operator_approved"):
                    approved_calls.append(dict(payload))
                return 409, self.guard_result(payload["symbols"])
            self.fail(path)

        receipt = mod.execute_account_hygiene(
            runtime=self.runtime(),
            request=self.request(execute=True),
            send=send,
            run_id="123",
            public_head="e" * 40,
        )
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["status"], "PREFLIGHT_BLOCKED")
        self.assertTrue(any(
            "unexpected_broker_position:NVDA" == problem
            for problem in receipt["preflight"]["problems"]
        ))
        self.assertEqual(approved_calls, [])

    def test_extended_session_is_previewable_but_execute_fails_closed(self):
        approved_calls = []

        def send(method, path, *, payload=None, timeout=None, **kwargs):
            if path == mod.PREVIEW_ROUTE:
                return 200, self.initial_preview()
            if path == mod.FLATTEN_ROUTE:
                if payload.get("operator_approved"):
                    approved_calls.append(dict(payload))
                return 409, self.guard_result(payload["symbols"], market_state="extended")
            self.fail(path)

        receipt = mod.execute_account_hygiene(
            runtime=self.runtime(),
            request=self.request(execute=True),
            send=send,
            run_id="123",
            public_head="e" * 40,
        )
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["status"], "PREFLIGHT_BLOCKED")
        self.assertTrue(any("regular_session_required" in p for p in receipt["preflight"]["problems"]))
        self.assertEqual(approved_calls, [])

    def test_execute_calls_existing_flatten_route_then_requires_zero_position_reconcile(self):
        calls = []
        preview_count = 0

        def send(method, path, *, payload=None, timeout=None, **kwargs):
            nonlocal preview_count
            calls.append((path, dict(payload or {})))
            if path == mod.PREVIEW_ROUTE:
                preview_count += 1
                if preview_count == 1:
                    return 200, self.initial_preview()
                return 200, {
                    "ok": True,
                    "position_count": 0,
                    "open_order_count": 0,
                    "flatten_candidates": [],
                }
            if path == mod.FLATTEN_ROUTE and not payload.get("operator_approved"):
                return 409, self.guard_result(payload["symbols"])
            if path == mod.FLATTEN_ROUTE and payload.get("operator_approved"):
                return 200, {
                    "ok": True,
                    "status": "flatten_reconciled",
                    "place_order_called": True,
                    "broker_order_placed": True,
                    "blockers": [],
                    "reconcile": {
                        "remaining_symbols": [],
                        "open_order_count_after": 0,
                    },
                }
            self.fail(path)

        receipt = mod.execute_account_hygiene(
            runtime=self.runtime(),
            request=self.request(execute=True),
            send=send,
            run_id="123",
            public_head="e" * 40,
        )
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["status"], "PAPER_ACCOUNT_HYGIENE_RECONCILED")
        self.assertTrue(receipt["execution"]["called"])
        self.assertTrue(receipt["execution"]["broker_order_placed"])
        self.assertTrue(receipt["cleanup"]["flatten_called"])
        self.assertFalse(receipt["cleanup"]["global_cancel_called"])
        self.assertTrue(receipt["final_reconciliation"]["account_flat"])
        approved = [
            payload for path, payload in calls
            if path == mod.FLATTEN_ROUTE and payload.get("operator_approved")
        ]
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["ibkr_paper_flatten_ack_13z39"], mod.ROUTE_ACK)


if __name__ == "__main__":
    unittest.main()
