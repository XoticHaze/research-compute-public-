"""Bounded public CC fire tests: an opaque capsule cannot select MM private source."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/mmibkr-operator-console-deploy-r1.yml"
CANONICAL = "a" * 40


def resolver_script():
    txt = WORKFLOW.read_text()
    block = txt.split("      - name: Resolve accepted console source", 1)[1]
    block = block.split("      - name: Require owner-approved exact operator-console release source", 1)[0]
    body = block.split("          python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    return textwrap.dedent(body)


class OpaquePrivateWebConsoleFireTests(unittest.TestCase):
    def run_fire(self, node):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "rendezvous/fire/mmibkr-operator-console-deploy-r1"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(node))
            output = root / "github-env.txt"
            env = dict(os.environ,
                       GITHUB_ENV=str(output),
                       GITHUB_EVENT_NAME="push",
                       CANONICAL_PRIVATE_SOURCE_SHA=CANONICAL,
                       GITHUB_EVENT_PATH=str(root / "unused.json"))
            result = subprocess.run([sys.executable, "-c", resolver_script()],
                                    cwd=root, env=env, capture_output=True, text=True)
            return result.returncode, (output.read_text() if output.exists() else ""), result.stdout

    def test_no_overlay_request_keeps_incumbent(self):
        code, out, stdout = self.run_fire({"source_sha": CANONICAL})
        self.assertEqual(code, 0)
        self.assertIn("CC_PRIVATE_WEB_FIRE_REQUESTED=0", out)
        self.assertIn("CC_PRIVATE_WEB_FIRE_MODE=INCUMBENT_ONLY", stdout)

    def test_exact_opaque_capsule_requested_without_public_source(self):
        capsule = "private-web-aabbccddeeff112233445566"
        code, out, stdout = self.run_fire({
            "source_sha": CANONICAL, "private_web_capsule_id": capsule})
        self.assertEqual(code, 0)
        self.assertIn("CC_PRIVATE_WEB_FIRE_REQUESTED=1", out)
        self.assertIn("CC_PRIVATE_WEB_FIRE_CAPSULE_ID=" + capsule, out)
        self.assertIn("ENCRYPTED_OVERLAY_REQUESTED", stdout)

    def test_bad_capsule_path_cannot_override_deploy(self):
        code, out, _ = self.run_fire({
            "source_sha": CANONICAL,
            "private_web_capsule_id": "../private-source"})
        self.assertNotEqual(code, 0)
        self.assertNotIn("CC_PRIVATE_WEB_FIRE_REQUESTED=1", out)

    def test_wrong_mm_source_cannot_deploy_overlay(self):
        code, out, _ = self.run_fire({
            "source_sha": "b" * 40,
            "private_web_capsule_id": "private-web-aabbccddeeff112233445566"})
        self.assertNotEqual(code, 0)
        self.assertNotIn("CC_PRIVATE_WEB_FIRE_REQUESTED=1", out)

    def test_fleet_cryptographic_approval_never_replaced_by_fire(self):
        txt = WORKFLOW.read_text()
        self.assertIn("CC_PRIVATE_WEB_FIRE_VARIABLE_ID_COLLISION=1", txt)
        self.assertIn("python scripts/private_web_capsule_consumer_v1.py", txt)
        self.assertIn("--authority-base \"$FLEET_AUTHORITY_BASE\"", txt)
        self.assertIn("CC_PRIVATE_WEB_ENCRYPTED_OVERLAY_COMPOSED=1", txt)
        self.assertLess(txt.index("CC_PRIVATE_WEB_FIRE_VARIABLE_ID_COLLISION=1"),
                        txt.index("python scripts/private_web_capsule_consumer_v1.py"))
        self.assertLess(txt.index("python scripts/private_web_capsule_consumer_v1.py"),
                        txt.index("Deploy locked operator-console Worker and private static assets"))


if __name__ == "__main__":
    unittest.main()
