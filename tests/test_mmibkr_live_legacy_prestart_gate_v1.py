"""Brokerless guard: direct legacy workflow_dispatch must not bypass live ledger admission."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/mmibkr-selected-runtime-live-owner-r1.yml"
STEP = "      - name: Require explicit canonical owner activation and exact handoff scope"
NEXT = "      - uses: actions/setup-python@"


def _owner_prestart_script() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count(STEP) == 1
    section = source.split(STEP, 1)[1].split(NEXT, 1)[0]
    shell = section.split("        run: |\n", 1)[1]
    return "\n".join(line[10:] for line in shell.splitlines() if line.startswith("          ")) + "\n"


class LegacyWritablePrestartGateTest(unittest.TestCase):
    def _invoke(self, *, admission_only: str, mode: str, predecessor: str = "") -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, ADMISSION_ONLY=admission_only,
                   HANDOFF_MODE=mode, PREDECESSOR_RUN=predecessor)
        return subprocess.run(["bash", "-c", _owner_prestart_script()],
                              env=env, text=True, capture_output=True,
                              check=False, timeout=5)

    def test_direct_legacy_writable_is_denied_before_any_broker_step(self) -> None:
        result = self._invoke(admission_only="false", mode="legacy")
        self.assertEqual(result.returncode, 64)
        self.assertIn("LIVE_LEGACY_WRITABLE_ACCOUNT_LEDGER_NOT_ADMITTED=1", result.stdout)
        self.assertNotIn("EXPLICIT_APPROVED_CANONICAL_LIVE_OWNER=1", result.stdout)

    def test_legacy_read_only_admission_remains_allowed(self) -> None:
        result = self._invoke(admission_only="true", mode="legacy")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NO_ORDER_WARM_HANDOFF_MODE=legacy", result.stdout)

    def test_successor_writable_still_requires_numeric_predecessor(self) -> None:
        result = self._invoke(admission_only="false", mode="successor")
        self.assertEqual(result.returncode, 64)
        self.assertNotIn("EXPLICIT_APPROVED_CANONICAL_LIVE_OWNER=1", result.stdout)

    def test_successor_first_step_does_not_override_downstream_reconciler(self) -> None:
        result = self._invoke(admission_only="false", mode="successor", predecessor="39499524894")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EXPLICIT_APPROVED_CANONICAL_LIVE_OWNER=1", result.stdout)
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Reconcile restored live successor with canonical broker-ledger read-only gate", source)
        self.assertIn("LIVE_RUNTIME_SUCCESSOR_CANONICAL_RECONCILER_SOURCE_NOT_ADMITTED=1", source)

    def test_other_writable_modes_remain_denied(self) -> None:
        for mode in ("producer", "supervised_5h", "gateway_pool_5h"):
            with self.subTest(mode=mode):
                result = self._invoke(admission_only="false", mode=mode)
                self.assertEqual(result.returncode, 64)
                self.assertNotIn("EXPLICIT_APPROVED_CANONICAL_LIVE_OWNER=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
