from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalDataMaterializeDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        operator = self.source_root / "scripts" / "operator"
        operator.mkdir(parents=True)
        (self.source_root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        (operator / "__init__.py").write_text("", encoding="utf-8")
        module = operator / "canonical_data_materialize_v1.py"
        module.write_text(
            "import hashlib,json\n"
            "from pathlib import Path\n"
            "def materialize_snapshot(payload, data_root):\n"
            "    root=Path(data_root); root.mkdir(parents=True,exist_ok=True)\n"
            "    out=root/'stocks'/'AMAT'/'15Min.csv'; out.parent.mkdir(parents=True,exist_ok=True)\n"
            "    out.write_text('timestamp,open,high,low,close,volume\\n2026-09-22T15:00:00Z,1,2,0,1,10\\n',encoding='utf-8')\n"
            "    raw=out.read_bytes(); rel=out.relative_to(root).as_posix()\n"
            "    artifacts=[{'relative_path':rel,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]\n"
            "    manifest_hash=hashlib.sha256(json.dumps(artifacts,sort_keys=True,separators=(',',':')).encode()).hexdigest()\n"
            "    return {'schema':'mmibkr.canonical_data_materialize_result.v1','ok':True,'dataset_count':1,'artifact_count':1,'artifacts':artifacts,'artifact_manifest_sha256':manifest_hash,'broker_request_made':False,'boundaries':{'broker_action':False,'order_submission':False,'cancel':False,'flatten':False,'live_trading':False,'strategy_spec_mutation':False,'runtime_authority':False,'promotion_mutation':False}}\n",
            encoding="utf-8",
        )
        self.entry_blob = git_blob_sha1(module.read_bytes())
        self.commit = "a" * 40
        self.archive = "b" * 64
        self.source_receipt = {
            "schema": mod.SOURCE_RECEIPT_SCHEMA,
            "mmibkr_repository": mod.SOURCE_REPOSITORY,
            "requested_source_ref": self.commit,
            "mmibkr_head": self.commit,
            "source_archive_sha256": self.archive,
            "source_root": str(self.source_root.resolve()),
            "broker_credentials_materialized": False,
            "tws_credentials_required": False,
            "source_token_emitted": False,
            "paper_or_live_authority": False,
        }
        self.input_root = self.root / "inputs"
        self.input_root.mkdir()
        self.snapshot = self.input_root / "snapshot.json"
        self.snapshot.write_text(
            json.dumps(
                {
                    "schema": "mmibkr.canonical_data_materialize_request.v1",
                    "authority": "readonly_market_data",
                    "source": {
                        "provider": "fixture",
                        "observation_id": "one",
                        "observed_at": "2026-09-22T15:00:00Z",
                        "provenance_sha256": "c" * 64,
                    },
                    "boundaries": {
                        "broker_action": False,
                        "order_submission": False,
                        "cancel": False,
                        "flatten": False,
                        "live_trading": False,
                        "strategy_spec_mutation": False,
                        "runtime_authority": False,
                        "promotion_mutation": False,
                    },
                    "datasets": [],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self) -> dict:
        raw = self.snapshot.read_bytes()
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "data-one",
            "capability_id": "CANONICAL_DATA_MATERIALIZE",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": "scripts/operator/canonical_data_materialize_v1.py",
                "module": "scripts.operator.canonical_data_materialize_v1",
                "callable": "materialize_snapshot",
                "git_blob_sha1": self.entry_blob,
            },
            "arguments": {
                "snapshot": {
                    "relative_path": "snapshot.json",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                }
            },
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 200000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_materialization_is_hash_bound_content_addressed_and_sanitized(self):
        out = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )
        self.assertFalse(out["cache_hit"])
        receipt = out["receipt"]
        result = receipt["result"]
        self.assertEqual(receipt["capability_id"], "CANONICAL_DATA_MATERIALIZE")
        self.assertEqual(result["dataset_count"], 1)
        self.assertEqual(result["artifact_count"], 2)
        self.assertFalse(result["broker_request_made"])
        self.assertNotIn("AMAT", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.assertRegex(result["artifact_ref"], r"^[0-9a-f]{64}$")
        artifact_root = (
            self.receipt_dir
            / "artifacts"
            / "materialized"
            / result["artifact_ref"]
        )
        self.assertTrue((artifact_root / "stocks/AMAT/15Min.csv").is_file())
        self.assertTrue((artifact_root / "materialization_manifest.json").is_file())
        manifest = json.loads(
            (artifact_root / "materialization_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["source_input"]["sha256"], result["source_input_sha256"])
        self.assertFalse(manifest["broker_request_made"])
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(receipt["authority"][key])

        second = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["receipt"], receipt)

        # Crash-window recovery: artifact publication may precede receipt publication.
        # Removing only the completed receipt must recover from the verified content store
        # without rerunning the canonical materializer or mutating the artifact.
        data_path = artifact_root / "stocks/AMAT/15Min.csv"
        before_mtime = data_path.stat().st_mtime_ns
        receipt_path = self.receipt_dir / "receipts" / f"{result['artifact_ref']}.json"
        receipt_path.unlink()
        recovered = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )
        self.assertFalse(recovered["cache_hit"])
        self.assertEqual(recovered["receipt"]["result"], result)
        self.assertEqual(data_path.stat().st_mtime_ns, before_mtime)

    def test_corrupt_content_addressed_artifact_fails_closed_on_receipt_recovery(self):
        first = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )
        result = first["receipt"]["result"]
        artifact_root = self.receipt_dir / "artifacts" / "materialized" / result["artifact_ref"]
        receipt_path = self.receipt_dir / "receipts" / f"{result['artifact_ref']}.json"
        receipt_path.unlink()
        (artifact_root / "stocks/AMAT/15Min.csv").write_text("corrupt\n", encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "artifact identity mismatch"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=self.receipt_dir,
            )

    def test_snapshot_digest_and_path_traversal_fail_before_owner_execution(self):
        req = self.request()
        req["arguments"]["snapshot"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=self.receipt_dir,
            )

        req = self.request()
        req["arguments"]["snapshot"]["relative_path"] = "../snapshot.json"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "relative_path rejected"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=self.receipt_dir,
            )

    def test_materialization_requires_receipt_backed_artifact_store(self):
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "requires receipt_dir"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_entrypoint_drift_fails_closed(self):
        req = self.request()
        req["entrypoint"]["git_blob_sha1"] = "e" * 40
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "blob mismatch"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=self.receipt_dir,
            )


if __name__ == "__main__":
    unittest.main()
