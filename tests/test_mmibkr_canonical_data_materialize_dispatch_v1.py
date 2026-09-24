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
        self.source_root.mkdir()

        data_manager = self.source_root / "data_manager.py"
        data_manager.write_text(
            "from pathlib import Path\n"
            "import hashlib,json\n"
            "import pandas as pd\n"
            "class DataManager:\n"
            "    def __init__(self, config, ib, sr_engine=None):\n"
            "        self.base=Path(config['DATA_OUTPUT_DIR'])\n"
            "        self.base.mkdir(parents=True,exist_ok=True)\n"
            "    def _dir(self,symbol):\n"
            "        p=self.base/'stocks'/symbol; p.mkdir(parents=True,exist_ok=True); return p\n"
            "    def _path_for(self,asset_type,symbol,tf,features=False):\n"
            "        suffix='.features.csv' if features else '.csv'\n"
            "        return self._dir(symbol)/(tf+suffix)\n"
            "    def _aggregate_path(self,asset_type,symbol):\n"
            "        return self._dir(symbol)/'aggregate.csv'\n"
            "    def _write_frame(self,symbol,tf,frame):\n"
            "        raw=self._path_for('stocks',symbol,tf,False)\n"
            "        feat=self._path_for('stocks',symbol,tf,True)\n"
            "        frame.to_csv(raw,index=False); frame.to_csv(feat,index=False)\n"
            "        digest=hashlib.sha256((symbol+'|'+tf+'|fixture').encode()).hexdigest()\n"
            "        sidecar=feat.with_suffix(feat.suffix+'.manifest.json')\n"
            "        sidecar.write_text(json.dumps({'contract_version':'feature_artifact_sidecar.v1','feature_manifest_hash':digest,'feature_manifest':{'manifest_hash':digest},'artifact':{'filename':feat.name}},sort_keys=True)+'\\n',encoding='utf-8')\n"
            "    def ingest_external_stock_source_bars(self,symbol,source_tf,frame,*,target_timeframes=None,source_origin='external'):\n"
            "        frame=frame.copy()\n"
            "        frame['timestamp']=pd.to_datetime(frame['timestamp'],utc=True)\n"
            "        frame=frame.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)\n"
            "        requested=[]\n"
            "        for tf in [source_tf]+list(target_timeframes or []):\n"
            "            if tf not in requested: requested.append(tf)\n"
            "        frames={}\n"
            "        aggregate=[]\n"
            "        for tf in requested:\n"
            "            node=frame.copy(); node['timeframe']=tf\n"
            "            self._write_frame(symbol,tf,node); frames[tf]=node; aggregate.append(node)\n"
            "        pd.concat(aggregate,ignore_index=True).to_csv(self._aggregate_path('stocks',symbol),index=False)\n"
            "        return {'ok':True,'schema':'mmibkr.data_manager_external_source_ingest.v1','symbol':symbol,'source_timeframe':source_tf,'source_origin':source_origin,'frames':frames,'frame_evidence':[],'broker_request_made':False}\n",
            encoding="utf-8",
        )
        (self.source_root / "feature_contract.py").write_text(
            "FEATURE_MANIFEST_VERSION='feature_manifest.v2'\n",
            encoding="utf-8",
        )
        self.entry_blob = git_blob_sha1(data_manager.read_bytes())
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
        self.dataset = self.input_root / "amat-1min.csv"
        self.dataset.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-09-22T14:31:00Z,101,102,100,101.5,1000\n"
            "2026-09-22T14:30:00Z,100,101,99,100.5,900\n"
            "2026-09-22T14:31:00Z,101,102,100,101.5,1000\n",
            encoding="utf-8",
        )
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self) -> dict:
        raw = self.dataset.read_bytes()
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "data-amat",
            "capability_id": "CANONICAL_DATA_MATERIALIZE",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": "data_manager.py",
                "module": "data_manager",
                "callable": "DataManager",
                "git_blob_sha1": self.entry_blob,
            },
            "arguments": {
                "asset_type": "stocks",
                "symbol": "AMAT",
                "source_timeframe": "1Min",
                "target_timeframes": ["1Min", "15Min"],
                "source_origin": "governed_test_snapshot",
                "dataset": {
                    "relative_path": self.dataset.name,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                },
            },
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_materialization_writes_hashed_relative_artifacts_without_broker_authority(self):
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
        self.assertEqual(result["schema"], "mmibkr.canonical_data_materialization.v1")
        self.assertEqual(result["symbol"], "AMAT")
        self.assertEqual(result["source_timeframe"], "1Min")
        self.assertEqual(result["frame_count"], 2)
        self.assertFalse(result["broker_request_made"])
        self.assertFalse(result["safety"]["market_data_acquisition"])
        self.assertFalse(result["safety"]["historical_data_requests"])
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(str(self.input_root), rendered)
        self.assertNotIn(str(self.receipt_dir), rendered)

        fp = receipt["job_fingerprint"]
        artifact_root = self.receipt_dir / "artifacts" / fp
        self.assertGreaterEqual(result["artifact_count"], 7)
        for node in result["artifacts"]:
            self.assertFalse(Path(node["relative_path"]).is_absolute())
            path = artifact_root / node["relative_path"]
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_size, node["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), node["sha256"])
        self.assertRegex(result["canonical_dependencies"]["data_manager.py"], r"^[0-9a-f]{40}$")
        self.assertRegex(result["canonical_dependencies"]["feature_contract.py"], r"^[0-9a-f]{40}$")

    def test_materialization_requires_receipt_storage(self):
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "requires receipt_dir"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_input_path_and_digest_drift_fail_closed(self):
        req = self.request()
        req["arguments"]["dataset"]["relative_path"] = "../escape.csv"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "relative_path rejected"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=self.receipt_dir,
            )

        req = self.request()
        req["arguments"]["dataset"]["sha256"] = "c" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=self.receipt_dir,
            )

    def test_content_identical_rerun_reuses_receipt_and_validates_artifacts(self):
        first = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )
        second = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["receipt"], second["receipt"])

    def test_cached_artifact_tamper_is_detected(self):
        first = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )
        receipt = first["receipt"]
        artifact = receipt["result"]["artifacts"][0]
        path = self.receipt_dir / "artifacts" / receipt["job_fingerprint"] / artifact["relative_path"]
        path.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "artifact hash mismatch"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=self.receipt_dir,
            )

    def test_output_path_and_provider_authority_are_not_request_fields(self):
        req = self.request()
        req["arguments"]["output_path"] = "/tmp/controlled"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "unexpected fields"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=self.receipt_dir,
            )


if __name__ == "__main__":
    unittest.main()
