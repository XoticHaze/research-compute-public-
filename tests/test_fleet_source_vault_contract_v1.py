from __future__ import annotations

from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "cloudflare/fleet-authority/src/source_exchange.js"
INDEX = ROOT / "cloudflare/fleet-authority/src/index.js"


class FleetSourceVaultContractTests(unittest.TestCase):
    def test_vault_is_code_approved_and_private_key_never_exposed(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("APPROVED_SOURCE_SNAPSHOTS", text)
        self.assertIn("manifest_sha256", text)
        self.assertIn("archive_sha256", text)
        self.assertIn("archive_bytes", text)
        self.assertIn("source_ref", text)
        self.assertIn("vault_source_snapshot_not_approved", text)
        self.assertIn("RSA-OAEP", text)
        self.assertIn("modulusLength: 3072", text)
        self.assertIn("SOURCE_VAULT_RSA_PRIVATE_KEY", text)
        self.assertIn("SOURCE_VAULT_RSA_PUBLIC_KEY", text)
        self.assertIn("private_key_exported: false", text)
        self.assertIn("keypair_self_test: true", text)
        self.assertIn("_vaultKeypairSelfTest", text)
        self.assertNotIn("private_jwk:", text)
        self.assertNotIn("privateJwk:", text)

    def test_public_key_is_public_but_unwrap_requires_runtime_oidc(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("/v1/source-vault/public-key", text)
        self.assertIn("/v1/source-vault/unwrap", text)
        self.assertIn(
            "(method === 'POST' && pathname === '/v1/source-vault/unwrap')",
            text,
        )
        self.assertIn("return 'consumer';", text)
        self.assertIn("role !== 'consumer'", text)

    def test_approved_unwrap_creates_reusable_same_source_attestation(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("mmibkr-source-vault-unwrap-v2", text)
        self.assertIn("mmibkr-cloud-source-vault-attestation-v1", text)
        self.assertIn("reusable_attestation_stored: true", text)
        self.assertIn("source_transport: 'fleet_authority_exact_sha_encrypted_snapshot_vault'", text)
        self.assertIn("attest:${sourceSha}:${archiveSha}", text)
        self.assertIn("plaintext_sha256: archiveSha", text)
        self.assertIn("archive_bytes: archiveBytes", text)

    def test_fleet_attested_source_can_be_first_use_pinned_as_reusable_vault_snapshot(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("mmibkr-source-vault-dynamic-approval-v1", text)
        self.assertIn("vaultapproval:", text)
        self.assertIn("fleet_attested_first_use_pin", text)
        self.assertIn("mmibkr-cloud-source-fleet-stream-attestation-v1", text)
        self.assertIn("APPROVED_PRIVATE_SOURCE_STREAMS.has(sourceSha)", text)
        self.assertIn("snapshot_manifest_approval", text)

    def test_vault_unwrap_receives_request_identity_context(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("async _vaultUnwrap(body, request)", text)
        self.assertIn("this._vaultUnwrap(body, request)", text)
        self.assertIn("this._producerIdentity(request)", text)

    def test_private_source_stream_is_oidc_gated_and_code_pinned(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("MMIBKR_PRIVATE_SOURCE_TOKEN", text)
        self.assertIn("APPROVED_PRIVATE_SOURCE_STREAMS", text)
        self.assertIn("ca1d97ebfd95a4e23e7be520a4d8a44d49d44251", text)
        self.assertIn("ec1831181ae49ef75679e103737ac04a9bc8a445", text)
        self.assertIn("cb28771e5fd3aa610d8fcf2ef683596a1cfabd51", text)
        self.assertIn("06ee6b93f1155a242b846b967fc73df05afcebd9", text)
        self.assertIn("61f0842b2de8709509453cb390310d246ea39ad3", text)
        self.assertIn("1ecb1de8dda1c8797b6fa1af6dba6f6e1765438e", text)
        self.assertIn("5aeb0370a18c4c941852c7454706ba9ffa28da68", text)
        self.assertIn("d81df85788ebb6be6d4d69b9b9a537be96f16507", text)
        self.assertIn("8a82107be253c3facd3b090cf752bc51b3a8ef8d", text)
        self.assertIn("5c261f6252dd332806908d9f9a8ba0ac839f1b63", text)
        self.assertIn("/v1/source-vault/private-archive/", text)
        self.assertIn("fleet_authority_oidc_private_archive_stream", text)
        self.assertIn("redirect: 'follow'", text)
        self.assertIn("upstream.body", text)
        self.assertIn("private_source_token_exposed: false", text)

    def test_ui_build_private_stream_is_exact_sha_scoped_and_expires(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("UI_BUILD_VALIDATION_IDENTITY", text)
        self.assertIn(
            "mm-ui-react-exact-build-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn(
            "ca0adfa9f07d85b500594bbd334bb002e20b1eb6",
            text,
        )
        self.assertIn("UI_BUILD_PRIVATE_ARCHIVE_EXPIRES_AT", text)
        self.assertIn("2026-09-23T12:00:00Z", text)
        self.assertIn("isPrivateSourceStreamApproved", text)
        self.assertIn("privateArchivePathAllowed", text)
        self.assertIn("/v1/source-vault/private-archive/attest", text)
        self.assertIn(
            "/^\\/v1\\/source-vault\\/private-archive\\/[0-9a-f]{40}$/",
            text,
        )

    def test_private_pr_validation_stream_is_exact_sha_expiring_and_archive_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("PRIVATE_PR_EXACT_VALIDATION_IDENTITY", text)
        self.assertIn(
            "mmibkr-private-pr-exact-validation-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn(
            "aac81518231e776c28c646d974473c631d6e3a05",
            text,
        )
        self.assertIn("PRIVATE_PR_EXACT_VALIDATION_EXPIRES_AT", text)
        self.assertIn("2026-09-23T12:00:00Z", text)
        self.assertIn("matchedPrivatePrValidation", text)
        self.assertIn(
            "(matchedPrivatePrValidation && privateArchivePathAllowed)",
            text,
        )
        self.assertNotIn(
            "(matchedPrivatePrValidation && operatorDeployPathAllowed)",
            text,
        )

    def test_private_pr_validation_uses_exact_pr668_suite_without_public_test_log(self):
        workflow = (ROOT / ".github" / "workflows" / "mmibkr-private-pr-exact-validation-r1.yml").read_text(encoding="utf-8")
        self.assertIn("Build exact private bot image for PR 668 validation", workflow)
        self.assertIn("Validate exact private PR 668 operator backend contracts", workflow)
        self.assertIn("Validate exact private PR 668 Bot Console acceptance and production build", workflow)
        self.assertIn("MMIBKR_PRIVATE_PR668_EXACT_IMAGE_READY=1", workflow)
        self.assertIn("ENABLE_LIVE_TRADING=0", workflow)
        self.assertIn("tests.test_cloud_operator_snapshot_v1", workflow)
        self.assertIn("tests.test_crw_operator_context_projection_v1", workflow)
        self.assertIn("npm run verify:bot-console", workflow)
        self.assertIn("npm run build", workflow)
        self.assertIn('(\n            set -euo pipefail\n            cd "$ui"', workflow)
        self.assertIn("MMIBKR_PRIVATE_PLAINTEXT_PUBLISHED=0", workflow)
        self.assertIn("MMIBKR_PRIVATE_PR_SAFE_DIAGNOSTIC=", workflow)
        self.assertNotIn('cat "$log"', workflow)

    def test_private_pr666_validation_is_isolated_exact_sha_expiring_and_archive_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("PRIVATE_PR666_EXACT_VALIDATION_IDENTITY", text)
        self.assertIn(
            "mmibkr-private-pr666-exact-validation-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn(
            "553197599239f1efd0a302642872a5a064a1da32",
            text,
        )
        self.assertIn("PRIVATE_PR666_EXACT_VALIDATION_EXPIRES_AT", text)
        self.assertIn("matchedPrivatePr666Validation", text)
        self.assertIn(
            "(matchedPrivatePr666Validation && privateArchivePathAllowed)",
            text,
        )
        self.assertNotIn(
            "(matchedPrivatePr666Validation && operatorDeployPathAllowed)",
            text,
        )

    def test_private_pr670_validation_is_isolated_exact_sha_expiring_and_archive_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("PRIVATE_PR670_EXACT_VALIDATION_IDENTITY", text)
        self.assertIn(
            "mmibkr-private-pr670-forward-lifecycle-validation-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn(
            "7e6c9fba036f26c05022896ada6f98fb79b1e560",
            text,
        )
        self.assertIn("PRIVATE_PR670_EXACT_VALIDATION_EXPIRES_AT", text)
        self.assertIn("matchedPrivatePr670Validation", text)
        self.assertIn(
            "(matchedPrivatePr670Validation && privateArchivePathAllowed)",
            text,
        )
        self.assertNotIn(
            "(matchedPrivatePr670Validation && operatorDeployPathAllowed)",
            text,
        )

    def test_private_pr671_validation_is_isolated_exact_sha_expiring_and_archive_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("PRIVATE_PR671_EXACT_VALIDATION_IDENTITY", text)
        self.assertIn(
            "mmibkr-private-pr671-forward-evidence-validation-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn(
            "23233724fa4f84c16b5b92467070931a6e9c6e50",
            text,
        )
        self.assertIn("PRIVATE_PR671_EXACT_VALIDATION_EXPIRES_AT", text)
        self.assertIn("matchedPrivatePr671Validation", text)
        self.assertIn(
            "(matchedPrivatePr671Validation && privateArchivePathAllowed)",
            text,
        )
        self.assertNotIn(
            "(matchedPrivatePr671Validation && operatorDeployPathAllowed)",
            text,
        )

        workflow = (
            ROOT
            / ".github"
            / "workflows"
            / "mmibkr-private-pr671-forward-evidence-validation-r1.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("PRIVATE_SOURCE_SHA: 23233724fa4f84c16b5b92467070931a6e9c6e50", workflow)
        self.assertIn("tests.test_cloud_forward_performance_v1", workflow)
        self.assertIn("tests.test_cloud_operator_snapshot_v1", workflow)
        self.assertIn("BotConsolePage.acceptance.test.mjs", workflow)
        self.assertIn("npm run build", workflow)
        self.assertIn("MMIBKR_PRIVATE_PLAINTEXT_PUBLISHED=0", workflow)
        self.assertNotIn('cat "$log"', workflow)

    def test_private_promotion_review_validation_is_exact_sha_expiring_and_archive_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("PRIVATE_PROMOTION_REVIEW_EXACT_VALIDATION_IDENTITY", text)
        self.assertIn(
            "mmibkr-private-promotion-review-validation-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn(
            "cfb18a0b6ff02f3aa35823d23223b029fa770be4",
            text,
        )
        self.assertIn("PRIVATE_PROMOTION_REVIEW_EXACT_VALIDATION_EXPIRES_AT", text)
        self.assertIn("2026-09-23T12:00:00Z", text)
        self.assertIn("matchedPrivatePromotionReviewValidation", text)
        self.assertIn(
            "(matchedPrivatePromotionReviewValidation && privateArchivePathAllowed)",
            text,
        )
        self.assertNotIn(
            "(matchedPrivatePromotionReviewValidation && operatorDeployPathAllowed)",
            text,
        )

        workflow = (
            ROOT
            / ".github"
            / "workflows"
            / "mmibkr-private-promotion-review-validation-r1.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("PRIVATE_SOURCE_SHA: cfb18a0b6ff02f3aa35823d23223b029fa770be4", workflow)
        self.assertIn("npm run verify:promotion-review", workflow)
        self.assertIn("npm run build", workflow)
        self.assertIn("ENABLE_LIVE_TRADING=0", workflow)
        self.assertIn("MMIBKR_PRIVATE_PLAINTEXT_PUBLISHED=0", workflow)
        self.assertNotIn('cat "$log"', workflow)

    def test_runtime_bootstrap_identity_is_private_archive_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("SOURCE_VAULT_BOOTSTRAP_IDENTITY", text)
        self.assertIn(
            "mmibkr-source-vault-bootstrap-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn("matchedBootstrap", text)
        self.assertIn("privateArchivePathAllowed", text)
        self.assertIn("(matchedBootstrap && privateArchivePathAllowed)", text)

    def test_operator_console_deploy_identity_is_vault_unwrap_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("OPERATOR_CONSOLE_DEPLOY_IDENTITY", text)
        self.assertIn(
            "mmibkr-operator-console-deploy-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn("matchedOperatorDeploy", text)
        self.assertIn("operatorDeployPathAllowed", text)
        self.assertIn("pathname === '/v1/source-vault/unwrap'", text)
        self.assertIn(
            "(matchedOperatorDeploy && operatorDeployPathAllowed)",
            text,
        )

    def test_missed_trade_audit_identity_is_vault_unwrap_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("MISSED_TRADE_AUDIT_IDENTITY", text)
        self.assertIn(
            "mmibkr-selected-runtime-missed-trade-audit-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn("matchedMissedTradeAudit", text)
        self.assertIn("operatorDeployPathAllowed", text)
        self.assertIn(
            "(matchedMissedTradeAudit && operatorDeployPathAllowed)",
            text,
        )

    def test_stream_attestation_is_bound_to_run_stream_sha_and_size(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("streamgrant:", text)
        self.assertIn("mmibkr-fleet-private-source-attest-v1", text)
        self.assertIn("archive_sha256", text)
        self.assertIn("archive_bytes", text)
        self.assertIn("private_attestation_stored: true", text)
        self.assertIn("attest:${sourceSha}:${archiveSha}", text)
        self.assertIn("plaintext_sha256: archiveSha", text)

    def test_runtime_identity_is_exactly_pinned(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("XoticHaze/mm-ibkr-runtime", text)
        self.assertIn(
            "XoticHaze/mm-ibkr-runtime/.github/workflows/"
            "mmibkr-selected-runtime-cloud-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn("XoticHaze/research-compute-public-", text)
        self.assertIn("refs/heads/ibkr-b1-authority-v1", text)

    def test_health_exposes_vault_configuration_only(self):
        text = INDEX.read_text(encoding="utf-8")
        self.assertIn("source_vault_configured", text)
        self.assertIn("private_source_authority_configured", text)
        self.assertIn("MMIBKR_PRIVATE_SOURCE_TOKEN", text)
        self.assertNotIn("vault:rsa-oaep:private-jwk", text)


if __name__ == "__main__":
    unittest.main()

# Hashed unwrap diagnostics must remain non-secret.

# source-vault response encoding helper must exist.
