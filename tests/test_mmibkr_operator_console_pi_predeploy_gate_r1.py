"""Exact public release workflow regression; no credentials, Cloudflare or private source needed."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/mmibkr-operator-console-deploy-r1.yml"


def preflight_script():
    source = WORKFLOW.read_text(encoding="utf-8")
    first = "          python3 - <<'PY_PI_PREFLIGHT'\n"
    last = "\n          PY_PI_PREFLIGHT"
    assert source.count(first) == 1 and source.count(last) == 1
    body = source.split(first, 1)[1].split(last, 1)[0]
    assert all(line.startswith("          ") for line in body.splitlines())
    return "\n".join(line[10:] for line in body.splitlines()) + "\n"


class CloudflareReleasePreflight(unittest.TestCase):
    def test_predeploy_gate_precedes_access_reconcile_and_worker_deploy(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        required = [
            "- name: Build exact private Bot Console",
            "- name: Preflight bot-source permissions BEFORE Cloudflare mutations",
            "- name: Reconcile exact-email Cloudflare Access application",
            "- name: Deploy locked operator-console Worker and private static assets",
            "- name: Bind owner-approved Pi bot OIDC publisher identity",
            "- name: Bind protected Pi bot origin source identity",
        ]
        offsets = [source.index(x) for x in required]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("MMIBKR_PI_BOT_PREDEPLOY_CLOUDFLARE_MUTATIONS=0", preflight_script())

    def test_exact_preflight_positive_negative_matrix(self):
        script = preflight_script()
        good_source = json.dumps({
            "repository": "XoticHaze/mm-IBKR",
            "ref": "main",
            "root_observation_prefix": "observations/",
            "typed_result_prefix": "typed/",
        })
        bad_source = json.dumps({
            "repository": "XoticHaze/mm-IBKR",
            "ref": "main",
            "root_observation_prefix": "../bad/",
            "typed_result_prefix": "typed/",
        })
        matrix = [
            ("legacy without publisher", False, "", "", True, "PASS"),
            ("card missing pin", True, "", "", False, "OWNER_PIN_MISSING"),
            ("card missing source", True, "a" * 40, "", False, "PRIVATE_BINDING_MISSING"),
            ("card malformed pin", True, "a" * 39, good_source, False, "OWNER_PIN_INVALID"),
            ("card accepted pin and source", True, "a" * 40, good_source, True, "PASS"),
            ("card traversal source", True, "a" * 40, bad_source, False, "PRIVATE_BINDING_INVALID"),
            ("legacy malformed optional source", False, "", "{", False, "PRIVATE_BINDING_INVALID"),
        ]
        with tempfile.TemporaryDirectory() as root:
            card_path = (Path(root) / "mmibkr-operator-console-source/extracted/mm-ibkr/"
                         "ui-react/src/components/PiBotLiveStatusCard.jsx")
            card_path.parent.mkdir(parents=True)
            for description, has_card, pin, binding, should_pass, label in matrix:
                with self.subTest(case=description):
                    if has_card:
                        card_path.write_text("fixture\n", encoding="utf-8")
                    else:
                        card_path.unlink(missing_ok=True)
                    env = {
                        "RUNNER_TEMP": root,
                        "MMIBKR_PI_BOT_PUBLISHER_APPROVED_SHA": pin,
                        "MMIBKR_PI_BOT_PRIVATE_SOURCE_BINDING": binding,
                    }
                    result = subprocess.run(
                        [sys.executable, "-c", script], env=env,
                        text=True, capture_output=True, timeout=10, check=False,
                    )
                    combined = result.stdout + result.stderr
                    self.assertEqual(result.returncode == 0, should_pass)
                    self.assertIn("MMIBKR_PI_BOT_PREDEPLOY_" + label, combined)
                    self.assertNotIn("observations/", combined)
                    self.assertNotIn("../bad/", combined)


if __name__ == "__main__":
    unittest.main()
