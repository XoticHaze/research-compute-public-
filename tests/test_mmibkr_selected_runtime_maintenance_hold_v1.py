from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.mmibkr_selected_runtime_maintenance_hold_v1 import (
    SCHEMA,
    read_maintenance_hold,
)


ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "rendezvous/control/mmibkr-selected-runtime-cloud-maintenance-hold-r1.json"
OWNER_WORKFLOW = ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-r1.yml"
WATCHDOG_WORKFLOW = ROOT / ".github/workflows/mmibkr-selected-runtime-cloud-watchdog-r1.yml"


class SelectedRuntimeMaintenanceHoldTests(unittest.TestCase):
    def test_committed_hygiene_hold_is_fail_closed_and_non_authoritative(self):
        node = read_maintenance_hold(CONTROL)
        self.assertEqual(node["schema"], SCHEMA)
        self.assertTrue(node["enabled"])
        self.assertEqual(node["reason"], "paper_account_hygiene_679")
        self.assertFalse(node["broker_mutation_authority"])
        self.assertFalse(node["live_execution_allowed"])

    def test_missing_hold_defaults_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            node = read_maintenance_hold(Path(temp) / "missing.json")
        self.assertFalse(node["enabled"])
        self.assertFalse(node["broker_mutation_authority"])
        self.assertFalse(node["live_execution_allowed"])

    def test_invalid_or_authoritative_hold_fails_closed(self):
        cases = [
            {"schema": "wrong", "enabled": True, "reason": "x", "broker_mutation_authority": False, "live_execution_allowed": False},
            {"schema": SCHEMA, "enabled": "true", "reason": "x", "broker_mutation_authority": False, "live_execution_allowed": False},
            {"schema": SCHEMA, "enabled": True, "reason": "", "broker_mutation_authority": False, "live_execution_allowed": False},
            {"schema": SCHEMA, "enabled": True, "reason": "x", "broker_mutation_authority": True, "live_execution_allowed": False},
            {"schema": SCHEMA, "enabled": True, "reason": "x", "broker_mutation_authority": False, "live_execution_allowed": True},
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "hold.json"
            for node in cases:
                path.write_text(json.dumps(node) + "\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_maintenance_hold(path)

    def test_owner_routes_future_dispatch_to_maintenance_hold(self):
        text = OWNER_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("mmibkr-selected-runtime-cloud-maintenance-hold-r1.json", text)
        self.assertIn("scripts/mmibkr_selected_runtime_maintenance_hold_v1.py", text)
        self.assertIn('mode="maintenance_hold"', text)
        self.assertIn("MMIBKR_SELECTED_RUNTIME_CLOUD_MAINTENANCE_HOLD=1", text)

    def test_watchdog_respects_same_hold_before_dispatch(self):
        text = WATCHDOG_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("mmibkr-selected-runtime-cloud-maintenance-hold-r1.json", text)
        self.assertIn("scripts/mmibkr_selected_runtime_maintenance_hold_v1.py", text)
        self.assertIn("MMIBKR_CLOUD_WATCHDOG=maintenance_hold", text)
        self.assertIn("steps.maintenance_hold.outputs.enabled != 'true'", text)


if __name__ == "__main__":
    unittest.main()
