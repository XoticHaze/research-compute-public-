from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-operator-console-deploy-r1.yml"


class OperatorConsoleAccessReconcileTests(unittest.TestCase):
    def test_deploy_reconciles_exact_email_access_policy(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("MMIBKR_ACCESS_ALLOWED_EMAILS", text)
        self.assertIn("MM-IBKR approved operators", text)
        self.assertIn("'decision': 'allow'", text)
        self.assertIn("{'email': {'email': email}}", text)
        self.assertIn("/access/policies", text)
        self.assertIn("/access/apps", text)
        self.assertIn("'type': 'self_hosted'", text)
        self.assertIn(
            "'mmibkr-operator-console.slenderiq.workers.dev'",
            text,
        )

    def test_zero_trust_org_is_read_not_created_by_deployer(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("/access/organizations", text)
        self.assertIn("auth_domain", text)
        self.assertNotIn(
            "api('POST', f'/accounts/{account}/access/organizations'",
            text,
        )

    def test_publisher_path_is_specific_bypass_with_worker_oidc_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("MM-IBKR Operator Snapshot Publisher", text)
        self.assertIn("MM-IBKR operator snapshot OIDC ingress", text)
        self.assertIn("publisher_domain = hostname + '/v1/operator-snapshot'", text)
        self.assertIn("'decision': 'bypass'", text)
        self.assertIn("'include': [{'everyone': {}}]", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_PUBLISHER_INGRESS=OIDC_WORKER_GATED", text)
        self.assertIn("publisher_status != 401", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_PUBLISHER_UNAUTHENTICATED_DENIED=1", text)

    def test_reader_path_is_specific_bypass_with_worker_oidc_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("MM-IBKR Operator Snapshot Reader", text)
        self.assertIn("MM-IBKR operator snapshot read OIDC ingress", text)
        self.assertIn("reader_domain = hostname + '/v1/operator-snapshot-read'", text)
        self.assertIn("reader_policy_body = {", text)
        self.assertIn("'decision': 'bypass'", text)
        self.assertIn("reader_app_body = {", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_READER_INGRESS=OIDC_WORKER_GATED", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_READER_PATH=/v1/operator-snapshot-read", text)
        self.assertIn("reader_status != 401", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_READER_UNAUTHENTICATED_DENIED=1", text)

    def test_promotion_machine_paths_are_specific_bypasses_with_worker_oidc_gates(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("MM-IBKR Promotion Candidate Publisher", text)
        self.assertIn("promotion_publisher_domain = hostname + '/v1/promotion-candidates'", text)
        self.assertIn("promotion_publisher_app_body = {", text)
        self.assertIn("'id': publisher_policy_id", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_PROMOTION_PUBLISHER_INGRESS=OIDC_WORKER_GATED", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_PROMOTION_PUBLISHER_PATH=/v1/promotion-candidates", text)
        self.assertIn("promotion_publisher_status != 401", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_PROMOTION_PUBLISHER_UNAUTHENTICATED_DENIED=1", text)

        self.assertIn("MM-IBKR Promotion Review Reader", text)
        self.assertIn("promotion_reader_domain = hostname + '/v1/promotion-review-read'", text)
        self.assertIn("promotion_reader_app_body = {", text)
        self.assertIn("'id': reader_policy_id", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_PROMOTION_READER_INGRESS=OIDC_WORKER_GATED", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_PROMOTION_READER_PATH=/v1/promotion-review-read", text)
        self.assertIn("promotion_reader_status != 401", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_PROMOTION_READER_UNAUTHENTICATED_DENIED=1", text)

    def test_worker_verifier_secrets_are_bound_after_access_app_exists(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ACCESS_TEAM_DOMAIN", text)
        self.assertIn("ACCESS_AUD", text)
        self.assertIn("ACCESS_ALLOWED_EMAILS", text)
        self.assertIn("wrangler@4.131.2 secret put ACCESS_TEAM_DOMAIN", text)
        self.assertIn("wrangler@4.131.2 secret put ACCESS_AUD", text)
        self.assertIn("wrangler@4.131.2 secret put ACCESS_ALLOWED_EMAILS", text)

    def test_access_preflight_precedes_worker_deploy(self):
        import os
        import subprocess
        import textwrap

        text = WORKFLOW.read_text(encoding="utf-8")
        start = "      - name: Preflight Access release credentials before Worker deployment"
        deploy = "      - name: Deploy locked operator-console Worker and private static assets"
        self.assertIn(start, text)
        self.assertLess(text.index(start), text.index(deploy))
        block = text.split(start, 1)[1].split("      - name: Reconcile exact-email Cloudflare Access application", 1)[0]
        self.assertIn("/access/organizations", block)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_ACCESS_PREDEPLOY=READY", block)
        self.assertNotIn("exc.read()", block)
        self.assertIn("except Exception:", block)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_ACCESS_PREDEPLOY_UNAVAILABLE=1", block)
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        for missing in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "ACCESS_ALLOWED_EMAILS"):
            with self.subTest(missing=missing):
                env = dict(os.environ)
                env.update({"CLOUDFLARE_API_TOKEN": "synthetic",
                            "CLOUDFLARE_ACCOUNT_ID": "synthetic",
                            "ACCESS_ALLOWED_EMAILS": "operator@example.test"})
                env[missing] = ""
                result = subprocess.run(["bash", "-c", script], env=env,
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 43, result.stderr)
                self.assertIn("MMIBKR_OPERATOR_CONSOLE_ACCESS_PREDEPLOY_REQUIRED=1", result.stdout)
                self.assertNotIn("operator@example.test", result.stdout + result.stderr)

    def test_no_email_allowlist_keeps_worker_locked(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "MMIBKR_OPERATOR_CONSOLE_ACCESS_BINDING=LOCKED_EMAIL_ALLOWLIST_MISSING",
            text,
        )
        self.assertIn(
            "MMIBKR_OPERATOR_CONSOLE_ACCESS_BINDING=LOCKED_UNCONFIGURED",
            text,
        )

    def test_access_is_reconciled_before_worker_deploy_and_control_plane_proof(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        preflight = "Preflight Access release credentials before Worker deployment"
        access_step = "Reconcile exact-email Cloudflare Access application"
        deploy_step = "Deploy locked operator-console Worker and private static assets"
        control_plane_step = "Prove deployed Worker through Cloudflare control plane"
        bind_step = "Bind Worker defense-in-depth Access verifier"
        self.assertLess(text.index(preflight), text.index(access_step))
        self.assertLess(text.index(access_step), text.index(deploy_step))
        self.assertLess(text.index(deploy_step), text.index(control_plane_step))
        self.assertLess(text.index(control_plane_step), text.index(bind_step))
        self.assertIn("/workers/scripts/", text)
        self.assertIn("/settings", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_CONTROL_PLANE=READY", text)
        self.assertIn("for path in ('/', '/bot-console', '/operator/promotion-review', '/api/operator-snapshot', '/healthz'):", text)
        self.assertNotIn("operator-console pre-Access health did not converge", text)

    def test_missing_access_binding_is_terminal_not_a_successful_deploy(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        access = text.split("      - name: Reconcile exact-email Cloudflare Access application", 1)[1].split("      - name: Deploy locked operator-console Worker", 1)[0]
        bind = text.split("      - name: Bind Worker defense-in-depth Access verifier", 1)[1].split("      - name: Prove unauthenticated surface fails closed", 1)[0]
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_ACCESS_BINDING=LOCKED_EMAIL_ALLOWLIST_MISSING'\n            exit 43", access)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_ACCESS_BINDING=LOCKED_UNCONFIGURED'\n            exit 44", bind)

    def test_public_actions_never_echo_cloudflare_provider_error_bodies(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        # Cloudflare error bodies can contain operator email allowlists and
        # account or policy identifiers. Public CI logs must not echo them.
        self.assertNotIn("detail = exc.read", text)
        self.assertNotIn("json.dumps(node.get('errors')", text)
        self.assertIn("Cloudflare Worker settings proof failed HTTP {exc.code}", text)
        self.assertIn("Cloudflare Access request failed HTTP {exc.code}", text)
        self.assertIn("Cloudflare Worker settings proof rejected", text)
        self.assertIn("Cloudflare Access request rejected", text)

    def test_unauthenticated_acceptance_rejects_public_200(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("class NoRedirect(HTTPRedirectHandler)", text)
        self.assertIn("if status == 200:", text)
        self.assertIn("unauthenticated operator-console path became public", text)
        self.assertIn("cloudflareaccess.com", text)


    def test_anonymous_browser_requires_real_https_access_redirect(self):
        import ast
        import textwrap
        from urllib.parse import urlsplit

        text = WORKFLOW.read_text(encoding="utf-8")
        block = text.split(
            "      - name: Prove unauthenticated surface fails closed", 1
        )[1].split("      - name: Publish scoped R2 MM deployment receipt", 1)[0]
        script = textwrap.dedent(
            block.split("          python - <<'PY'\n", 1)[1]
            .split("\n          PY", 1)[0]
        )
        tree = ast.parse(script)
        predicate = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "is_access_redirect"
        )
        namespace = {"urlsplit": urlsplit}
        exec(
            compile(ast.Module(body=[predicate], type_ignores=[]), "<access-redirect>", "exec"),
            namespace,
        )
        accepts = namespace["is_access_redirect"]
        self.assertTrue(accepts("https://team.cloudflareaccess.com/cdn-cgi/access/login"))
        for invalid in (
            "https://evil.example/redirect?next=cloudflareaccess.com",
            "https://cloudflareaccess.com.evil.example/login",
            "https://team.cloudflareaccess.com.evil.example/login",
            "http://team.cloudflareaccess.com/cdn-cgi/access/login",
            "https://evil.example/redirect?token=private",
        ):
            with self.subTest(invalid=invalid):
                self.assertFalse(accepts(invalid))
        self.assertIn("if path in browser_paths and status not in {302, 303, 307}:", script)
        self.assertNotIn("and 'cloudflareaccess.com' not in location", script)
        self.assertNotIn(":{location}", script)

    def test_deploy_receipt_distinguishes_locked_unconfigured_from_access_configured(self):
        import json
        import os
        import subprocess
        import sys
        import tempfile
        import textwrap

        text = WORKFLOW.read_text(encoding="utf-8")
        receipt_step = text.split(
            "      - name: Publish scoped R2 MM deployment receipt", 1
        )[1].split("      - name: Destroy private deployment source", 1)[0]
        script = textwrap.dedent(
            receipt_step.split("          python - <<'PY'\n", 1)[1]
            .split("\n          PY", 1)[0]
        )
        for configured in (False, True):
            with self.subTest(configured=configured), tempfile.TemporaryDirectory() as td:
                env = dict(os.environ)
                env["REQUEST_SOURCE_SHA"] = "a" * 40
                env["CLOUDFLARE_DEPLOY_TOKEN_R2"] = "synthetic-scoped-token"
                env.pop("MMIBKR_ACCESS_AUD", None)
                env.pop("MMIBKR_ACCESS_TEAM_DOMAIN", None)
                if configured:
                    env["MMIBKR_ACCESS_AUD"] = "synthetic-audience"
                    env["MMIBKR_ACCESS_TEAM_DOMAIN"] = "https://example.cloudflareaccess.com"
                result = subprocess.run(
                    [sys.executable, "-c", script], cwd=td, env=env,
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                receipt = json.loads(
                    (Path(td) / "rendezvous/receipts/mmibkr-operator-console-deploy-r2.json")
                    .read_text(encoding="utf-8")
                )
                self.assertIs(receipt["access_reconciliation_step_completed"], configured)
                self.assertEqual(
                    receipt["access_reconciliation_state"],
                    "configured" if configured else "locked_unconfigured",
                )
                self.assertEqual(
                    receipt["access_reconciliation_credential"],
                    "legacy_access_capable_token" if configured else "not_exercised",
                )


    def test_exact_owner_release_approval_precedes_private_source_and_cloudflare(self):
        import os
        import subprocess
        import sys
        import textwrap

        text = WORKFLOW.read_text(encoding="utf-8")
        start = "      - name: Require owner-approved exact operator-console release source"
        after = "      - name: Materialize accepted private source from reusable encrypted vault"
        self.assertIn(start, text)
        self.assertLess(text.index("      - name: Resolve accepted console source"), text.index(start))
        self.assertLess(text.index(start), text.index(after))
        self.assertLess(text.index(start), text.index("      - name: Require Cloudflare deploy credential"))
        block = text.split(start, 1)[1].split(after, 1)[0]
        script = textwrap.dedent(
            block.split("          python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
        )
        for approved, permitted in (
            (None, False), ("b" * 40, False), ("A" * 40, False), ("a" * 40, True),
        ):
            with self.subTest(approved=approved):
                env = dict(os.environ)
                env["REQUEST_SOURCE_SHA"] = "a" * 40
                if approved is None:
                    env.pop("MMIBKR_OPERATOR_CONSOLE_APPROVED_SOURCE_SHA", None)
                else:
                    env["MMIBKR_OPERATOR_CONSOLE_APPROVED_SOURCE_SHA"] = approved
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    env=env, capture_output=True, text=True, check=False,
                )
                self.assertIs(result.returncode == 0, permitted)
                self.assertNotIn("a" * 40, result.stdout + result.stderr)
                if permitted:
                    self.assertIn("MMIBKR_OPERATOR_CONSOLE_OWNER_RELEASE_APPROVED=1", result.stdout)


    def test_public_ci_omits_access_control_plane_ids(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("MMIBKR_OPERATOR_CONSOLE_ACCESS_APP_ID=", text)
        self.assertNotIn("MMIBKR_OPERATOR_CONSOLE_ACCESS_POLICY_ID=", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_ACCESS_APP=CONFIGURED", text)


if __name__ == "__main__":
    unittest.main()
