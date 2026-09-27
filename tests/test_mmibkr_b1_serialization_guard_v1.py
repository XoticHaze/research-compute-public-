import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_b1_serialization_guard_v1 as guard


def base_control():
    return {
        "schema": guard.SCHEMA,
        "enabled": True,
        "owner": "continue-release",
        "reason": "test",
        "blocked_push_channels": [
            "mmibkr-private-test-probe-r1",
            "mmibkr-canonical-research-session-bau-r1",
        ],
        "workflow_dispatch_allowed": True,
        "broker_mutation_authority": False,
        "runtime_activation_authority": False,
        "promotion_authority": False,
        "live_execution_allowed": False,
    }


class B1SerializationGuardTests(unittest.TestCase):
    def test_enabled_freeze_blocks_protected_push(self):
        node = base_control()
        allowed, reason = guard.evaluate(node, event="push", channel="mmibkr-private-test-probe-r1")
        self.assertFalse(allowed)
        self.assertEqual(reason, "B1_SERIALIZATION_PUSH_BLOCKED")

    def test_enabled_freeze_allows_workflow_dispatch(self):
        node = base_control()
        allowed, reason = guard.evaluate(node, event="workflow_dispatch", channel="mmibkr-private-test-probe-r1")
        self.assertTrue(allowed)
        self.assertEqual(reason, "B1_SERIALIZATION_DISPATCH_ALLOWED")

    def test_disabled_freeze_allows_push(self):
        node = base_control()
        node["enabled"] = False
        allowed, reason = guard.evaluate(node, event="push", channel="mmibkr-private-test-probe-r1")
        self.assertTrue(allowed)
        self.assertEqual(reason, "B1_SERIALIZATION_FREEZE_DISABLED")

    def test_unlisted_push_channel_is_not_blocked(self):
        node = base_control()
        allowed, reason = guard.evaluate(node, event="push", channel="unrelated-workflow")
        self.assertTrue(allowed)
        self.assertEqual(reason, "B1_SERIALIZATION_EVENT_NOT_BLOCKED")

    def test_load_control_rejects_authority_escalation(self):
        node = base_control()
        node["live_execution_allowed"] = True
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "control.json"
            path.write_text(json.dumps(node), encoding="utf-8")
            with self.assertRaises(SystemExit):
                guard.load_control(path)


if __name__ == "__main__":
    unittest.main()
