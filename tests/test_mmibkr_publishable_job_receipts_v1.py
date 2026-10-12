from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.mmibkr_publishable_job_receipts_v1 import stage


def _sha(node):
    raw=json.dumps(node,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class PublishableCanonicalJobReceiptTests(unittest.TestCase):
    def _fixture(self, root: Path):
        receipt_dir=root/"receipts"
        nested=receipt_dir/"receipts"
        nested.mkdir(parents=True)
        output=root/"public"
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
        terminal=root/"session-terminal.json"
        terminal.write_text(json.dumps(session),encoding="utf-8")
        return terminal,receipt_dir,output

    def test_stage_fails_closed_before_public_receipt_artifact_or_log(self):
        with tempfile.TemporaryDirectory() as td:
            terminal,receipt_dir,output=self._fixture(Path(td))
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):
                with self.assertRaisesRegex(RuntimeError, "two_sided_private_result_return_not_admitted"):
                    stage(terminal,receipt_dir,output)
            self.assertFalse(output.exists())
            self.assertNotIn("capital_accounting", stream.getvalue())
            self.assertNotIn("w124", stream.getvalue())

    def test_stage_rejects_authority_escalation(self):
        with tempfile.TemporaryDirectory() as td:
            terminal,receipt_dir,output=self._fixture(Path(td))
            path=receipt_dir/"receipts"/(("a"*64)+".json")
            job=json.loads(path.read_text())
            job["authority"]["runtime_activation"]=True
            path.write_text(json.dumps(job),encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError,"two_sided_private_result_return_not_admitted"):
                stage(terminal,receipt_dir,output)

    def test_stage_rejects_session_job_result_digest_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            terminal,receipt_dir,output=self._fixture(Path(td))
            session=json.loads(terminal.read_text())
            session["jobs"]["w124"]["result_sha256"]="d"*64
            terminal.write_text(json.dumps(session),encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError,"two_sided_private_result_return_not_admitted"):
                stage(terminal,receipt_dir,output)


if __name__=="__main__":
    unittest.main()
