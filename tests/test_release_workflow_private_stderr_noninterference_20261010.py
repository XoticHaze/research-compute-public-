"""Synthetic public Actions runner-log noninterference for the selected workflow."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile


def test_canonical_session_runner_stderr_redirected_and_private_temp_removed():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / '.github/workflows/mmibkr-canonical-research-session-bau-r1.yml').read_text()
    assert '> "$RUNNER_TEMP/session-terminal.json" \\\n            2> "$RUNNER_TEMP/session-runner-private-stderr.log"' in workflow
    assert '"$RUNNER_TEMP/session-runner-private-stderr.log" "$RUNNER_TEMP/terminal-receipt.json"' in workflow
    # No private runner stderr should be in the two declared public artifact roots.
    assert 'path: ${{ runner.temp }}/public-job-receipts' not in workflow or \
        'session-runner-private-stderr.log' not in workflow.split('path: ${{ runner.temp }}/public-job-receipts')[1].split('if-no-files-found:')[0]
    with tempfile.TemporaryDirectory() as td:
        code = 'import sys; sys.stderr.write("PRIVATE_NESTED_ERROR_SENTINEL\\n"); sys.exit(7)'
        shell = '''set +e
python -c "$TEST_PYTHON" > "$RUNNER_TEMP/session-terminal.json" 2> "$RUNNER_TEMP/session-runner-private-stderr.log"
rc=$?
set -e
if [ "$rc" -ne 0 ]; then echo 'CANONICAL_SESSION_FAILED'; fi
rm -f "$RUNNER_TEMP/session-terminal.json" "$RUNNER_TEMP/session-runner-private-stderr.log"
exit 0'''
        env = dict(os.environ, RUNNER_TEMP=td, TEST_PYTHON=code)
        result = subprocess.run(['bash', '-c', shell], env=env, capture_output=True, text=True, check=True)
        assert result.stdout.strip() == 'CANONICAL_SESSION_FAILED'
        assert 'PRIVATE_' not in result.stdout + result.stderr
        assert not (Path(td) / 'session-runner-private-stderr.log').exists()
