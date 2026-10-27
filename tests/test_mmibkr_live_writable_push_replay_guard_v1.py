"""Offline dispatch-admission regression: replayable push markers cannot launch writable IBKR."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/mmibkr-selected-runtime-live-owner-r1.yml"


def _dispatch_script() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    fire = source.split("      - name: Dispatch explicitly authorized canonical owner", 1)[1].split("\n  contract:", 1)[0]
    body = fire.split("        run: |", 1)[1]
    return "\n".join(line[10:] if line.startswith("          ") else line for line in body.splitlines())


class LiveWritablePushReplayGuardTests(unittest.TestCase):
    def _run(self, changed_patch: str) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_gh = root / "gh"
            post_log = root / "post.log"
            fake_gh.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *'/commits/'*) printf '%s\\n' \"$MOCK_PATCH\" ;;\n"
                "  *'/runs?'*) printf '0\\n' ;;\n"
                "  *'--method POST'*) printf '%s\\n' \"$*\" >> \"$MOCK_POST_LOG\" ;;\n"
                "  *) exit 99 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o700)
            env = dict(os.environ)
            env.update(
                PATH=str(root) + os.pathsep + env.get("PATH", ""),
                GITHUB_REPOSITORY="XoticHaze/research-compute-public-",
                GITHUB_SHA="a" * 40,
                GH_TOKEN="synthetic-not-real",
                MOCK_PATCH=changed_patch,
                MOCK_POST_LOG=str(post_log),
            )
            completed = subprocess.run(
                ["bash", "-c", _dispatch_script()],
                env=env, capture_output=True, text=True, timeout=15, check=False,
            )
            return completed, post_log.read_text() if post_log.exists() else ""


    def test_new_legacy_live_marker_is_rejected_before_dispatch(self):
        outcome, post = self._run("+live_owner_approved_dispatch_request_20261019_abcdef: true")
        self.assertEqual(outcome.returncode, 64, outcome.stderr)
        self.assertIn("LIVE_WRITABLE_PUSH_DISPATCH_REQUIRES_INDEPENDENT_ADMISSION=1", outcome.stdout)
        self.assertEqual(post, "")

    def test_new_successor_marker_cannot_replay_historical_predecessor(self):
        outcome, post = self._run("+live_successor_approved_dispatch_request_20261020_abcdef: 39492758670")
        self.assertEqual(outcome.returncode, 64, outcome.stderr)
        self.assertIn("LIVE_WRITABLE_PUSH_DISPATCH_REQUIRES_INDEPENDENT_ADMISSION=1", outcome.stdout)
        self.assertEqual(post, "")

    def test_readonly_pool_push_requires_independent_operator_issuer(self):
        outcome, post = self._run("+gateway_pool_5h_readonly_dispatch_request_20261022_abcdef: 15m")
        self.assertEqual(outcome.returncode, 64, outcome.stderr)
        self.assertIn("LIVE_READONLY_PUSH_DISPATCH_REQUIRES_INDEPENDENT_OPERATOR_ISSUER=1", outcome.stdout)
        self.assertEqual(post, "")

    def test_supervised_readonly_push_requires_independent_operator_issuer(self):
        outcome, post = self._run("+supervised_5h_dispatch_request_20261023_abcdef: true")
        self.assertEqual(outcome.returncode, 64, outcome.stderr)
        self.assertIn("LIVE_READONLY_PUSH_DISPATCH_REQUIRES_INDEPENDENT_OPERATOR_ISSUER=1", outcome.stdout)
        self.assertEqual(post, "")

    def test_direct_attended_operator_dispatch_remains_declared(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("gateway_pool_5h", source)
        self.assertIn("supervised_5h", source)
        self.assertNotIn("gh api --method POST", _dispatch_script())

    def test_old_marker_not_newly_added_cannot_replay(self):
        outcome, post = self._run(" live_owner_approved_dispatch_request_20261019_abcdef: true")
        self.assertEqual(outcome.returncode, 64, outcome.stderr)
        self.assertEqual(post, "")

    def test_two_new_markers_fail_closed(self):
        outcome, post = self._run(
            "+gateway_pool_5h_readonly_dispatch_request_20261022_abcdef: 15m\n"
            "+live_owner_approved_dispatch_request_20261019_abcdef: true"
        )
        self.assertEqual(outcome.returncode, 64, outcome.stderr)
        self.assertEqual(post, "")


if __name__ == "__main__":
    unittest.main()
