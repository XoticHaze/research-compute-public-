"""Fail closed on public identifier injection after the selected publisher allowlist."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

import pytest

from scripts.mmibkr_publishable_job_receipts_v1 import stage
from tests.test_mmibkr_publishable_job_receipts_v1 import PublishableCanonicalJobReceiptTests


FIXTURE = PublishableCanonicalJobReceiptTests()


def _inject_private_ids(root: Path, *, capability: str = "REGISTRY_BACKTEST"):
    terminal, receipt_dir, output = FIXTURE._fixture(root)
    private_job = "PRIVATE_JOB_SENTINEL_NESTED_20261010"
    private_session = "PRIVATE_SESSION_SENTINEL_NESTED_20261010"
    receipt_path = receipt_dir / "receipts" / ("a" * 64 + ".json")
    job = json.loads(receipt_path.read_text())
    job["job_id"] = private_job
    job["capability_id"] = capability
    job["mmibkr"]["private_source"] = "PRIVATE_SOURCE_SENTINEL_NESTED_20261010"
    receipt_path.write_text(json.dumps(job))
    session = json.loads(terminal.read_text())
    state = session["jobs"].pop("w124")
    session["jobs"][private_job] = state
    session["session_id"] = private_session
    terminal.write_text(json.dumps(session))
    return terminal, receipt_dir, output


def test_private_job_and_session_identifiers_never_cross_public_projection():
    with tempfile.TemporaryDirectory() as tmp:
        terminal, receipts, output = _inject_private_ids(Path(tmp))
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            manifest = stage(terminal, receipts, output)
        published = "\n".join([stream.getvalue(), json.dumps(manifest)] +
                              [p.name + p.read_text() for p in output.iterdir()])
        for sentinel in ("PRIVATE_JOB_SENTINEL", "PRIVATE_SESSION_SENTINEL", "PRIVATE_SOURCE_SENTINEL"):
            assert sentinel not in published
        assert manifest["jobs"][0]["job_id"] == "job-" + "a" * 64
        assert manifest["session_id"] == "session-" + "c" * 64
        assert (output / ("job-" + "a" * 64 + ".json")).is_file()


def test_capability_id_is_fixed_registry_member_not_freeform_public_identifier():
    with tempfile.TemporaryDirectory() as tmp:
        terminal, receipts, output = _inject_private_ids(Path(tmp), capability="PRIVATE_CAPABILITY_SENTINEL")
        with pytest.raises(ValueError, match="canonical job capability identity invalid") as exc:
            stage(terminal, receipts, output)
        assert "PRIVATE_CAPABILITY_SENTINEL" not in str(exc.value)
        assert not list(output.glob("*.json"))


def test_malformed_session_fingerprint_rejected_before_public_write():
    with tempfile.TemporaryDirectory() as tmp:
        terminal, receipts, output = _inject_private_ids(Path(tmp))
        session = json.loads(terminal.read_text())
        session["session_fingerprint"] = "PRIVATE_SESSION_FINGERPRINT_SENTINEL"
        terminal.write_text(json.dumps(session))
        with pytest.raises(ValueError, match="session fingerprint invalid") as exc:
            stage(terminal, receipts, output)
        assert "PRIVATE_SESSION_FINGERPRINT_SENTINEL" not in str(exc.value)
        assert not list(output.glob("*.json"))


def test_duplicate_job_fingerprint_rejected_before_public_collision():
    with tempfile.TemporaryDirectory() as tmp:
        terminal, receipts, output = _inject_private_ids(Path(tmp))
        session = json.loads(terminal.read_text())
        first = next(iter(session["jobs"]))
        session["jobs"]["PRIVATE_OTHER_JOB_SENTINEL"] = dict(session["jobs"][first])
        terminal.write_text(json.dumps(session))
        with pytest.raises(ValueError, match="identity mismatch|duplicate public job fingerprint") as exc:
            stage(terminal, receipts, output)
        assert "PRIVATE_OTHER_JOB_SENTINEL" not in str(exc.value)


def test_error_does_not_echo_private_job_id_or_source_path():
    with tempfile.TemporaryDirectory() as tmp:
        terminal, receipts, output = _inject_private_ids(Path(tmp))
        path = receipts / "receipts" / ("a" * 64 + ".json")
        path.write_text("[]")
        with pytest.raises(ValueError, match="canonical JSON root must be object") as exc:
            stage(terminal, receipts, output)
        assert "PRIVATE_" not in str(exc.value)
        assert str(path) not in str(exc.value)
