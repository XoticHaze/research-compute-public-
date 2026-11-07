"""No-cloud-mutation contract tests for independently approved neutral first seal."""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from scripts.operator import reference_neutral_first_seal_v1 as deploy


class FirstSealContractTests(unittest.TestCase):
    def test_exact_existing_account_and_merged_blob_pins(self):
        self.assertEqual(deploy.ACCOUNT, 'b33595eb85f346b0d1bf201810b4499a')
        self.assertEqual(deploy.WORKER, 'reference-release-broker-v1')
        self.assertEqual(len(deploy.EXPECTED_FILES), 6)
        self.assertEqual(deploy.EXPECTED_FILES['src/signer_vault.js'],
                         '9e37b06daf6e6deed3e0ec8100fce6904693ca3f')
        config, digest = deploy.exact_source()
        self.assertEqual(config['vars']['BROKER_SIGNER_MODE'], 'legacy-jwk-v1')
        self.assertEqual(len(digest), 64)
        self.assertEqual(set(config['exports']), {'GrantLedger', 'BrokerSignerVault'})

    def test_invalid_grant_authority_point_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'authority-public.b64'
            f.write_text(base64.b64encode(b'\x04' + b'\x00' * 64).decode())
            with self.assertRaisesRegex(deploy.Held, 'AUTHORITY_PUBLIC_P256_POINT_INVALID'):
                deploy.authority_public(f)

    def test_valid_uncompressed_grant_authority_public_is_verifiable_without_private(self):
        key = ec.generate_private_key(ec.SECP256R1())
        raw = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'authority-public.b64'
            f.write_text(base64.b64encode(raw).decode() + '\n')
            observed, key_id = deploy.authority_public(f)
            self.assertEqual(observed, base64.b64encode(raw).decode())
            self.assertEqual(key_id, 'sha256:' + hashlib.sha256(raw).hexdigest())

    def test_remote_active_version_requires_one_exact_100_percent(self):
        active = 'd0a7a738-739d-4570-84f5-549c711e58c3'
        with patch.object(deploy, 'run', return_value=json.dumps({
                'versions': [{'version_id': active, 'percentage': 100}]})):
            self.assertEqual(deploy.deployment_status('wrangler'), active)
        for versions in (
            [{'version_id': active, 'percentage': 50},
             {'version_id': active, 'percentage': 50}],
            [{'version_id': active, 'percentage': 90}],
            [{'version_id': 'invalid', 'percentage': 100}],
        ):
            with patch.object(deploy, 'run', return_value=json.dumps({'versions': versions})):
                with self.assertRaises(deploy.Held):
                    deploy.deployment_status('wrangler')

    def test_existing_signer_verifier_or_vault_not_rotated(self):
        active = 'd0a7a738-739d-4570-84f5-549c711e58c3'
        base = {'GRANT_LEDGER': {'name': 'GRANT_LEDGER',
                                 'class_name': 'GrantLedger',
                                 'namespace_id': 'original'},
                'ALLOWED_JOB_WORKFLOW_SHA': {'text': deploy.WORKFLOW_SHA},
                'ALLOWED_JOB_WORKFLOW_REF': {
                    'text': 'XoticHaze/research-compute-public-/.github/workflows/secure-compute-harness-v1.yml@'
                            + deploy.WORKFLOW_SHA},
                'MAX_ADMISSION_SECONDS': {'text': '300'},
                'MAX_INTENT_SECONDS': {'text': '259200'}}
        with patch.object(deploy, 'deployment_status', return_value=active), \
             patch.object(deploy, 'live_bindings', return_value=base):
            self.assertEqual(deploy.preflight('wrangler', active)[1], base['GRANT_LEDGER'])
        for name in ('BROKER_SIGNING_PRIVATE_JWK', 'AUTHORITY_PUBLIC_B64',
                     'BROKER_SIGNER_VAULT', 'BROKER_FIRST_SEAL_APPROVAL_ID'):
            with patch.object(deploy, 'deployment_status', return_value=active), \
                 patch.object(deploy, 'live_bindings',
                              return_value=dict(base, **{name: {'name': name}})):
                with self.assertRaisesRegex(deploy.Held, 'POSSIBLE_PRIOR_SIGNER_OR_SEAL'):
                    deploy.preflight('wrangler', active)

    def test_wrong_grant_ledger_namespace_or_live_workflow_pin_cannot_deploy(self):
        active = 'd0a7a738-739d-4570-84f5-549c711e58c3'
        for binding_set in (
            {'GRANT_LEDGER': {'class_name':'GrantLedger'}},
            {'GRANT_LEDGER': {'class_name':'GrantLedger', 'namespace_id':'original'},
             'ALLOWED_JOB_WORKFLOW_SHA': {'text':'0'*40}},
        ):
            with patch.object(deploy, 'deployment_status', return_value=active), patch.object(deploy, 'live_bindings', return_value=binding_set):
                with self.assertRaises(deploy.Held):
                    deploy.preflight('wrangler', active)

    def test_unapproved_stage_and_rollback_shortcuts_absent(self):
        source = Path(deploy.__file__).read_text()
        self.assertNotIn("'versions', 'upload'", source)
        self.assertNotIn("'secret', 'put'", source)
        self.assertNotIn("'rollback'", source)
        self.assertIn("'deploy', '--strict'", source)
        self.assertIn('APPROVE_', source)
        self.assertIn('AMBIENT_BEARER_OVERRIDE_REFUSED', source)

    def test_cannot_select_original_account_via_unreviewed_env(self):
        with patch.dict(deploy.os.environ, {'CLOUDFLARE_ACCOUNT_ID':
                        'ce43cd7b917d98a4bb4866d30eed99c0'}, clear=True):
            with self.assertRaisesRegex(deploy.Held, 'NEUTRAL_ACCOUNT_ENV_NOT_SELECTED'):
                deploy.wrangler()


if __name__ == '__main__':
    unittest.main()
