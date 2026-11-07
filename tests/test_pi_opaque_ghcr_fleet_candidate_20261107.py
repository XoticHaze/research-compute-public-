"""Real JS negative tests for private candidate resolver; no real private source identifiers."""
import re
import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLEET = ROOT / "cloudflare/fleet-authority/src/source_exchange.js"
MODULE = ROOT / "cloudflare/fleet-authority/src/pi_opaque_ghcr.js"


class OpaquePiCandidateTests(unittest.TestCase):
    def test_actual_js_parse(self):
        for path in (FLEET, MODULE):
            result = subprocess.run(["node", "--check", str(path)], text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr[:1500])

    def test_workflow_scoped_oidc_and_candidate_path(self):
        source = FLEET.read_text()
        module = MODULE.read_text()
        self.assertIn("matchedPiOpaquePublisher && piOpaquePublisherPathAllowed", source)
        self.assertIn("claims.event_name === 'push'", source)
        self.assertIn("'/v1/source-vault/pi-image-candidate'", source)
        self.assertIn("approved.source_sha !== sourceSha", source)
        self.assertIn("matchedBootstrap && privateArchivePathAllowed", source)
        self.assertIn("private_pi_candidate_unavailable", source)
        self.assertIn("PI_GHCR_OPAQUE_PUBLISH_IDENTITY", module)
        self.assertIn("mmibkr-ghcr-opaque-publish-r1.yml@refs/heads/main", module)
        self.assertNotIn("PRIVATE_SOURCE_TOKEN: ", source + module)
        # Guard the new public helper and its own tests against accidentally
        # adding a literal private commit fingerprint to public Git again.
        new_files = module + Path(__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?<![a-f0-9])[a-f0-9]{40}(?![a-f0-9])", new_files))

    def test_private_resolver_mock_and_rejection_matrix(self):
        js = textwrap.dedent(r"""
            import assert from 'node:assert/strict';
            import {resolvePiImageCandidate} from './cloudflare/fleet-authority/src/pi_opaque_ghcr.js';
            const sha='a'.repeat(40), branch='release/pi-bot-test';
            const suites=[
             'test_pi_root_external_baseline_owner_epoch_20261106',
             'test_pi_canonical_live_fill_commit_bridge_20261106',
             'test_pi_canonical_pending_live_fill_recovery_20261106',
             'test_pi_canonical_account_margin_cap_bridge_20261106',
             'test_pi_canonical_margin_call_binding_20261106',
             'test_selected_runtime_live_execution_ledger_v1',
            ];
            const candidate={
             schema:'mmibkr.pi_ghcr_release_candidate.v1',
             approval_level:'GHCR_PRIVATE_IMAGE_BUILD_AND_PUBLISH_ONLY_NOT_RUNTIME_OR_BROKER_APPROVAL',
             source_repository:'XoticHaze/mm-IBKR',source_sha:sha,
             source_branch_at_review:branch,source_branch_head_at_review:sha,
             release_expiry_utc:'2030-11-10T00:00:00Z',
             require_exact_commit_sha:true,
             target_registry:'ghcr.io/xotichaze/mmibkr-pi-canonical-private-20261030',
             target_visibility:'private',platform:'linux/arm64',
             dockerfile:'deploy/pi-bot/Dockerfile',
             approval_not_sufficient_for_live:true,
             native_brokerless_suites:suites,
            };
            const token={MMIBKR_PRIVATE_SOURCE_TOKEN:'synthetic-only'};
            const mock=(doc,head=sha)=>async uri=>{
              if(uri.includes('/contents/'))return{ok:true,json:async()=>({
                encoding:'base64',
                content:Buffer.from(JSON.stringify(doc)).toString('base64')})};
              if(uri.includes('/git/ref/heads/'))return{ok:true,json:async()=>({
                object:{sha:head}})};
              throw Error('unexpected path');
            };
            const ok=await resolvePiImageCandidate(token,{
              fetchImpl:mock(candidate),nowMs:1762490000000});
            assert.equal(ok.source_sha,sha);
            assert.equal(ok.broker_authorized,false);
            assert.deepEqual(ok.native_brokerless_suites,suites);
            const negatives=[
              [{...candidate,source_branch_head_at_review:'b'.repeat(40)},sha],
              [{...candidate,target_visibility:'public'},sha],
              [{...candidate,approval_not_sufficient_for_live:false},sha],
              [{...candidate,native_brokerless_suites:suites.slice(0,5)},sha],
              [{...candidate,release_expiry_utc:'2020-01-01T00:00:00Z'},sha],
              [candidate,'b'.repeat(40)],
            ];
            for(const [doc,head] of negatives)
              await assert.rejects(()=>resolvePiImageCandidate(token,{
                fetchImpl:mock(doc,head),nowMs:1762490000000}));
            await assert.rejects(()=>resolvePiImageCandidate({},{
              fetchImpl:mock(candidate),nowMs:1762490000000}));
            process.stdout.write('PI_OPAQUE_CANDIDATE_NEGATIVE_MATRIX=PASS');
        """)
        result = subprocess.run(
            ["node", "--experimental-default-type=module", "--input-type=module", "-e", js],
            text=True, capture_output=True, cwd=ROOT, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[:1500])
        self.assertIn("PI_OPAQUE_CANDIDATE_NEGATIVE_MATRIX=PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
