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

    def test_worker_verifier_secrets_are_bound_after_access_app_exists(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ACCESS_TEAM_DOMAIN", text)
        self.assertIn("ACCESS_AUD", text)
        self.assertIn("ACCESS_ALLOWED_EMAILS", text)
        self.assertIn("wrangler@4.131.2 secret put ACCESS_TEAM_DOMAIN", text)
        self.assertIn("wrangler@4.131.2 secret put ACCESS_AUD", text)
        self.assertIn("wrangler@4.131.2 secret put ACCESS_ALLOWED_EMAILS", text)

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

    def test_worker_control_plane_is_proved_before_access_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        control_plane_step = "Prove deployed Worker through Cloudflare control plane"
        access_step = "Reconcile exact-email Cloudflare Access application"
        self.assertIn(control_plane_step, text)
        self.assertIn("/workers/scripts/", text)
        self.assertIn("/settings", text)
        self.assertIn("MMIBKR_OPERATOR_CONSOLE_CONTROL_PLANE=READY", text)
        self.assertLess(text.index(control_plane_step), text.index(access_step))
        self.assertIn("for path in ('/', '/api/operator-snapshot', '/healthz'):", text)
        self.assertNotIn("operator-console pre-Access health did not converge", text)

    def test_unauthenticated_acceptance_rejects_public_200(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("class NoRedirect(HTTPRedirectHandler)", text)
        self.assertIn("if status == 200:", text)
        self.assertIn("unauthenticated operator-console path became public", text)
        self.assertIn("cloudflareaccess.com", text)


if __name__ == "__main__":
    unittest.main()
