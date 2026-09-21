from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"


class OperatorConsolePublisherContractTests(unittest.TestCase):
    def test_cloud_owner_publishes_only_sanitized_operator_snapshot(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Publish private operator snapshot", text)
        self.assertIn(
            "strategy_runtime/cloud_operator_snapshot_v1/latest.json",
            text,
        )
        self.assertIn("mmibkr.cloud_operator_snapshot.v1", text)
        self.assertIn("mmibkr-operator-console", text)
        self.assertIn("/v1/operator-snapshot", text)
        self.assertIn("X-MMIBKR-Caller-Run-Id", text)
        self.assertIn("private_operator_state", text)
        self.assertIn("account_identifiers_included", text)
        self.assertIn("credentials_included", text)
        self.assertIn("tokens_included", text)
        self.assertIn("execution_authority_included", text)
        self.assertIn("presentation_projection_only", text)
        self.assertIn("broker_mutation_authority", text)
        self.assertIn("live_execution_allowed", text)

    def test_console_publish_is_nonblocking_for_trading_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        marker = "- name: Publish private operator snapshot"
        start = text.index(marker)
        section = text[start : start + 800]
        self.assertIn("continue-on-error: true", section)
        self.assertIn("if: ${{ success() }}", section)

    def test_publisher_uses_github_oidc_not_persistent_console_secret(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ACTIONS_ID_TOKEN_REQUEST_URL", text)
        self.assertIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", text)
        self.assertIn("audience'] = 'mmibkr-operator-console'", text)
        section_start = text.index("- name: Publish private operator snapshot")
        section_end = text.index("- name: Publish sanitized cloud-session receipt")
        section = text[section_start:section_end]
        for forbidden in (
            "OPERATOR_CONSOLE_TOKEN",
            "CLOUDFLARE_API_TOKEN",
            "MMIBKR_PRIVATE_SOURCE_TOKEN",
            "IBKR_PAPER_PASSWORD",
            "TWS_PASSWORD",
        ):
            self.assertNotIn(forbidden, section)


if __name__ == "__main__":
    unittest.main()
