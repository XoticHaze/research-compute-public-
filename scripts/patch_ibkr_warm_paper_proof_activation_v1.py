from __future__ import annotations

from pathlib import Path

WORKFLOW = Path('.github/workflows/ibkr-cloudflare-readonly-b1-r1.yml')
TEST = Path('tests/test_ibkr_b1_warm_state_workflow_v2.py')


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'expected exactly one anchor, found {count}: {old[:120]!r}')
    return text.replace(old, new, 1)


def main() -> None:
    workflow = WORKFLOW.read_text(encoding='utf-8')
    anchor = "      - name: Refuse cold login inside IBKR reset window\n"
    guard = """      - name: Require restored warm state for paper submit proof
        if: env.IBKR_PAPER_PROOF_MODE == '1'
        run: |
          set -euo pipefail
          test \"${{ steps.restore.outputs.restored }}\" = \"1\" || { echo 'paper submit proof requires accepted restored warm state'; exit 43; }
          echo 'IBKR_PAPER_PROOF_WARM_STATE_REQUIRED=1'

"""
    if 'IBKR_PAPER_PROOF_WARM_STATE_REQUIRED=1' not in workflow:
        workflow = replace_once(workflow, anchor, guard + anchor)
    WORKFLOW.write_text(workflow, encoding='utf-8')

    tests = TEST.read_text(encoding='utf-8')
    method = """
    def test_paper_submit_proof_requires_restored_warm_state(self):
        restore = self.text.index('name: Restore encrypted warm Gateway state if available')
        require = self.text.index('name: Require restored warm state for paper submit proof')
        auth = self.text.index('name: Resolve authenticated session boundary')
        self.assertLess(restore, require)
        self.assertLess(require, auth)
        guard = self.text[require:auth]
        self.assertIn("if: env.IBKR_PAPER_PROOF_MODE == '1'", guard)
        self.assertIn('test \"${{ steps.restore.outputs.restored }}\" = \"1\"', guard)
        self.assertIn('IBKR_PAPER_PROOF_WARM_STATE_REQUIRED=1', guard)

"""
    if 'def test_paper_submit_proof_requires_restored_warm_state' not in tests:
        tests = replace_once(tests, "\n\nif __name__ == '__main__':\n", method + "\nif __name__ == '__main__':\n")
    TEST.write_text(tests, encoding='utf-8')
    print('IBKR_WARM_ONLY_MUTATION_GUARD_PATCHED=1')


if __name__ == '__main__':
    main()
