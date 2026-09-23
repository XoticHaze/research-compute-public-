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

    def test_promotion_review_snapshot_is_exactly_code_pinned_after_bootstrap(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "'1eadfe97304bb78a7e0fabf571e73dfcf0060909': Object.freeze({",
            text,
        )
        self.assertIn(
            "source_ref: '1eadfe97304bb78a7e0fabf571e73dfcf0060909'",
            text,
        )
        self.assertIn(
            "manifest_sha256: 'b908a6bdd827c3111d4bb66e23449037d31bbfa1b36f22d868357b15abd99c9b'",
            text,
        )
        self.assertIn(
            "archive_sha256: '72a6b205fa7d601162d8e9c79bb888fcc8f475c74f0b4b67229189b5fae58597'",
            text,
        )
        self.assertIn("archive_bytes: 66322824", text)

    def test_forward_testing_snapshot_is_exactly_code_pinned_after_bootstrap(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "'5e56997fe31987fb1ac471ebecb03795b6614887': Object.freeze({",
            text,
        )
        self.assertIn(
            "source_ref: '5e56997fe31987fb1ac471ebecb03795b6614887'",
            text,
        )
        self.assertIn(
            "manifest_sha256: '90f7003b95d526cdbfd0d706314cf45aaa3e727353093684c66e8749342526a0'",
            text,
        )
        self.assertIn(
            "archive_sha256: '1061e11f3105e51ff193a1119b3260e34a4f6b5a388a27adcf806631ba0a6a2e'",
            text,
        )
        self.assertIn("archive_bytes: 66336837", text)

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
            "mmibkr-private-pr666-ownership-final-validation-r1.yml@refs/heads/main",
            text,
        )
        self.assertIn(
            "a303718aade958c98bc12d5e812de870eb6f229d",
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
            "29a445ff42f8e1e2be0533f8cc200537f35caa5a",
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
            "70aec26cd98b2c2273c1b762694d55f2698baa7d",
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
        self.assertIn("PRIVATE_SOURCE_SHA: 70aec26cd98b2c2273c1b762694d55f2698baa7d", workflow)
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
            "d7b468ea22740df65c4b350dc15b74b0c377280f",
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
        self.assertIn("PRIVATE_SOURCE_SHA: d7b468ea22740df65c4b350dc15b74b0c377280f", workflow)
        self.assertIn("npm run verify:promotion-review", workflow)
        self.assertIn("npm run build", workflow)
        self.assertIn("'broker_action': False", workflow)
        self.assertIn("'live_trading_allowed': False", workflow)
        self.assertIn("MMIBKR_PRIVATE_PLAINTEXT_PUBLISHED=0", workflow)
        self.assertNotIn('cat "$log"', workflow)

    def test_promotion_review_merged_source_bootstrap_is_exact_sha_expiring_and_bootstrap_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("OPERATOR_CONSOLE_PROMOTION_BOOTSTRAP_SOURCE", text)
        self.assertIn(
            "5e56997fe31987fb1ac471ebecb03795b6614887",
            text,
        )
        self.assertIn("OPERATOR_CONSOLE_PROMOTION_BOOTSTRAP_EXPIRES_AT", text)
        self.assertIn("2026-09-23T12:00:00Z", text)
        self.assertIn("operatorConsolePromotionBootstrapApproved", text)
        self.assertIn(
            "matchesIdentity(identity, SOURCE_VAULT_BOOTSTRAP_IDENTITY)",
            text,
        )
        self.assertNotIn(
            "matchesIdentity(identity, OPERATOR_CONSOLE_DEPLOY_IDENTITY)\n  );\n  const operatorConsolePromotionBootstrapApproved",
            text,
        )

    def test_selected_runtime_ownership_source_bootstrap_is_exact_sha_expiring_and_bootstrap_only(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("SELECTED_RUNTIME_OWNERSHIP_BOOTSTRAP_SOURCE", text)
        self.assertIn(
            "35e6b44e5c2618f780a84c1c204fe14c76bdf0e5",
            text,
        )
        self.assertIn("SELECTED_RUNTIME_OWNERSHIP_BOOTSTRAP_EXPIRES_AT", text)
        self.assertIn("2026-09-23T12:00:00Z", text)
        self.assertIn("selectedRuntimeOwnershipBootstrapApproved", text)
        self.assertIn(
            "matchesIdentity(identity, SOURCE_VAULT_BOOTSTRAP_IDENTITY)",
            text,
        )
        self.assertNotIn(
            "matchesIdentity(identity, OPERATOR_CONSOLE_DEPLOY_IDENTITY)\n  );\n  const selectedRuntimeOwnershipBootstrapApproved",
            text,
        )

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
