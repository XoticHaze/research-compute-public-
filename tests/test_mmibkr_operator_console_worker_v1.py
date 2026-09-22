from __future__ import annotations

from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cloudflare" / "operator-console" / "src" / "index.js"
WRANGLER = ROOT / "cloudflare" / "operator-console" / "wrangler.jsonc"


class OperatorConsoleWorkerContractTests(unittest.TestCase):
    def test_browser_surface_requires_cloudflare_access_jwt(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("cf-access-jwt-assertion", text)
        self.assertIn("ACCESS_TEAM_DOMAIN", text)
        self.assertIn("ACCESS_AUD", text)
        self.assertIn("/cdn-cgi/access/certs", text)
        self.assertIn("access_denied", text)
        self.assertIn("verifyAccess(request, env)", text)

    def test_publisher_is_github_oidc_bound_to_cloud_owner_workflows(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("mmibkr-operator-console", text)
        self.assertIn("token.actions.githubusercontent.com", text)
        self.assertIn("XoticHaze/research-compute-public-", text)
        self.assertIn("XoticHaze/mm-ibkr-runtime", text)
        self.assertIn("mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main", text)
        self.assertIn("runner_environment", text)
        self.assertIn("repository_visibility", text)
        self.assertIn("x-mmibkr-caller-run-id", text)

    def test_snapshot_fails_closed_on_privacy_and_authority_flags(self):
        text = SOURCE.read_text(encoding="utf-8")
        for marker in (
            "mmibkr.cloud_operator_snapshot.v1",
            "private_operator_state",
            "account_identifiers_included",
            "credentials_included",
            "tokens_included",
            "private_source_included",
            "execution_authority_included",
            "presentation_projection_only",
            "strategy_authority",
            "execution_policy_authority",
            "sizing_authority",
            "broker_mutation_authority",
            "live_execution_allowed",
        ):
            self.assertIn(marker, text)
        self.assertIn("snapshot_privacy_contract_rejected", text)
        self.assertIn("snapshot_authority_contract_rejected", text)

    def test_publish_201_requires_durable_object_readback(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("await this.ctx.storage.put('latest', record)", text)
        self.assertIn("await this.ctx.storage.get('latest')", text)
        self.assertIn("operator_snapshot_readback_failed", text)
        self.assertIn("snapshot_readback_unverified", text)
        self.assertIn("durable_readback_verified: true", text)

    def test_machine_snapshot_read_is_oidc_bound_and_read_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        route = "url.pathname === '/v1/operator-snapshot-read'"
        self.assertIn(route, text)
        start = text.index(route)
        end = text.index("await verifyAccess(request, env)", start)
        section = text[start:end]
        self.assertIn("verifySnapshotReader(request)", section)
        self.assertIn("operator-state.internal/latest", section)
        self.assertIn("validateSnapshot(record.snapshot)", section)
        self.assertIn("mmibkr.operator_console_machine_read.v1", section)
        self.assertIn("broker_mutation_authority: false", section)
        self.assertIn("live_execution_allowed: false", section)
        self.assertNotIn("storage.put(", section)
        self.assertNotIn("placeOrder", section)
        self.assertNotIn("/submit", section)
        self.assertNotIn("/flatten", section)
        self.assertNotIn("/cancel", section)

    def test_encrypted_public_bridge_is_read_only_oidc_reader_not_publisher(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("const ALLOWED_MACHINE_READERS", text)
        self.assertIn("repository: 'XoticHaze/research-compute-public-'", text)
        self.assertIn(
            "XoticHaze/research-compute-public-/.github/workflows/mmibkr-operator-snapshot-read-bridge-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn("repository_visibility: 'public'", text)
        publisher_start = text.index("async function verifyPublisher(request)")
        reader_start = text.index("async function verifySnapshotReader(request)")
        publisher_section = text[publisher_start:reader_start]
        self.assertIn("claims.repository_visibility !== 'public'", publisher_section)
        self.assertNotIn("ALLOWED_MACHINE_READERS", publisher_section)
        reader_end = text.index("function normalizeTeamDomain", reader_start)
        reader_section = text[reader_start:reader_end]
        self.assertIn("trustedMachineReader", reader_section)
        self.assertIn("identity.repository_visibility", reader_section)
        read_route = text.index("url.pathname === '/v1/operator-snapshot-read'")
        access_gate = text.index("await verifyAccess(request, env)", read_route)
        read_section = text[read_route:access_gate]
        self.assertIn("verifySnapshotReader(request)", read_section)
        self.assertNotIn("verifyPublisher(request)", read_section)

    def test_machine_snapshot_read_precedes_human_access_gate(self):
        text = SOURCE.read_text(encoding="utf-8")
        machine = text.index("url.pathname === '/v1/operator-snapshot-read'")
        access = text.index("await verifyAccess(request, env)")
        self.assertLess(machine, access)

    def test_static_assets_run_through_worker_first(self):
        config = json.loads(WRANGLER.read_text(encoding="utf-8"))
        assets = config["assets"]
        self.assertTrue(assets["run_worker_first"])
        self.assertEqual(assets["binding"], "ASSETS")
        self.assertEqual(assets["not_found_handling"], "single-page-application")
        self.assertEqual(config["name"], "mmibkr-operator-console")

    def test_private_snapshot_state_is_durable_object_backed(self):
        config = json.loads(WRANGLER.read_text(encoding="utf-8"))
        bindings = config["durable_objects"]["bindings"]
        self.assertEqual(
            bindings,
            [{"name": "OPERATOR_STATE", "class_name": "OperatorState"}],
        )
        self.assertEqual(config["exports"]["OperatorState"]["storage"], "sqlite")
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("this.ctx.storage.put('latest'", text)
        self.assertIn("this.ctx.storage.get('latest')", text)

    def test_worker_does_not_embed_broker_or_private_source_credentials(self):
        text = SOURCE.read_text(encoding="utf-8")
        forbidden = (
            "IBKR_PAPER_USERNAME",
            "IBKR_PAPER_PASSWORD",
            "MMIBKR_PRIVATE_SOURCE_TOKEN",
            "IBKR_REMOTE_SOURCE_TOKEN",
            "TWS_PASSWORD",
        )
        for marker in forbidden:
            self.assertNotIn(marker, text)

    def test_same_source_partial_runtime_projection_preserves_prior_runtime_rows(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("function mergeRuntimeProjection(previousRecord, incomingSnapshot)", text)
        self.assertIn("const previousSource = snapshotSourceSha(previous)", text)
        self.assertIn("const incomingSource = snapshotSourceSha(incomingSnapshot)", text)
        self.assertIn("previousSource !== incomingSource", text)
        self.assertIn("const merged = new Map()", text)
        self.assertIn("for (const row of previousRuntimes)", text)
        self.assertIn("for (const row of incomingRuntimes)", text)
        self.assertIn("merged.set(runtimeId, row)", text)
        self.assertIn("...incomingSnapshot", text)
        self.assertIn("runtimes,", text)
        self.assertIn("runtimeMergeApplied: runtimes.length > incomingRuntimes.length", text)

    def test_runtime_union_receipt_distinguishes_received_and_stored_counts(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("received_runtime_count: incomingSnapshot.runtimes.length", text)
        self.assertIn("stored_runtime_count: snapshot.runtimes.length", text)
        self.assertIn("runtime_merge_applied: merged.runtimeMergeApplied", text)
        self.assertIn("received_runtime_count: receipt.received_runtime_count", text)
        self.assertIn("runtime_count: receipt.received_runtime_count", text)
        self.assertIn("stored_runtime_count: receipt.runtime_count", text)

    def test_source_change_fails_closed_to_incoming_runtime_set(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("if (!previousSource || !incomingSource || previousSource !== incomingSource)", text)
        source_change = text.index(
            "if (!previousSource || !incomingSource || previousSource !== incomingSource)"
        )
        incoming_return = text.index("snapshot: incomingSnapshot", source_change)
        merge_map = text.index("const merged = new Map()", source_change)
        self.assertLess(incoming_return, merge_map)

    def test_external_publish_receipt_keeps_runtime_count_legacy_compatible(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("runtime_count: receipt.received_runtime_count", text)
        self.assertIn("stored_runtime_count: receipt.runtime_count", text)
        self.assertIn("received_runtime_count: receipt.received_runtime_count", text)


if __name__ == "__main__":
    unittest.main()
