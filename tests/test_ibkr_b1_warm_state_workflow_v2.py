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
        self.assertNotIn('/healthz', self.text)
        self.assertNotIn('allowed_workflow_sha', self.text)
        self.assertNotIn('ALLOWED_WORKFLOW_SHA', self.text)
        self.assertNotIn("expected_sha = os.environ['GITHUB_SHA']", self.text)
        self.assertNotIn('deployed fleet authority provenance does not match this workflow SHA', self.text)

        obtain = self.text.index('name: Obtain one-run sealed gateway environment')
        restore = self.text.index('name: Restore encrypted warm Gateway state if available')
        self.assertLess(obtain, restore)

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

    def test_clean_stop_generation_does_not_consume_legacy_live_snapshot(self):
        self.assertIn('name=ibkr-b1-warm-state-clean-v2&per_page=20', self.text)
        self.assertIn('name: ibkr-b1-warm-state-clean-v2', self.text)
        self.assertNotIn('name=ibkr-b1-warm-state&per_page=20', self.text)
        self.assertNotIn('name: ibkr-b1-warm-state\n', self.text)

    def test_controller_native_warm_seed_is_separate_from_live_settings(self):
        self.assertIn('warm_volume="ibkr-b1-warm-seed-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"', self.text)
        self.assertIn('-v "$warm_volume:/warm-seed"', self.text)
        self.assertIn('tar -xzf /import/ibkr-b1-warm-state.tgz -C /warm-seed', self.text)
        self.assertIn('-e GATEWAY_WARM_STATE=/home/ibgateway/warm-state', self.text)
        self.assertIn('-v "$warm_volume:/home/ibgateway/warm-state:ro"', self.text)
        self.assertIn('-e TWS_SETTINGS_PATH=/home/ibgateway/Jts_b1', self.text)
        self.assertIn('-v "$jts_volume:/home/ibgateway/Jts_b1"', self.text)
        self.assertIn("test \"$GATEWAY_WARM_STATE\" != \"$TWS_SETTINGS_PATH\"", self.text)
        self.assertIn('IBKR_CONTROLLER_NATIVE_WARM_SEED_BOUND=1', self.text)
        self.assertIn('IBKR_WARM_STATE_SEED_MODE=CONTROLLER_NATIVE', self.text)
        self.assertNotIn('-v "$jts_volume:/state" -v "$RUNNER_TEMP:/import:ro" alpine:3.22 sh -lc \'tar -xzf /import/ibkr-b1-warm-state.tgz -C /state', self.text)

    def test_native_seed_volume_is_destroyed_with_private_runtime(self):
        self.assertIn('docker volume rm -f "$warm_volume"', self.text)

    def test_consumer_acceptance_marker_is_emitted_after_post_auth_pipeline(self):
        post_auth = self.text.index('python scripts/ibkr_post_auth_pipeline_v1.py')
        consumer_ready = self.text.index("echo 'IBKR_CONSUMER_READY=1'", post_auth)
        self.assertLess(post_auth, consumer_ready)


if __name__ == '__main__':
    unittest.main()
