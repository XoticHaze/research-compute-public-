from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalOptionsFeatureMaterializeDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()
        (self.source_root / "scripts" / "operator").mkdir(parents=True)
        (self.source_root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        (self.source_root / "scripts" / "operator" / "__init__.py").write_text("", encoding="utf-8")

        owner = self.source_root / "options_snapshot_features.py"
        owner.write_text(
            "from pathlib import Path\n"
            "import hashlib,json\n"
            "CALLS=[]\n"
            "def materialize_options_feature_artifact(history_path,target_bar_csv,output_feature_csv,output_manifest_json,*,symbol,target_timeframe,max_snapshot_age_seconds,risk_free_rate):\n"
            "    CALLS.append({'history':str(history_path),'bars':str(target_bar_csv),'symbol':symbol,'target_timeframe':target_timeframe,'max_snapshot_age_seconds':max_snapshot_age_seconds,'risk_free_rate':risk_free_rate})\n"
            "    feature=Path(output_feature_csv); manifest=Path(output_manifest_json)\n"
            "    feature.write_text('timestamp,OPTIONS_OBSERVATION_AVAILABLE,OPTIONS_FRESH_ROW_COUNT\\n2026-09-24T14:15:00Z,1,2\\n2026-09-24T14:30:00Z,1,0\\n',encoding='utf-8')\n"
            "    manifest_hash='c'*64; semantic_hash='d'*64\n"
            "    manifest.write_text(json.dumps({'manifest_hash':manifest_hash,'feature_semantic_hash':semantic_hash,'feature_count':2},sort_keys=True)+'\\n',encoding='utf-8')\n"
            "    digest=hashlib.sha256(feature.read_bytes()).hexdigest()\n"
            "    return {'schema':'mm.options_snapshot_bar_feature_materialization.v1','symbol':symbol,'target_timeframe':target_timeframe,'history_observations_for_symbol':2,'target_bar_rows':3,'fresh_aligned_bar_rows':2,'unavailable_or_stale_bar_rows':1,'max_snapshot_age_seconds':max_snapshot_age_seconds,'risk_free_rate':risk_free_rate,'first_observation_utc':'2026-09-24T14:01:00+00:00','last_observation_utc':'2026-09-24T14:31:00+00:00','first_target_bar_utc':'2026-09-24T14:00:00+00:00','last_target_bar_utc':'2026-09-24T14:30:00+00:00','safety':{'provider_acquisition':False,'bar_resample':False,'target_or_label_materialization':False,'forward_fill_beyond_max_age':False,'strategy_spec_write':False,'runtime_activation':False,'promotion_mutation':False,'broker_submit':False,'live_trading':False},'feature_artifact':{'path':str(feature),'sha256':digest,'bytes':feature.stat().st_size,'rows':2,'columns':['timestamp','OPTIONS_OBSERVATION_AVAILABLE','OPTIONS_FRESH_ROW_COUNT']},'feature_manifest':{'path':str(manifest),'manifest_hash':manifest_hash,'feature_semantic_hash':semantic_hash,'feature_count':2}}\n",
            encoding="utf-8",
        )
        self.owner_blob = git_blob_sha1(owner.read_bytes())

        scanner = self.source_root / "options_scanner.py"
        scanner.write_text("class OptionsScanner:\n    pass\n", encoding="utf-8")

        feature_contract = self.source_root / "feature_contract.py"
        feature_contract.write_text(
            "import json\n"
            "from pathlib import Path\n"
            "def read_feature_artifact_sidecar(feature_path,verify_artifact=True):\n"
            "    path=Path(feature_path); side=path.with_name(path.name+'.manifest.json')\n"
            "    return json.loads(side.read_text(encoding='utf-8'))\n",
            encoding="utf-8",
        )
        self.feature_contract_blob = git_blob_sha1(feature_contract.read_bytes())

        publisher = self.source_root / "scripts" / "operator" / "publish_canonical_feature_sidecar.py"
        publisher.write_text(
            "from pathlib import Path\n"
            "import json\n"
            "def publish_sidecar(feature_csv,manifest_json,*,expected_feature_sha256,expected_manifest_hash):\n"
            "    feature=Path(feature_csv); manifest=Path(manifest_json)\n"
            "    node=json.loads(manifest.read_text(encoding='utf-8'))\n"
            "    if node.get('manifest_hash')!=expected_manifest_hash: raise ValueError('manifest hash mismatch')\n"
            "    side=feature.with_name(feature.name+'.manifest.json')\n"
            "    payload={'contract_version':'feature_artifact_sidecar.v1','feature_manifest_hash':expected_manifest_hash,'feature_manifest':{'contract_version':'feature_contract.v1','feature_contract_mode':'canonical_compute','causal':True,'manifest_hash':expected_manifest_hash,'feature_semantic_hash':node['feature_semantic_hash'],'features':[{'feature_id':'options_a','output_column':'OPTIONS_OBSERVATION_AVAILABLE','identity_hash':'1'*64,'causal':True},{'feature_id':'options_rows','output_column':'OPTIONS_FRESH_ROW_COUNT','identity_hash':'2'*64,'causal':True}]},'artifact':{'filename':feature.name,'sha256':expected_feature_sha256},'publication':{'feature_recompute':False,'downloader':False,'resampler':False,'feature_value_mutation':False}}\n"
            "    side.write_text(json.dumps(payload,sort_keys=True)+'\\n',encoding='utf-8')\n"
            "    return {'schema':'mm.canonical_feature_sidecar_publication.v1','status':'PASS','feature_path':str(feature),'feature_sha256':expected_feature_sha256,'feature_rows':2,'feature_outputs':['OPTIONS_OBSERVATION_AVAILABLE','OPTIONS_FRESH_ROW_COUNT'],'feature_manifest_hash':expected_manifest_hash,'sidecar_path':str(side),'sidecar_contract_version':'feature_artifact_sidecar.v1','safety':payload['publication']}\n",
            encoding="utf-8",
        )

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
        self.history = self.input_root / "snapshot_history.jsonl"
        self.history.write_text(
            '{"schema":"mmibkr.options_snapshot_history.v1","snapshot_id":"fixture"}\n',
            encoding="utf-8",
        )
        self.bars = self.input_root / "15Min.csv"
        self.bars.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-09-24T14:00:00Z,100,101,99,100.5,10\n"
            "2026-09-24T14:15:00Z,100.5,102,100,101.5,11\n"
            "2026-09-24T14:30:00Z,101.5,103,101,102.5,12\n",
            encoding="utf-8",
        )
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def _input_ref(self, path: Path) -> dict:
        raw = path.read_bytes()
        return {
            "scope": "input_root",
            "relative_path": path.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }

    def request(self) -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "options-feature-materialize-fixture",
            "capability_id": "OPTIONS_FEATURE_MATERIALIZE",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": "options_snapshot_features.py",
                "module": "options_snapshot_features",
                "callable": "materialize_options_feature_artifact",
                "git_blob_sha1": self.owner_blob,
            },
            "arguments": {
                "history": self._input_ref(self.history),
                "target_bars": self._input_ref(self.bars),
                "symbol": "AAPL",
                "target_timeframe": "15Min",
                "max_snapshot_age_seconds": 1200,
                "risk_free_rate": 0.04,
            },
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def execute(self, req=None):
        return mod.execute_request(
            req or self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )

    def test_delegates_to_canonical_owner_and_publishes_chainable_feature_artifact(self):
        out = self.execute()
        self.assertFalse(out["cache_hit"])
        receipt = out["receipt"]
        result = receipt["result"]
        self.assertEqual(result["schema"], "mmibkr.options_feature_materialization.v1")
        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["target_timeframe"], "15Min")
        self.assertEqual(result["max_snapshot_age_seconds"], 1200)
        self.assertEqual(result["risk_free_rate"], 0.04)
        self.assertEqual(result["history_observations_for_symbol"], 2)
        self.assertEqual(result["fresh_aligned_bar_rows"], 2)
        self.assertEqual(result["unavailable_or_stale_bar_rows"], 1)
        self.assertEqual(result["feature_manifest_hash"], "c" * 64)
        self.assertEqual(result["feature_semantic_hash"], "d" * 64)
        self.assertFalse(result["safety"]["provider_acquisition"])
        self.assertFalse(result["safety"]["bar_resample"])
        self.assertFalse(result["safety"]["target_or_label_materialization"])
        self.assertFalse(result["safety"]["forward_fill_beyond_max_age"])
        self.assertFalse(result["safety"]["broker_submit"])
        self.assertFalse(result["safety"]["runtime_activation"])
        self.assertFalse(result["safety"]["promotion_mutation"])
        self.assertFalse(result["safety"]["live_trading"])

        self.assertEqual(set(result["artifact_map"]), {"features", "manifest", "sidecar"})
        artifact_root = self.receipt_dir / "artifacts" / receipt["job_fingerprint"]
        for node in result["artifacts"]:
            path = artifact_root / node["relative_path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), node["sha256"])

        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        self.assertEqual(
            set(result["canonical_dependencies"]),
            {
                "options_snapshot_features.py",
                "options_scanner.py",
                "feature_contract.py",
                "scripts/operator/publish_canonical_feature_sidecar.py",
            },
        )

        feature_ref = {
            "scope": "receipt_artifact",
            "job_fingerprint": receipt["job_fingerprint"],
            **result["artifact_map"]["features"],
        }
        validate_req = {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "options-feature-contract-validate",
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
                "git_blob_sha1": self.feature_contract_blob,
            },
            "arguments": {
                "feature_artifact": feature_ref,
                "expected_manifest_hash": "c" * 64,
                "expected_semantic_hash": "d" * 64,
            },
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }
        validated = mod.execute_request(
            validate_req,
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=self.receipt_dir,
        )["receipt"]["result"]
        self.assertEqual(validated["feature_manifest_hash"], "c" * 64)
        self.assertEqual(validated["feature_semantic_hash"], "d" * 64)
        self.assertEqual(
            validated["feature_columns"],
            ["OPTIONS_OBSERVATION_AVAILABLE", "OPTIONS_FRESH_ROW_COUNT"],
        )

    def test_request_rejects_unowned_output_or_acquisition_fields(self):
        req = self.request()
        req["arguments"]["output_path"] = "/tmp/escape.csv"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "unexpected fields"):
            self.execute(req)

        req = self.request()
        req["arguments"]["provider_acquisition"] = True
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "unexpected fields"):
            self.execute(req)

    def test_parameter_and_governed_input_validation_fail_closed(self):
        req = self.request()
        req["arguments"]["max_snapshot_age_seconds"] = 0
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "must be positive"):
            self.execute(req)

        req = self.request()
        req["arguments"]["risk_free_rate"] = 0.9
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "within -0.10..0.50"):
            self.execute(req)

        req = self.request()
        req["arguments"]["history"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            self.execute(req)

    def test_canonical_owner_authority_drift_fails_closed(self):
        owner = self.source_root / "options_snapshot_features.py"
        text = owner.read_text(encoding="utf-8").replace(
            "'provider_acquisition':False",
            "'provider_acquisition':True",
        )
        owner.write_text(text, encoding="utf-8")
        req = self.request()
        req["entrypoint"]["git_blob_sha1"] = git_blob_sha1(owner.read_bytes())
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "canonical safety contract rejected"):
            self.execute(req)

    def test_requires_receipt_storage_and_detects_cached_artifact_tamper(self):
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "requires receipt_dir"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

        first = self.execute()
        second = self.execute()
        self.assertTrue(second["cache_hit"])
        result = first["receipt"]["result"]
        artifact_root = self.receipt_dir / "artifacts" / first["receipt"]["job_fingerprint"]
        target = artifact_root / result["artifact_map"]["features"]["relative_path"]
        target.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "artifact hash mismatch"):
            self.execute()


if __name__ == "__main__":
    unittest.main()
