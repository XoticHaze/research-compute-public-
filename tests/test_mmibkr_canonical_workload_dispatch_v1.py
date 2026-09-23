from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalWorkloadDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()
        module = self.source_root / "autotuner_strategy_bridge.py"
        module.write_text(
            "import hashlib, json\n"
            "def normalize_strategy_spec(payload):\n"
            "    spec=dict(payload)\n"
            "    strategy_id=str(spec.get('strategy_id') or '').strip()\n"
            "    symbol=str(spec.get('symbol') or '').strip().upper()\n"
            "    timeframe=str(spec.get('timeframe') or '').strip()\n"
            "    if not strategy_id or not symbol or not timeframe:\n"
            "        raise ValueError('missing StrategySpec identity')\n"
            "    spec['strategy_id']=strategy_id; spec['symbol']=symbol; spec['timeframe']=timeframe\n"
            "    spec['parameters']=dict(spec.get('parameters') or {})\n"
            "    raw=json.dumps(spec,sort_keys=True,separators=(',',':')).encode()\n"
            "    return {'strategy_spec':spec,'strategy_spec_digest':hashlib.sha256(raw).hexdigest(),'source_payload':payload}\n",
            encoding="utf-8",
        )
        self.entry_blob = git_blob_sha1(module.read_bytes())
        self.commit = "a" * 40
        self.archive_sha = "b" * 64
        self.source_receipt = {
            "schema": mod.SOURCE_RECEIPT_SCHEMA,
            "mmibkr_repository": mod.SOURCE_REPOSITORY,
            "requested_source_ref": self.commit,
            "mmibkr_head": self.commit,
            "source_archive_sha256": self.archive_sha,
            "source_root": str(self.source_root.resolve()),
            "broker_credentials_materialized": False,
            "tws_credentials_required": False,
            "source_token_emitted": False,
            "paper_or_live_authority": False,
        }

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self, job_id: str, symbol: str = "mnq") -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": job_id,
            "capability_id": "STRATEGY_SPEC_VALIDATE",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive_sha,
            },
            "entrypoint": {
                "path": "autotuner_strategy_bridge.py",
                "module": "autotuner_strategy_bridge",
                "callable": "normalize_strategy_spec",
                "git_blob_sha1": self.entry_blob,
            },
            "arguments": {
                "strategy_spec": {
                    "strategy_id": "crw_score_multi_mode",
                    "symbol": symbol,
                    "timeframe": "12Min",
                    "parameters": {"ENTRY_EXTREME": -2.8},
                }
            },
            "resources": {"max_wall_seconds": 30, "max_output_bytes": 100_000},
            "authority": "research_only",
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_strategy_spec_validate_emits_sanitized_fail_closed_receipt(self):
        result = mod.execute_request(
            self.request("job-one"),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
        )
        receipt = result["receipt"]
        self.assertFalse(result["cache_hit"])
        self.assertEqual(receipt["schema"], mod.RECEIPT_SCHEMA)
        self.assertEqual(receipt["result"]["strategy_spec"]["symbol"], "MNQ")
        self.assertRegex(receipt["result"]["strategy_spec_digest"], r"^[0-9a-f]{64}$")
        self.assertNotIn("source_payload", receipt["result"])
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertIs(receipt["authority"][key], False)

    def test_unknown_capability_and_entrypoint_drift_fail_closed(self):
        unknown = self.request("job-unknown")
        unknown["capability_id"] = "SHELL"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "not allowlisted"):
            mod.execute_request(unknown, source_root=self.source_root, source_receipt=self.source_receipt)

        drift = self.request("job-drift")
        drift["entrypoint"]["git_blob_sha1"] = "c" * 40
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "blob mismatch"):
            mod.execute_request(drift, source_root=self.source_root, source_receipt=self.source_receipt)

    def test_source_receipt_authority_or_identity_drift_fails_closed(self):
        bad = dict(self.source_receipt)
        bad["paper_or_live_authority"] = True
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "paper_or_live_authority=false"):
            mod.execute_request(self.request("job-auth"), source_root=self.source_root, source_receipt=bad)

        bad = dict(self.source_receipt)
        bad["mmibkr_head"] = "c" * 40
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "commit mismatch"):
            mod.execute_request(self.request("job-source"), source_root=self.source_root, source_receipt=bad)

    def test_content_addressed_receipt_reuse_skips_duplicate_work(self):
        receipt_dir = self.root / "runtime-state"
        first = mod.execute_request(
            self.request("job-cache"),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            receipt_dir=receipt_dir,
        )
        second = mod.execute_request(
            self.request("job-cache"),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            receipt_dir=receipt_dir,
        )
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["receipt"], second["receipt"])

    def test_plan_fans_out_independent_jobs_then_joins_dependency(self):
        plan = {
            "schema": mod.PLAN_SCHEMA,
            "plan_id": "plan-one",
            "max_parallel": 2,
            "jobs": [
                {"job_id": "a", "depends_on": [], "request": self.request("a", "MNQ")},
                {"job_id": "b", "depends_on": [], "request": self.request("b", "APH")},
                {"job_id": "c", "depends_on": ["a", "b"], "request": self.request("c", "AMAT")},
            ],
        }
        result = mod.execute_plan(
            plan,
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            receipt_dir=self.root / "plan-state",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["waves"], [["a", "b"], ["c"]])
        self.assertTrue(all(row["state"] == "completed" for row in result["jobs"].values()))
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertIs(result["authority"][key], False)

        rerun = mod.execute_plan(
            plan,
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            receipt_dir=self.root / "plan-state",
        )
        self.assertEqual(rerun["status"], "completed")
        self.assertTrue(all(row["state"] == "cached" for row in rerun["jobs"].values()))

    def test_plan_cycles_are_rejected_before_execution(self):
        plan = {
            "schema": mod.PLAN_SCHEMA,
            "plan_id": "cycle",
            "max_parallel": 2,
            "jobs": [
                {"job_id": "a", "depends_on": ["b"], "request": self.request("a")},
                {"job_id": "b", "depends_on": ["a"], "request": self.request("b")},
            ],
        }
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "cycle"):
            mod.validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
