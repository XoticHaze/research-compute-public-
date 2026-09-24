import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
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


    def authority_config(self):
        return {
            "schema": "selected_runtime_universe_14tu.v1",
            "default_runtime_id": "mnq",
            "policy": {
                "canonical_execution_authority": "selected_runtime.execution_policy",
                "paper_submit_enabled_by_config_only": True,
                "live_submit_enabled_by_config_only": True,
            },
            "runtime_ids": [
                {
                    "runtime_id": "amat",
                    "status": "active_selected",
                    "instrument_class": "STK",
                    "strategy_id": "crw_score_multi_mode",
                    "strategy_profile": "selected_bootstrap",
                    "parameter_preset_id": "crw_amat_15m_selected",
                    "symbol": "AMAT",
                    "signal_symbol": "AMAT",
                    "timeframe": "15Min",
                    "execution_contract": {"secType": "STK", "symbol": "AMAT", "conId": 1, "exchange": "SMART"},
                    "execution_policy": {
                        "paper_submit_enabled": True,
                        "live_submit_enabled": False,
                        "dca_enabled": False,
                        "max_shares": 1,
                        "allow_inactive_session_orders": True,
                    },
                },
                {
                    "runtime_id": "aph",
                    "status": "active_selected",
                    "instrument_class": "STK",
                    "strategy_id": "crw_score_multi_mode",
                    "strategy_profile": "selected_bootstrap",
                    "parameter_preset_id": "crw_aph_15m_selected",
                    "symbol": "APH",
                    "signal_symbol": "APH",
                    "timeframe": "15Min",
                    "execution_contract": {"secType": "STK", "symbol": "APH", "conId": 2, "exchange": "SMART"},
                    "execution_policy": {
                        "paper_submit_enabled": True,
                        "live_submit_enabled": False,
                        "dca_enabled": False,
                        "max_shares": 1,
                        "allow_inactive_session_orders": True,
                    },
                },
                {
                    "runtime_id": "mnq",
                    "status": "active_selected",
                    "instrument_class": "FUT",
                    "strategy_id": "crw_score_multi_mode",
                    "strategy_profile": "proven_exec",
                    "parameter_preset_id": "crw_mnq_extreme_default",
                    "symbol": "MNQ",
                    "signal_symbol": "MNQ1!",
                    "timeframe": "12Min",
                    "execution_contract": {"secType": "FUT", "symbol": "MNQ", "conId": 3, "exchange": "CME"},
                    "execution_policy": {
                        "paper_submit_enabled": True,
                        "live_submit_enabled": False,
                        "dca_enabled": True,
                        "max_contracts": 3,
                        "max_dca_adds": 2,
                        "allow_inactive_session_orders": True,
                    },
                },
            ],
        }

    def write_source_root(self, root: Path, config=None):
        path = root / "config" / "selected_runtime_universe_14tu.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config or self.authority_config()), encoding="utf-8")
        return root

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

    def test_discover_accepts_exact_child_created_just_before_dispatch_return(self):
        nonce = "ae405f13d345771c"
        expected_head = "b" * 40
        started = datetime(2026, 9, 24, 1, 8, 9, tzinfo=timezone.utc)
        response = {
            "workflow_runs": [{
                "id": 35941580182,
                "event": "workflow_dispatch",
                "head_branch": mod.B1_REF,
                "head_sha": expected_head,
                "display_title": f"IBKR B1 {mod.MODE} {nonce}",
                "created_at": "2026-09-24T01:08:08Z",
            }]
        }

        with patch.object(mod, "_api_json", return_value=(200, response)):
            run_id = mod._discover(
                "token",
                nonce=nonce,
                expected_head=expected_head,
                started=started,
                timeout_sec=1,
            )

        self.assertEqual(run_id, "35941580182")

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


    def test_source_rebind_allows_strategy_spec_only_drift_when_runtime_authority_matches(self):
        stale = self.stale()
        for row in stale["runtimes"]:
            row["execution_policy"] = {}
        stale["runtime"]["source_sha"] = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            previous = self.write_source_root(base / "previous")
            current_config = copy.deepcopy(self.authority_config())
            for row in current_config["runtime_ids"]:
                row["strategy_spec_digest"] = "changed-only-non-authority"
                row["strategy_params"] = {"extra_evidence": True}
            current = self.write_source_root(base / "current", current_config)
            rebound = mod._rebind_snapshot_source(
                stale,
                previous_source_root=previous,
                current_source_root=current,
                expected_source_sha="b" * 40,
            )
        self.assertEqual(rebound["runtime"]["source_sha"], "b" * 40)
        self.assertEqual(rebound["runtime"]["source_ref"], "b" * 40)
        proof = rebound["maintenance_source_rebind"]
        self.assertTrue(proof["selected_runtime_authority_exact_match"])
        self.assertFalse(proof["strategy_or_execution_authority_mutated"])
        self.assertEqual(
            set(row["runtime_id"] for row in rebound["runtimes"]),
            {"amat", "aph", "mnq"},
        )

    def test_source_rebind_rejects_execution_policy_drift(self):
        stale = self.stale()
        stale["runtime"]["source_sha"] = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            previous = self.write_source_root(base / "previous")
            current_config = copy.deepcopy(self.authority_config())
            current_config["runtime_ids"][0]["execution_policy"]["paper_submit_enabled"] = False
            current = self.write_source_root(base / "current", current_config)
            with self.assertRaisesRegex(RuntimeError, "authority changed"):
                mod._rebind_snapshot_source(
                    stale,
                    previous_source_root=previous,
                    current_source_root=current,
                    expected_source_sha="b" * 40,
                )

    def test_source_rebind_rejects_execution_contract_drift(self):
        stale = self.stale()
        stale["runtime"]["source_sha"] = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            previous = self.write_source_root(base / "previous")
            current_config = copy.deepcopy(self.authority_config())
            current_config["runtime_ids"][2]["execution_contract"]["conId"] = 999
            current = self.write_source_root(base / "current", current_config)
            with self.assertRaisesRegex(RuntimeError, "authority changed"):
                mod._rebind_snapshot_source(
                    stale,
                    previous_source_root=previous,
                    current_source_root=current,
                    expected_source_sha="b" * 40,
                )

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
