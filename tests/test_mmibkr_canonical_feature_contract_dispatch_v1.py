from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalFeatureContractValidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()
        module = self.source_root / "feature_contract.py"
        module.write_text(
            "import hashlib,json\n"
            "from pathlib import Path\n"
            "def _sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()\n"
            "def read_feature_artifact_sidecar(data_path, *, verify_artifact=True):\n"
            "    p=Path(data_path); side=p.with_suffix(p.suffix+'.manifest.json')\n"
            "    node=json.loads(side.read_text())\n"
            "    if verify_artifact:\n"
            "        art=node['artifact']\n"
            "        if art['filename']!=p.name: raise ValueError('feature sidecar artifact filename mismatch')\n"
            "        if art['size_bytes']!=p.stat().st_size: raise ValueError('feature artifact size mismatch')\n"
            "        if art['sha256']!=_sha(p): raise ValueError('feature artifact content hash mismatch')\n"
            "    return node\n",
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
        self.artifact = self.input_root / "AMAT.15Min.features.csv"
        self.artifact.write_text(
            "timestamp,EMA_20\n2026-09-22T15:00:00Z,210.5\n",
            encoding="utf-8",
        )
        manifest = {
            "contract_version": "feature_manifest.v2",
            "features": [
                {
                    "output_column": "EMA_20",
                    "identity_hash": "1" * 64,
                    "source_timeframe": "15Min",
                    "target_timeframe": "15Min",
                }
            ],
            "source_dataset_identity": {
                "artifact_sha256": hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
                "symbol": "AMAT",
            },
            "symbol_universe": ["AMAT"],
            "source_timeframes": ["15Min"],
            "target_timeframes": ["15Min"],
            "causal": True,
            "generation_identity": "canonical_data_materialize",
            "consumer_identity": "strategy_preview",
            "feature_contract_mode": "canonical",
            "label_target_columns_excluded": ["future_return"],
            "feature_semantic_hash": "2" * 64,
            "manifest_hash": "3" * 64,
        }
        sidecar = {
            "contract_version": "feature_artifact_sidecar.v1",
            "feature_manifest_hash": manifest["manifest_hash"],
            "feature_manifest": manifest,
            "artifact": {
                "filename": self.artifact.name,
                "sha256": hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
                "size_bytes": self.artifact.stat().st_size,
            },
        }
        self.sidecar = self.artifact.with_suffix(self.artifact.suffix + ".manifest.json")
        self.sidecar.write_text(json.dumps(sidecar, sort_keys=True), encoding="utf-8")

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self) -> dict:
        raw = self.artifact.read_bytes()
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "feature-one",
            "capability_id": "FEATURE_CONTRACT_VALIDATE",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": "feature_contract.py",
                "module": "feature_contract",
                "callable": "read_feature_artifact_sidecar",
                "git_blob_sha1": self.entry_blob,
            },
            "arguments": {
                "artifact": {
                    "relative_path": self.artifact.name,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                }
            },
            "resources": {"max_wall_seconds": 30, "max_output_bytes": 100000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_feature_artifact_and_sidecar_are_verified_and_sanitized(self):
        receipt = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
        )["receipt"]
        result = receipt["result"]
        self.assertEqual(receipt["capability_id"], "FEATURE_CONTRACT_VALIDATE")
        self.assertEqual(result["feature_manifest_hash"], "3" * 64)
        self.assertEqual(result["feature_semantic_hash"], "2" * 64)
        self.assertEqual(result["feature_count"], 1)
        self.assertTrue(result["causal"])
        self.assertEqual(result["source_timeframes"], ["15Min"])
        self.assertEqual(result["target_timeframes"], ["15Min"])
        self.assertEqual(result["symbol_universe"], ["AMAT"])
        self.assertRegex(result["source_dataset_identity_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["artifact"]["sha256"], hashlib.sha256(self.artifact.read_bytes()).hexdigest())
        self.assertEqual(result["sidecar"]["sha256"], hashlib.sha256(self.sidecar.read_bytes()).hexdigest())
        self.assertNotIn("source_dataset_identity", result)
        self.assertNotIn(str(self.root), json.dumps(receipt))

    def test_feature_artifact_digest_drift_fails_before_sidecar_validation(self):
        req = self.request()
        req["arguments"]["artifact"]["sha256"] = "4" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_missing_sidecar_fails_closed(self):
        self.sidecar.unlink()
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sidecar missing"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_noncausal_manifest_is_rejected(self):
        node = json.loads(self.sidecar.read_text(encoding="utf-8"))
        node["feature_manifest"]["causal"] = False
        self.sidecar.write_text(json.dumps(node, sort_keys=True), encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "not causal"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_entrypoint_drift_fails_closed(self):
        req = self.request()
        req["entrypoint"]["git_blob_sha1"] = "5" * 40
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "blob mismatch"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )


if __name__ == "__main__":
    unittest.main()
