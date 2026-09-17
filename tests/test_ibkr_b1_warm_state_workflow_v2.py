from pathlib import Path
import unittest


WORKFLOW = Path('.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml')


class IbkrB1WarmStateWorkflowV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding='utf-8')

    def test_authority_request_path_has_no_mutable_sha_or_health_preflight(self):
        self.assertIn('FLEET_AUTHORITY_URL:', self.text)
        self.assertIn('scripts/fleet_authority_envelope_consumer_v1.py', self.text)
        self.assertNotIn('FLEET_AUTHORITY_HEALTH', self.text)
        self.assertNotIn('Require deployed B1 authority contract', self.text)
        self.assertNotIn('allowed_workflow_sha', self.text)
        self.assertNotIn('ALLOWED_WORKFLOW_SHA', self.text)
        self.assertNotIn('expected_sha = os.environ[\'GITHUB_SHA\']', self.text)
        self.assertNotIn('deployed fleet authority provenance does not match this workflow SHA', self.text)

    def test_fresh_and_restored_sessions_are_classified_separately(self):
        self.assertIn('${{ steps.restore.outputs.restored }}', self.text)
        self.assertIn('IBKR_AUTH_PATH=WARM_STATE_RESTORED', self.text)
        self.assertIn('IBKR_AUTH_PATH=FRESH_SESSION', self.text)
        self.assertIn('IBKR_WARM_SESSION_REUSED=1', self.text)
        self.assertIn('IBKR_WARM_SESSION_REUSED=0', self.text)
        self.assertIn('IBKR_OPERATOR_ACTION=NONE_WARM_SESSION_REUSED', self.text)
        self.assertIn('IBKR_OPERATOR_ACTION=NONE_FRESH_SESSION_ESTABLISHED', self.text)

    def test_warm_reuse_ready_is_not_claimed_at_api_ready_boundary(self):
        api_ready = self.text.index("echo 'IBKR_GATEWAY_API_READY=1'")
        graceful_stop = self.text.index('name: Gracefully stop authenticated Gateway before warm-state snapshot')
        reuse_ready = self.text.index("print('IBKR_WARM_REUSE_READY=1')")
        self.assertLess(api_ready, graceful_stop)
        self.assertLess(graceful_stop, reuse_ready)
        self.assertNotIn('IBKR_WARM_REUSE_READY=1', self.text[api_ready:graceful_stop])

    def test_gateway_is_gracefully_stopped_before_snapshot(self):
        graceful_stop = self.text.index('name: Gracefully stop authenticated Gateway before warm-state snapshot')
        stop_command = self.text.index('docker stop --time 90 ibkr-cloudflare-b1', graceful_stop)
        seal = self.text.index('name: Seal authenticated Gateway warm state')
        publish = self.text.index('name: Publish reusable encrypted warm state')
        self.assertLess(graceful_stop, stop_command)
        self.assertLess(stop_command, seal)
        self.assertLess(seal, publish)
        self.assertNotIn('docker stop --time 10 ibkr-cloudflare-b1', self.text)

    def test_snapshot_requires_confirmed_clean_stop(self):
        self.assertIn('id: graceful_stop', self.text)
        self.assertIn("echo 'stopped=1' >> \"$GITHUB_OUTPUT\"", self.text)
        self.assertIn("if: steps.graceful_stop.outputs.stopped == '1'", self.text)
        self.assertIn('IBKR_GATEWAY_GRACEFUL_STOP=1', self.text)

    def test_reusable_state_claim_requires_seal(self):
        sealed = self.text.index("print('IBKR_WARM_STATE_SEALED=1')")
        persisted = self.text.index("print('IBKR_WARM_STATE_PERSISTED=1')")
        ready = self.text.index("print('IBKR_WARM_REUSE_READY=1')")
        self.assertLess(sealed, persisted)
        self.assertLess(persisted, ready)


if __name__ == '__main__':
    unittest.main()
