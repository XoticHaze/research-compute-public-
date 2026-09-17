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

    def test_restored_seed_is_owned_and_readable_by_controller_runtime_user(self):
        self.assertIn('gateway_uid="$(docker run --rm --entrypoint /usr/bin/id "$IBKR_CONTROLLER_IMAGE" -u)"', self.text)
        self.assertIn('gateway_gid="$(docker run --rm --entrypoint /usr/bin/id "$IBKR_CONTROLLER_IMAGE" -g)"', self.text)
        self.assertIn('-e GATEWAY_UID="$gateway_uid"', self.text)
        self.assertIn('-e GATEWAY_GID="$gateway_gid"', self.text)
        self.assertIn('chown -R "$GATEWAY_UID:$GATEWAY_GID" /warm-seed', self.text)
        self.assertIn('-v "$warm_volume:/warm-seed:ro"', self.text)
        self.assertIn('cp -a /warm-seed/. /tmp/warm-read-check/', self.text)
        self.assertIn('IBKR_WARM_STATE_SEED_READABLE=1', self.text)

    def test_native_seed_volume_is_destroyed_with_private_runtime(self):
        self.assertIn('docker volume rm -f "$warm_volume"', self.text)

    def test_consumer_acceptance_marker_is_emitted_after_post_auth_pipeline(self):
        post_auth = self.text.index('python scripts/ibkr_post_auth_pipeline_v1.py')
        consumer_ready = self.text.index("echo 'IBKR_CONSUMER_READY=1'", post_auth)
        self.assertLess(post_auth, consumer_ready)

    def test_readonly_remains_default_and_writable_api_requires_explicit_proof_dispatch(self):
        self.assertIn('default: readonly', self.text)
        self.assertIn('- paper_submit_proof', self.text)
        self.assertIn("IBKR_PAPER_PROOF_MODE: ${{ github.event_name == 'workflow_dispatch' && inputs.mode == 'paper_submit_proof' && '1' || '0' }}", self.text)
        self.assertIn('api_read_only=yes', self.text)
        self.assertIn('if [ "$IBKR_PAPER_PROOF_MODE" = "1" ]; then', self.text)
        self.assertIn('api_read_only=no', self.text)
        self.assertIn('-e READ_ONLY_API="$api_read_only"', self.text)
        self.assertNotIn('-e READ_ONLY_API=no', self.text)

    def test_explicit_dispatch_nonce_is_bound_into_run_identity(self):
        self.assertIn('dispatch_nonce:', self.text)
        self.assertIn("format('{0} {1}', inputs.mode, inputs.dispatch_nonce)", self.text)
        self.assertIn('run-name: >-', self.text)

    def test_paper_proof_uses_existing_warm_job_and_encrypted_command_gate(self):
        post_auth = self.text.index('name: Materialize canonical post-auth broker and forward-data handoff')
        proof = self.text.index('name: Execute one encrypted MM-authorized selected-runtime paper proof')
        stop = self.text.index('name: Gracefully stop authenticated Gateway before warm-state snapshot')
        self.assertLess(post_auth, proof)
        self.assertLess(proof, stop)
        self.assertIn("if: ${{ github.event_name == 'workflow_dispatch' && inputs.mode == 'paper_submit_proof' }}", self.text)
        self.assertIn('python scripts/ibkr_warm_selected_runtime_activation_v1.py', self.text)
        self.assertIn('--exchange-ref rendezvous-exchange', self.text)
        self.assertIn('GH_TOKEN: ${{ github.token }}', self.text)

    def test_paper_proof_failure_is_reported_only_after_warm_state_persistence(self):
        proof = self.text.index('name: Execute one encrypted MM-authorized selected-runtime paper proof')
        stop = self.text.index('name: Gracefully stop authenticated Gateway before warm-state snapshot')
        seal = self.text.index('name: Seal authenticated Gateway warm state')
        publish = self.text.index('name: Publish reusable encrypted warm state')
        assess = self.text.index('name: Enforce paper proof result after warm-state persistence')
        cleanup = self.text.index('name: Destroy private runtime material')
        self.assertLess(proof, stop)
        self.assertLess(stop, seal)
        self.assertLess(seal, publish)
        self.assertLess(publish, assess)
        self.assertLess(assess, cleanup)
        proof_block = self.text[proof:stop]
        self.assertIn('id: paper_proof', proof_block)
        self.assertIn('continue-on-error: true', proof_block)
        self.assertIn('steps.paper_proof.outcome', self.text[assess:cleanup])
        self.assertIn('IBKR_WARM_SELECTED_RUNTIME_PAPER_PROOF_ACCEPTED=0', self.text[assess:cleanup])

    def test_broker_job_write_permission_is_scoped_to_same_job_and_live_stays_disabled(self):
        broker = self.text.index('broker-data-proof:')
        broker_tail = self.text[broker:]
        self.assertIn('permissions:\n      contents: write\n      actions: read\n      id-token: write', broker_tail)
        self.assertIn('IBKR_REMOTE_GLOBAL_CANCEL_CALLED=0', Path('scripts/ibkr_warm_selected_runtime_activation_v1.py').read_text(encoding='utf-8'))
        activator = Path('scripts/ibkr_warm_selected_runtime_activation_v1.py').read_text(encoding='utf-8')
        self.assertIn('"ENABLE_LIVE_TRADING": "0"', activator)
        self.assertIn('"STRATEGY_IBKR_PAPER_GLOBAL_CANCEL_ENABLED_13Z37D": "0"', activator)

    def test_activation_private_material_is_destroyed_with_gateway_runtime(self):
        self.assertIn('docker rm -f mmibkr-warm-selected-runtime-proof', self.text)
        self.assertIn('docker image rm "mmibkr-warm-proof:${GITHUB_RUN_ID}"', self.text)
        self.assertIn('"$RUNNER_TEMP/ibkr-command-private.b64"', self.text)
        self.assertIn('"$RUNNER_TEMP/ibkr-paper-proof-return"', self.text)
        self.assertIn('"$RUNNER_TEMP/mm-ibkr-source"', self.text)


if __name__ == '__main__':
    unittest.main()