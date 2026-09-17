from pathlib import Path

workflow = Path('.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml')
text = workflow.read_text(encoding='utf-8')
old = """      - name: Execute one encrypted MM-authorized selected-runtime paper proof
        if: ${{ github.event_name == 'workflow_dispatch' && inputs.mode == 'paper_submit_proof' }}
        env:
"""
new = """      - name: Execute one encrypted MM-authorized selected-runtime paper proof
        id: paper_proof
        if: ${{ github.event_name == 'workflow_dispatch' && inputs.mode == 'paper_submit_proof' }}
        continue-on-error: true
        env:
"""
if text.count(old) != 1:
    raise SystemExit('paper proof step header target count mismatch')
text = text.replace(old, new, 1)

anchor = """      - name: Destroy private runtime material
        if: always()
"""
assessment = """      - name: Enforce paper proof result after warm-state persistence
        if: ${{ always() && env.IBKR_PAPER_PROOF_MODE == '1' }}
        run: |
          set -euo pipefail
          if [ \"${{ steps.paper_proof.outcome }}\" != \"success\" ]; then
            echo 'IBKR_WARM_SELECTED_RUNTIME_PAPER_PROOF_ACCEPTED=0'
            echo 'Paper proof failed or was blocked; Gateway was stopped and warm state was resealed before surfacing this failure.'
            exit 52
          fi
          echo 'IBKR_WARM_SELECTED_RUNTIME_PAPER_PROOF_ACCEPTED=1'

      - name: Destroy private runtime material
        if: always()
"""
if text.count(anchor) != 1:
    raise SystemExit('cleanup anchor target count mismatch')
text = text.replace(anchor, assessment, 1)
workflow.write_text(text, encoding='utf-8')

test_path = Path('tests/test_ibkr_b1_warm_state_workflow_v2.py')
tests = test_path.read_text(encoding='utf-8')
test_anchor = """    def test_broker_job_write_permission_is_scoped_to_same_job_and_live_stays_disabled(self):
"""
method = """    def test_paper_proof_failure_is_reported_only_after_warm_state_persistence(self):
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

"""
if tests.count(test_anchor) != 1:
    raise SystemExit('test insertion anchor count mismatch')
tests = tests.replace(test_anchor, method + test_anchor, 1)
test_path.write_text(tests, encoding='utf-8')

doc = Path('docs/IBKR_WARM_PAPER_PROOF_ACTIVATION_20260917.md')
d = doc.read_text(encoding='utf-8')
note = """
## Failure ordering guarantee

The paper-proof step is `continue-on-error` only to preserve lifecycle cleanup. A blocked or failed proof is not accepted: the existing Gateway is still gracefully stopped, the clean warm state is resealed and persisted, and only then does a dedicated assessment step fail the job. This prevents a proof failure from degrading the already-proven reusable authentication state.
"""
if '## Failure ordering guarantee' not in d:
    doc.write_text(d.rstrip() + '\n' + note, encoding='utf-8')
