"""Run the selected workflow's public-terminal projection against private ID sentinels."""
from __future__ import annotations

import json
from pathlib import Path


def _projection_code():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/mmibkr-canonical-research-session-bau-r1.yml").read_text()
    marker = "          # Public terminal must use the same digest-only identifiers"
    start = workflow.index(marker)
    end = workflow.index("          outer=(root/'outer-job-sha256.txt')", start)
    lines = workflow[start:end].splitlines()
    return "\n".join(line[10:] for line in lines) + "\n"


def test_workflow_terminal_public_ids_are_digest_only():
    code = _projection_code()
    compile(code, "selected_workflow_public_projection", "exec")
    node = {
        "schema": "mmibkr.canonical_session_receipt.v1",
        "session_id": "PRIVATE_SESSION_SENTINEL",
        "session_fingerprint": "c" * 64,
        "status": "completed",
        "jobs": {
            "PRIVATE_JOB_SENTINEL": {
                "state": "completed",
                "job_fingerprint": "a" * 64,
                "result_sha256": "b" * 64,
                "cache_hit": False,
                "private_parameters": "PRIVATE_NESTED_SENTINEL",
            }
        },
    }
    env = {"node": node}
    exec(code, env)
    published = json.dumps(env["safe_session"], sort_keys=True)
    assert "PRIVATE_" not in published
    assert env["safe_session"]["session_id"] == "session-" + "c" * 64
    assert list(env["safe_session"]["jobs"]) == ["job-" + "a" * 64]


def test_workflow_terminal_rejects_duplicate_public_fingerprints():
    code = _projection_code()
    node = {
        "schema": "mmibkr.canonical_session_receipt.v1",
        "session_id": "PRIVATE_SESSION_SENTINEL",
        "session_fingerprint": "c" * 64,
        "status": "completed",
        "jobs": {
            "PRIVATE_JOB_1": {"state": "completed", "job_fingerprint": "a" * 64},
            "PRIVATE_JOB_2": {"state": "completed", "job_fingerprint": "a" * 64},
        },
    }
    try:
        exec(code, {"node": node})
    except SystemExit as exc:
        assert "duplicate public job fingerprint rejected" in str(exc)
        assert "PRIVATE_" not in str(exc)
    else:
        raise AssertionError("duplicate public fingerprint accepted")
