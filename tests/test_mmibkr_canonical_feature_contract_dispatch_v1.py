from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalFeatureContractDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()

        feature_contract = self.source_root / "feature_contract.py"
        feature_contract.write_text(
            "from pathlib import Path\n"
            "import hashlib,json\n"
            "def _sha(path):\n"
            "    return hashlib.sha256(Path(path).read_bytes()).hexdigest()\n"
            "def read_feature_artifact_sidecar(data_path, *, verify_artifact=True):\n"
            "    path=Path(data_path); sidecar=path.with_suffix(path.suffix+'.manifest.json')\n"
            "    payload=json.loads(sidecar.read_text(encoding='utf-8'))\n"
            "    manifest=dict(payload.get('feature_manifest') or {})\n"
            "    if verify_artifact:\n"
            "        artifact=payload.get('artifact') or {}\n"
            "        if int(artifact.get('size_bytes') or -1)!=path.stat().st_size: raise ValueError('feature artifact size mismatch')\n"
            "        if str(artifact.get('sha256') or '').lower()!=_sha(path): raise ValueError('feature artifact content hash mismatch')\n"
            "    if str(payload.get('feature_manifest_hash') or '').lower()!=str(manifest.get('manifest_hash') or '').lower(): raise ValueError('feature sidecar manifest hash mismatch')\n"
            "    return {**payload,'feature_manifest_hash':manifest['manifest_hash'],'feature_manifest':manifest}\n",
            encoding="utf-8",
        )
        self.feature_blob = git_blob_sha1(feature_contract.read_bytes())

        data_manager = self.source_root / "data_manager.py"
        data_manager.write_text(
            "from pathlib import Path\n"
            "import hashlib,json\n"
            "import pandas as pd\n"
            "class DataManager:\n"
            "    def __init__(self, config, ib, sr_engine=None):\n"
            "        self.base=Path(config['DATA_OUTPUT_DIR']); self.base.mkdir(parents=True,exist_ok=True)\n"
            "    def _dir(self,symbol):\n"
            "        p=self.base/'stocks'/symbol; p.mkdir(parents=True,exist_ok=True); return p\n"
            "    def _path_for(self,asset_type,symbol,tf,features=False):\n"
            "        return self._dir(symbol)/(tf+('.features.csv' if features else '.csv'))\n"
            "    def _aggregate_path(self,asset_type,symbol): return self._dir(symbol)/'aggregate.csv'\n"
            "    def _manifest(self,symbol,tf):\n"
            "        semantic=hashlib.sha256(('semantic|'+tf).encode()).hexdigest()\n"
            "        manifest=hashlib.sha256(('manifest|'+symbol+'|'+tf).encode()).hexdigest()\n"
            "        return {'contract_version':'feature_manifest.v2','manifest_hash':manifest,'feature_semantic_hash':semantic,'features':[{'output_column':'close','identity_hash':hashlib.sha256(b'close').hexdigest()}],'source_dataset_identity':{'provider':'governed_fixture','symbol':symbol,'timeframe':tf},'symbol_universe':[symbol],'source_timeframes':[tf],'target_timeframes':[tf],'alignment_rules':[{'mode':'asof'}],'warmup_policies':[{'bars':0}],'missing_value_policies':['drop'],'causal':True,'generation_identity':'fixture','consumer_identity':'canonical_data_materialize','feature_contract_mode':'canonical_compute','label_target_columns_excluded':[]}\n"
            "    def _write(self,symbol,tf,frame):\n"
            "        raw=self._path_for('stocks',symbol,tf,False); feat=self._path_for('stocks',symbol,tf,True)\n"
            "        frame.to_csv(raw,index=False); frame.to_csv(feat,index=False)\n"
            "        manifest=self._manifest(symbol,tf)\n"
            "        sidecar=feat.with_suffix(feat.suffix+'.manifest.json')\n"
            "        sidecar.write_text(json.dumps({'contract_version':'feature_artifact_sidecar.v1','feature_manifest_hash':manifest['manifest_hash'],'feature_manifest':manifest,'artifact':{'filename':feat.name,'sha256':hashlib.sha256(feat.read_bytes()).hexdigest(),'size_bytes':feat.stat().st_size}},sort_keys=True)+'\\n',encoding='utf-8')\n"
            "    def ingest_external_stock_source_bars(self,symbol,source_tf,frame,*,target_timeframes=None,source_origin='external'):\n"
            "        frame=frame.copy(); frame['timestamp']=pd.to_datetime(frame['timestamp'],utc=True); frame=frame.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)\n"
            "        requested=[]\n"
            "        for tf in [source_tf]+list(target_timeframes or []):\n"
            "            if tf not in requested: requested.append(tf)\n"
            "        frames={}; aggregate=[]\n"
            "        for tf in requested:\n"
            "            node=frame.copy(); node['timeframe']=tf; self._write(symbol,tf,node); frames[tf]=node; aggregate.append(node)\n"
            "        pd.concat(aggregate,ignore_index=True).to_csv(self._aggregate_path('stocks',symbol),index=False)\n"
            "        return {'ok':True,'frames':frames,'broker_request_made':False}\n",
            encoding="utf-8",
        )
        self.data_blob = git_blob_sha1(data_manager.read_bytes())

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
        self.dataset = self.input_root / "amat.csv"
        self.dataset.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-09-22T14:30:00Z,100,101,99,100.5,900\n"
            "2026-09-22T14:31:00Z,101,102,100,101.5,1000\n",
            encoding="utf-8",
        )
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def data_request(self) -> dict:
        raw = self.dataset.read_bytes()
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "data-job",
            "capability_id": "CANONICAL_DATA_MATERIALIZE",
            "mmibkr": {"repository": mod.SOURCE_REPOSITORY, "commit": self.commit, "source_archive_sha256": self.archive},
            "entrypoint": {"path": "data_manager.py", "module": "data_manager", "callable": "DataManager", "git_blob_sha1": self.data_blob},
            "arguments": {
                "asset_type": "stocks",
                "symbol": "AMAT",
                "source_timeframe": "1Min",
                "target_timeframes": ["1Min", "15Min"],
                "source_origin": "governed_fixture",
                "dataset": {"relative_path": self.dataset.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)},
            },
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def feature_request(self, ref: dict, *, expected_manifest=None, expected_semantic=None) -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "feature-job",
            "capability_id": "FEATURE_CONTRACT_VALIDATE",
            "mmibkr": {"repository": mod.SOURCE_REPOSITORY, "commit": self.commit, "source_archive_sha256": self.archive},
            "entrypoint": {"path": "feature_contract.py", "module": "feature_contract", "callable": "read_feature_artifact_sidecar", "git_blob_sha1": self.feature_blob},
            "arguments": {
                "feature_artifact": ref,
                "expected_manifest_hash": expected_manifest,
                "expected_semantic_hash": expected_semantic,
            },
            "resources": {"max_wall_seconds": 30, "max_output_bytes": 200000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def materialized_feature_ref(self) -> tuple[dict, dict, dict]:
        data = mod.execute_request(
            self.data_request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )["receipt"]
        row = next(row for row in data["result"]["frames"] if row["timeframe"] == "15Min")
        feature = row["feature_artifact"]
        ref = {
            "scope": "receipt_artifact",
            "job_fingerprint": data["job_fingerprint"],
            "relative_path": feature["relative_path"],
            "sha256": feature["sha256"],
            "bytes": feature["bytes"],
        }
        return data, row, ref

    def test_materialize_to_feature_validation_handoff_uses_receipt_artifact_identity(self):
        data, row, ref = self.materialized_feature_ref()
        out = mod.execute_request(
            self.feature_request(
                ref,
                expected_manifest=row["feature_manifest_hash"],
            ),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            receipt_dir=self.receipt_dir,
        )["receipt"]
        result = out["result"]
        self.assertEqual(result["schema"], "mmibkr.feature_contract_validation.v1")
        self.assertEqual(result["feature_manifest_hash"], row["feature_manifest_hash"])
        self.assertRegex(result["feature_semantic_hash"], r"^[0-9a-f]{64}$")
        self.assertTrue(result["causal"])
        self.assertEqual(result["feature_count"], 1)
        self.assertEqual(result["feature_columns"], ["close"])
        self.assertEqual(result["symbol_universe"], ["AMAT"])
        self.assertEqual(result["target_timeframes"], ["15Min"])
        self.assertEqual(result["feature_artifact"]["job_fingerprint"], data["job_fingerprint"])
        rendered = json.dumps(out, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(out["authority"][key])

    def test_receipt_artifact_hash_drift_fails_closed(self):
        _, _, ref = self.materialized_feature_ref()
        ref["sha256"] = "c" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            mod.execute_request(
                self.feature_request(ref),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                receipt_dir=self.receipt_dir,
            )

    def test_expected_semantic_hash_mismatch_fails_closed(self):
        _, _, ref = self.materialized_feature_ref()
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "semantic hash mismatch"):
            mod.execute_request(
                self.feature_request(ref, expected_semantic="d" * 64),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                receipt_dir=self.receipt_dir,
            )

    def test_input_root_scope_is_supported_for_portable_external_feature_artifacts(self):
        data, row, _ = self.materialized_feature_ref()
        source_root = self.receipt_dir / "artifacts" / data["job_fingerprint"]
        feature = row["feature_artifact"]
        ref = {
            "scope": "input_root",
            "relative_path": feature["relative_path"],
            "sha256": feature["sha256"],
            "bytes": feature["bytes"],
        }
        receipt = mod.execute_request(
            self.feature_request(ref),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=source_root,
            receipt_dir=self.receipt_dir,
        )["receipt"]
        self.assertEqual(receipt["result"]["feature_artifact"]["scope"], "input_root")

    def test_invalid_receipt_job_fingerprint_is_rejected(self):
        _, _, ref = self.materialized_feature_ref()
        ref["job_fingerprint"] = "not-a-sha"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "job_fingerprint is invalid"):
            mod.execute_request(
                self.feature_request(ref),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                receipt_dir=self.receipt_dir,
            )


if __name__ == "__main__":
    unittest.main()
