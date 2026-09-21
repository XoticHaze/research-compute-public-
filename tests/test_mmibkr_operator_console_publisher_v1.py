from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "mmibkr-selected-runtime-cloud-r1.yml"
PUBLISHER = ROOT / "scripts" / "mmibkr_operator_snapshot_publish_v1.py"


class OperatorConsolePublisherContractTests(unittest.TestCase):
    def test_cloud_owner_publishes_only_sanitized_operator_snapshot(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        publisher = PUBLISHER.read_text(encoding="utf-8")
        combined = text + "\n" + publisher
        self.assertIn("Publish private operator snapshot", text)
        self.assertIn(
            "strategy_runtime/cloud_operator_snapshot_v1/latest.json",
            text,
        )
        self.assertIn("mmibkr.cloud_operator_snapshot.v1", combined)
        self.assertIn("mmibkr-operator-console", combined)
        self.assertIn("/v1/operator-snapshot", combined)
        self.assertIn("X-MMIBKR-Caller-Run-Id", combined)
        self.assertIn("private_operator_state", combined)
        self.assertIn("account_identifiers_included", combined)
        self.assertIn("credentials_included", combined)
        self.assertIn("tokens_included", combined)
        self.assertIn("execution_authority_included", combined)
        self.assertIn("presentation_projection_only", combined)
        self.assertIn("broker_mutation_authority", combined)
        self.assertIn("live_execution_allowed", combined)
        self.assertIn("mmibkr-operator-snapshot-publish.json", text)
        self.assertIn("docker run --rm", text)
        self.assertIn("/app/data/strategy_runtime/cloud_operator_snapshot_v1/latest.json", text)
        self.assertIn("chmod 600", text)
        for marker in (
            "MMIBKR_OPERATOR_SNAPSHOT_ACCOUNT_IDENTIFIERS_INCLUDED=0",
            "MMIBKR_OPERATOR_SNAPSHOT_CREDENTIALS_INCLUDED=0",
            "MMIBKR_OPERATOR_SNAPSHOT_TOKENS_INCLUDED=0",
            "MMIBKR_OPERATOR_SNAPSHOT_PRIVATE_SOURCE_INCLUDED=0",
            "MMIBKR_OPERATOR_SNAPSHOT_EXECUTION_AUTHORITY_INCLUDED=0",
            "MMIBKR_OPERATOR_SNAPSHOT_BROKER_MUTATION_AUTHORITY=0",
            "MMIBKR_OPERATOR_SNAPSHOT_LIVE_EXECUTION_ALLOWED=0",
            "MMIBKR_OPERATOR_SNAPSHOT_DURABLE_READBACK_VERIFIED=1",
        ):
            self.assertIn(marker, text)

    def test_exact_runtime_image_validates_operator_snapshot_contract(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("tests.test_cloud_operator_snapshot_v1", text)
        self.assertIn("durable_readback_verified", text)
        self.assertLess(
            text.index("Validate private hostless/runtime contracts in exact image"),
            text.index("Run bounded selected-runtime cloud owner"),
        )

    def test_console_publish_is_nonblocking_for_trading_owner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        marker = "- name: Publish private operator snapshot"
        start = text.index(marker)
        section = text[start : start + 800]
        self.assertIn("continue-on-error: true", section)
        self.assertIn("if: ${{ success() }}", section)

    def test_publisher_uses_github_oidc_not_persistent_console_secret(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        publisher = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("ACTIONS_ID_TOKEN_REQUEST_URL", publisher)
        self.assertIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", publisher)
        self.assertIn('OIDC_AUDIENCE = "mmibkr-operator-console"', publisher)
        section_start = text.index("- name: Run bounded selected-runtime cloud owner")
        section_end = text.index("- name: Publish sanitized cloud-session receipt")
        section = text[section_start:section_end] + "\n" + publisher
        for forbidden in (
            "OPERATOR_CONSOLE_TOKEN",
            "CLOUDFLARE_API_TOKEN",
            "MMIBKR_PRIVATE_SOURCE_TOKEN",
            "IBKR_PAPER_PASSWORD",
            "TWS_PASSWORD",
        ):
            self.assertNotIn(forbidden, section)

    def test_cycle_snapshot_stream_is_deduped_and_nonblocking(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        start = text.index("- name: Run bounded selected-runtime cloud owner")
        end = text.index("- name: Build sanitized successor checkpoint")
        section = text[start:end]
        self.assertIn("id: cloud_owner", section)
        self.assertIn("docker run \\", section)
        self.assertIn("--name \"$owner_container\"", section)
        self.assertIn("-d \\", section)
        self.assertIn("docker logs -f", section)
        self.assertIn("docker exec \"$owner_container\" cat", section)
        self.assertIn("sha256sum \"$snapshot_tmp\"", section)
        self.assertIn('snapshot_sha256\" != \"$last_seen_sha256', section)
        self.assertIn("--mode stream", section)
        self.assertIn("Operator snapshot stream publish failed; selected-runtime owner continues.", section)
        self.assertIn("stream_publish_count=", section)
        self.assertIn("stream_attempt_count=", section)
        self.assertIn('exit \"$owner_exit\"', section)

    def test_stream_publisher_does_not_receive_broker_or_live_authority(self):
        publisher = PUBLISHER.read_text(encoding="utf-8")
        for forbidden in (
            "IBKR_REMOTE_EXCHANGE_TOKEN",
            "IBKR_PAPER_PASSWORD",
            "TWS_PASSWORD",
            "ENABLE_LIVE_TRADING",
            "placeOrder",
            "/submit",
            "/flatten",
            "/cancel",
        ):
            self.assertNotIn(forbidden, publisher)


if __name__ == "__main__":
    unittest.main()
