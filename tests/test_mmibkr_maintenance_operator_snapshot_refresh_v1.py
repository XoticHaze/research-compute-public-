import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_maintenance_operator_snapshot_refresh_v1 as mod


class MaintenanceOperatorSnapshotRefreshTests(unittest.TestCase):
    def stale(self):
        return {
            "schema": mod.OPERATOR_SCHEMA,
            "generated_at_utc": "2026-09-23T19:30:00Z",
            "mode": "paper",
            "live_enabled": False,
            "runtime": {"source_sha": "a" * 40, "cloud_owner": "healthy", "broker": "connected"},
            "account": {"positions_count": 2, "open_orders_count": 0},
            "positions": [
                {"contract": {"conId": 1, "symbol": "AMAT", "secType": "STK"}, "position": 325.0, "avg_cost": 100.0},
                {"contract": {"conId": 2, "symbol": "APH", "secType": "STK"}, "position": 46.0, "avg_cost": 50.0},
            ],
            "runtimes": [
                {"runtime_id": "amat", "position": {"position": 0.0, "ownership_attributed": True, "ownership_source": mod.OWNERSHIP_SOURCE}},
                {"runtime_id": "aph", "position": {"position": 0.0, "ownership_attributed": True, "ownership_source": mod.OWNERSHIP_SOURCE}},
                {"runtime_id": "mnq", "position": {"position": 0.0, "ownership_attributed": True, "ownership_source": mod.OWNERSHIP_SOURCE}},
            ],
            "execution": {"open_orders_count": 0, "live_trading_enabled": False},
            "privacy": {"private_operator_state": True},
            "authority": {"broker_mutation_authority": False, "live_execution_allowed": False},
        }

    def fresh(self):
        from datetime import datetime, timezone
        return {
            "schema": mod.SNAPSHOT_SCHEMA,
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "run_id": "12345",
            "public_head": "b" * 40,
            "trading_mode": "paper",
            "read_only": True,
            "account_identifiers_included": False,
            "account_summary": [{"tag": "NetLiquidation", "value": "100000", "currency": "USD"}],
            "positions": copy.deepcopy(self.stale()["positions"]),
            "position_count": 2,
            "open_order_count": 0,
            "capabilities": {
                "account_state": True, "positions": True, "open_orders": True,
                "historical_market_data": False, "quotes": False, "completed_executions": False,
                "order_submission": False, "order_cancel": False, "global_cancel": False, "live_execution": False,
            },
        }

    def test_exact_position_parity_refreshes_timestamp_and_preserves_ownership(self):
        stale = self.stale()
        out = mod.refresh_snapshot(stale, self.fresh(), expected_source_sha="a" * 40, stale_sha256="c" * 64)
        self.assertEqual(out["runtime"]["cloud_owner"], "maintenance_hold")
        self.assertEqual(out["account"]["positions_count"], 2)
        self.assertEqual(out["account"]["open_orders_count"], 0)
        self.assertEqual(out["runtimes"], stale["runtimes"])
        self.assertTrue(out["maintenance_refresh"]["exact_broker_position_identity_match"])
        self.assertFalse(out["maintenance_refresh"]["broker_mutation"])

    def test_position_scope_drift_fails_closed(self):
        fresh = self.fresh()
        fresh["positions"][0]["position"] = 324.0
        with self.assertRaisesRegex(RuntimeError, "position identity changed"):
            mod.refresh_snapshot(self.stale(), fresh, expected_source_sha="a" * 40, stale_sha256="c" * 64)

    def test_open_order_drift_fails_closed(self):
        fresh = self.fresh()
        fresh["open_order_count"] = 1
        with self.assertRaisesRegex(RuntimeError, "open orders"):
            mod.refresh_snapshot(self.stale(), fresh, expected_source_sha="a" * 40, stale_sha256="c" * 64)

    def test_nonflat_strategy_inventory_fails_closed(self):
        stale = self.stale()
        stale["runtimes"][0]["position"]["position"] = 1.0
        with self.assertRaisesRegex(RuntimeError, "non-flat"):
            mod.refresh_snapshot(stale, self.fresh(), expected_source_sha="a" * 40, stale_sha256="c" * 64)

    def test_hold_contract_requires_exact_reason_and_no_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hold.json"
            path.write_text(json.dumps({
                "schema": mod.HOLD_SCHEMA,
                "enabled": True,
                "reason": mod.HOLD_REASON,
                "broker_mutation_authority": False,
                "live_execution_allowed": False,
            }))
            mod._validate_hold(path)
            node = json.loads(path.read_text())
            node["broker_mutation_authority"] = True
            path.write_text(json.dumps(node))
            with self.assertRaisesRegex(RuntimeError, "authority boundary"):
                mod._validate_hold(path)


if __name__ == "__main__":
    unittest.main()
