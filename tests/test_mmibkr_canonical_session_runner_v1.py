from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_session_runner_v1 as session_mod
from scripts import mmibkr_canonical_workload_dispatch_v1 as dispatch


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalSessionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()
        module = self.source_root / "autotuner_strategy_bridge.py"
        module.write_text(
            "import hashlib,json\n"
            "def normalize_strategy_spec(payload):\n"
            "    spec=dict(payload)\n"
            "    spec['symbol']=str(spec.get('symbol') or '').upper()\n"
            "    raw=json.dumps(spec,sort_keys=True,separators=(',',':')).encode()\n"
            "    return {'strategy_spec':spec,'strategy_spec_digest':hashlib.sha256(raw).hexdigest(),'source_payload':payload}\n",
            encoding="utf-8",
        )
        self.entry_blob = git_blob_sha1(module.read_bytes())
        self.commit = "a" * 40
        self.archive = "b" * 64
        self.source_receipt = {
            "schema": dispatch.SOURCE_RECEIPT_SCHEMA,
            "mmibkr_repository": dispatch.SOURCE_REPOSITORY,
            "requested_source_ref": self.commit,
            "mmibkr_head": self.commit,
            "source_archive_sha256": self.archive,
            "source_root": str(self.source_root.resolve()),
            "broker_credentials_materialized": False,
            "tws_credentials_required": False,
            "source_token_emitted": False,
            "paper_or_live_authority": False,
        }
        self.source_receipt_path = self.root / "source-receipt.json"
        self.source_receipt_path.write_text(
            json.dumps(self.source_receipt, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self, job_id: str, symbol: str, max_wall_seconds: int = 5) -> dict:
        return {
            "schema": dispatch.REQUEST_SCHEMA,
            "job_id": job_id,
            "capability_id": "STRATEGY_SPEC_VALIDATE",
            "mmibkr": {
                "repository": dispatch.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
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
                    "parameters": {},
                }
            },
            "resources": {
                "max_wall_seconds": max_wall_seconds,
                "max_output_bytes": 100_000,
            },
            "authority": dispatch.AUTHORITY,
            "forbidden_authorities": dict(dispatch.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_priority_order_and_dependency_join_are_deterministic(self):
        node = {
            "schema": session_mod.SESSION_SCHEMA,
            "session_id": "session-priority",
            "budget_seconds": 30,
            "reserve_seconds": 1,
            "max_parallel": 1,
            "jobs": [
                {
                    "job_id": "low",
                    "priority": 10,
                    "depends_on": [],
                    "request": self.request("low", "AMAT"),
                },
                {
                    "job_id": "high",
                    "priority": 100,
                    "depends_on": [],
                    "request": self.request("high", "MNQ"),
                },
                {
                    "job_id": "join",
                    "priority": 90,
                    "depends_on": ["high"],
                    "request": self.request("join", "APH"),
                },
            ],
        }
        result = session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            [[row["job_id"] for row in wave["jobs"]] for wave in result["waves"]],
            [["high"], ["join"], ["low"]],
        )
        self.assertTrue(
            all(
                row["state"] in {"completed", "cached"}
                for row in result["jobs"].values()
            )
        )
        for key in dispatch.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(result["authority"][key])

    def test_budget_defers_work_that_cannot_fit_without_starting_it(self):
        node = {
            "schema": session_mod.SESSION_SCHEMA,
            "session_id": "session-budget",
            "budget_seconds": 10,
            "reserve_seconds": 1,
            "max_parallel": 2,
            "jobs": [
                {
                    "job_id": "too-large",
                    "priority": 100,
                    "depends_on": [],
                    "request": self.request("too-large", "MNQ", max_wall_seconds=20),
                }
            ],
        }
        result = session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(result["status"], "budget_exhausted")
        row = result["jobs"]["too-large"]
        self.assertEqual(row["state"], "deferred_budget")
        self.assertEqual(row["required_wall_seconds"], 20)
        self.assertEqual(result["waves"], [])

    def test_same_session_fingerprint_resumes_without_duplicate_waves(self):
        node = {
            "schema": session_mod.SESSION_SCHEMA,
            "session_id": "session-resume",
            "budget_seconds": 20,
            "reserve_seconds": 1,
            "max_parallel": 2,
            "jobs": [
                {
                    "job_id": "a",
                    "priority": 10,
                    "depends_on": [],
                    "request": self.request("a", "MNQ"),
                },
                {
                    "job_id": "b",
                    "priority": 10,
                    "depends_on": [],
                    "request": self.request("b", "APH"),
                },
            ],
        }
        first = session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
        )
        second = session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
        )
        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["waves"], first["waves"])
        self.assertEqual(second["jobs"], first["jobs"])

    def external_dependency(self, raw: bytes, relative_path: str = "incoming/private-input.bin") -> dict:
        return {
            "scope": "input_root",
            "relative_path": relative_path,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "producer": {
                "mechanism": "source_exchange",
                "identity": "mmibkr-private-input-producer",
                "trigger": "rendezvous/fire/mmibkr-private-input-r1",
            },
        }

    def test_missing_external_artifact_is_explicit_wait_without_dispatch(self):
        raw = b"governed-private-input"
        node = {
            "schema": session_mod.SESSION_SCHEMA,
            "session_id": "session-external-wait",
            "budget_seconds": 20,
            "reserve_seconds": 1,
            "max_parallel": 1,
            "jobs": [
                {
                    "job_id": "consumer",
                    "priority": 100,
                    "depends_on": [],
                    "external_artifact_dependency": self.external_dependency(raw),
                    "request": self.request("consumer", "MNQ"),
                }
            ],
        }
        input_root = self.root / "governed-input"
        input_root.mkdir()
        result = session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
            input_root=input_root,
        )
        self.assertEqual(result["status"], "awaiting_external_artifact")
        row = result["jobs"]["consumer"]
        self.assertEqual(row["state"], "awaiting_external_artifact")
        self.assertEqual(row["reason"], "artifact_missing")
        self.assertEqual(
            row["external_artifact_dependency"]["producer"]["mechanism"],
            "source_exchange",
        )
        self.assertEqual(result["waves"], [])
        self.assertFalse(
            (self.receipt_dir / "session-inputs" / "session-external-wait" / "consumer.json").exists()
        )

    def test_same_session_resumes_after_exact_external_artifact_arrives(self):
        raw = b"governed-private-input"
        node = {
            "schema": session_mod.SESSION_SCHEMA,
            "session_id": "session-external-resume",
            "budget_seconds": 20,
            "reserve_seconds": 1,
            "max_parallel": 1,
            "jobs": [
                {
                    "job_id": "consumer",
                    "priority": 100,
                    "depends_on": [],
                    "external_artifact_dependency": self.external_dependency(raw),
                    "request": self.request("consumer", "MNQ"),
                }
            ],
        }
        input_root = self.root / "governed-input-resume"
        input_root.mkdir()
        first = session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
            input_root=input_root,
        )
        self.assertEqual(first["status"], "awaiting_external_artifact")

        target = input_root / "incoming" / "private-input.bin"
        target.parent.mkdir(parents=True)
        target.write_bytes(raw)
        second = session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
            input_root=input_root,
        )
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["jobs"]["consumer"]["state"], "completed")
        self.assertEqual(
            [[row["job_id"] for row in wave["jobs"]] for wave in second["waves"]],
            [["consumer"]],
        )
        self.assertGreater(second["started_at_epoch"], first["started_at_epoch"])

    def test_present_external_artifact_with_wrong_identity_fails_closed(self):
        raw = b"governed-private-input"
        node = {
            "schema": session_mod.SESSION_SCHEMA,
            "session_id": "session-external-tamper",
            "budget_seconds": 20,
            "reserve_seconds": 1,
            "max_parallel": 1,
            "jobs": [
                {
                    "job_id": "consumer",
                    "priority": 100,
                    "depends_on": [],
                    "external_artifact_dependency": self.external_dependency(raw),
                    "request": self.request("consumer", "MNQ"),
                }
            ],
        }
        input_root = self.root / "governed-input-tamper"
        target = input_root / "incoming" / "private-input.bin"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"governed-private-inpuX")
        result = session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
            input_root=input_root,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            result["jobs"]["consumer"]["error_class"],
            "external_artifact_sha256_mismatch",
        )
        self.assertEqual(result["waves"], [])

    def test_external_artifact_dependency_rejects_path_escape(self):
        raw = b"x"
        node = {
            "schema": session_mod.SESSION_SCHEMA,
            "session_id": "session-external-path",
            "budget_seconds": 20,
            "reserve_seconds": 1,
            "max_parallel": 1,
            "jobs": [
                {
                    "job_id": "consumer",
                    "priority": 100,
                    "depends_on": [],
                    "external_artifact_dependency": self.external_dependency(
                        raw,
                        "../escape.bin",
                    ),
                    "request": self.request("consumer", "MNQ"),
                }
            ],
        }
        with self.assertRaisesRegex(
            session_mod.CanonicalSessionError,
            "relative_path rejected",
        ):
            session_mod.validate_session(node)

    def test_session_id_cannot_be_reused_for_different_plan(self):
        node = {
            "schema": session_mod.SESSION_SCHEMA,
            "session_id": "session-identity",
            "budget_seconds": 20,
            "reserve_seconds": 1,
            "max_parallel": 1,
            "jobs": [
                {
                    "job_id": "a",
                    "priority": 10,
                    "depends_on": [],
                    "request": self.request("a", "MNQ"),
                }
            ],
        }
        session_mod.execute_session(
            node,
            source_root=self.source_root,
            source_receipt_path=self.source_receipt_path,
            receipt_dir=self.receipt_dir,
        )
        changed = json.loads(json.dumps(node))
        changed["jobs"][0]["priority"] = 99
        with self.assertRaisesRegex(session_mod.CanonicalSessionError, "different fingerprint"):
            session_mod.execute_session(
                changed,
                source_root=self.source_root,
                source_receipt_path=self.source_receipt_path,
                receipt_dir=self.receipt_dir,
            )


if __name__ == "__main__":
    unittest.main()
