from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ibkr_warm_selected_runtime_activation_v1 as mod


class B1CanonicalDockerfileTests(unittest.TestCase):
    def test_canonical_runtime_builds_dockerfile_bot(self):
        calls = []

        def run(cmd, **kwargs):
            calls.append(list(cmd))
            class Result:
                returncode = 0
            return Result()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "mm-ibkr"
            root.mkdir(parents=True)
            (root / "Dockerfile.bot").write_text(
                "FROM python:3.11 AS bot\n",
                encoding="utf-8",
            )
            runtime = {
                "source_root": str(root),
            }
            with patch.object(
                mod.proof_v1,
                "_http_json",
                return_value=(200, {"ok": True}),
            ):
                image, data_dir = mod.start_canonical_runtime(
                    runtime=runtime,
                    run_id="12345",
                    runner_temp=Path(td),
                    gateway_host="127.0.0.1",
                    gateway_port=4002,
                    run=run,
                    sleep=lambda _: None,
                )

        self.assertEqual(image, "mmibkr-warm-proof:12345")
        build = calls[0]
        self.assertEqual(build[:3], ["docker", "build", "-f"])
        self.assertEqual(build[3], str(root / "Dockerfile.bot"))
        self.assertIn("--target", build)
        self.assertIn("bot", build)

    def test_missing_dockerfile_bot_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "mm-ibkr"
            root.mkdir(parents=True)
            with self.assertRaisesRegex(
                mod.ActivationError,
                "Dockerfile.bot missing",
            ):
                mod.start_canonical_runtime(
                    runtime={"source_root": str(root)},
                    run_id="12345",
                    runner_temp=Path(td),
                    gateway_host="127.0.0.1",
                    gateway_port=4002,
                    run=lambda *a, **k: None,
                    sleep=lambda _: None,
                )


if __name__ == "__main__":
    unittest.main()
