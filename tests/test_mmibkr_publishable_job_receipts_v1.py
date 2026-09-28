from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.mmibkr_publishable_job_receipts_v1 import stage


def _sha(node):
    raw=json.dumps(node,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path: Path):
    receipt_dir=tmp_path/"receipts"
    nested=receipt_dir/"receipts"
    nested.mkdir(parents=True)
    output=tmp_path/"public"
    result={"schema":"example","capital_accounting":{"starting_nav":100000,"max_drawdown_pct":12.5}}
    result_sha=_sha(result)
    fp="a"*64
    job={
        "schema":"mmibkr.canonical_workload_receipt.v1",
        "job_id":"w124",
        "job_fingerprint":fp,
        "capability_id":"REGISTRY_BACKTEST",
        "status":"completed",
        "authority":{
            "research_only":True,
            "broker_submit":False,
            "broker_cancel":False,
            "broker_flatten":False,
            "strategy_spec_write":False,
            "runtime_activation":False,
            "promotion_mutation":False,
            "live_trading":False,
        },
        "mmibkr":{"commit":"b"*40},
        "entrypoint":{"path":"strategy_backtest_registry.py"},
        "resources":{"max_wall_seconds":1200,"max_output_bytes":3000000},
        "result_sha256":result_sha,
        "result":result,
    }
    (nested/f"{fp}.json").write_text(json.dumps(job),encoding="utf-8")
    session={
        "schema":"mmibkr.canonical_session_receipt.v1",
        "session_id":"session-1",
        "session_fingerprint":"c"*64,
        "status":"completed",
        "jobs":{"w124":{
            "state":"completed",
            "job_fingerprint":fp,
            "result_sha256":result_sha,
        }},
    }
    terminal=tmp_path/"session-terminal.json"
    terminal.write_text(json.dumps(session),encoding="utf-8")
    return terminal,receipt_dir,output


def test_stage_publishes_exact_sanitized_job_receipt_and_manifest(tmp_path,capsys):
    terminal,receipt_dir,output=_fixture(tmp_path)
    manifest=stage(terminal,receipt_dir,output)

    assert manifest["job_count"]==1
    assert manifest["jobs"][0]["job_id"]=="w124"
    published=json.loads((output/"w124.json").read_text())
    assert published["result"]["capital_accounting"]["starting_nav"]==100000
    assert published["authority"]["broker_submit"] is False
    assert json.loads((output/"manifest.json").read_text())["schema"]=="mmibkr.publishable_canonical_job_receipts.v1"
    stdout=capsys.readouterr().out
    assert "MMIBKR_CANONICAL_JOB_RECEIPT_BEGIN=w124" in stdout
    assert "MMIBKR_CANONICAL_JOB_RECEIPT_END=w124" in stdout


def test_stage_rejects_authority_escalation(tmp_path):
    terminal,receipt_dir,output=_fixture(tmp_path)
    path=receipt_dir/"receipts"/(("a"*64)+".json")
    job=json.loads(path.read_text())
    job["authority"]["runtime_activation"]=True
    path.write_text(json.dumps(job),encoding="utf-8")
    with pytest.raises(ValueError,match="authority escalation"):
        stage(terminal,receipt_dir,output)


def test_stage_rejects_session_job_result_digest_mismatch(tmp_path):
    terminal,receipt_dir,output=_fixture(tmp_path)
    session=json.loads(terminal.read_text())
    session["jobs"]["w124"]["result_sha256"]="d"*64
    terminal.write_text(json.dumps(session),encoding="utf-8")
    with pytest.raises(ValueError,match="session/job result digest mismatch"):
        stage(terminal,receipt_dir,output)
