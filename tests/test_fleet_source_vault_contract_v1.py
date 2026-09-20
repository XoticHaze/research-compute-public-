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
        self.assertIn("attest:\\${sourceSha}:\\${archiveSha}", text)
        self.assertIn("plaintext_sha256: archiveSha", text)
        self.assertIn("archive_bytes: archiveBytes", text)

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
        self.assertNotIn("vault:rsa-oaep:private-jwk", text)


if __name__ == "__main__":
    unittest.main()
