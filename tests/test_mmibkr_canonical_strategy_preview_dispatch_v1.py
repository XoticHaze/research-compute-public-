from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalStrategyPreviewDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()

        bridge = self.source_root / "autotuner_strategy_bridge.py"
        bridge.write_text(
            "import hashlib,json\n"
            "def normalize_strategy_spec(payload):\n"
            "    raw=dict(payload); spec=dict(raw.get('strategy_spec') or raw)\n"
            "    spec['strategy_id']=str(spec.get('strategy_id') or '')\n"
            "    spec['symbol']=str(spec.get('symbol') or '').upper()\n"
            "    spec['timeframe']=str(spec.get('timeframe') or '')\n"
            "    spec['asset_type']=str(spec.get('asset_type') or 'stocks')\n"
            "    spec['parameters']=dict(spec.get('parameters') or raw.get('params') or {})\n"
            "    if not spec['strategy_id'] or not spec['symbol'] or not spec['timeframe']: raise ValueError('identity missing')\n"
            "    digest=hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()\n"
            "    return {'strategy_spec':spec,'strategy_spec_digest':digest,'source_payload':raw}\n",
            encoding="utf-8",
        )

        feature_contract = self.source_root / "feature_contract.py"
        feature_contract.write_text(
            "from pathlib import Path\n"
            "import hashlib,json\n"
            "def read_feature_artifact_sidecar(data_path, *, verify_artifact=True):\n"
            "    path=Path(data_path); sidecar=path.with_suffix(path.suffix+'.manifest.json')\n"
            "    payload=json.loads(sidecar.read_text(encoding='utf-8'))\n"
            "    manifest=dict(payload.get('feature_manifest') or {})\n"
            "    if verify_artifact:\n"
            "        artifact=payload.get('artifact') or {}\n"
            "        if int(artifact.get('size_bytes') or -1)!=path.stat().st_size: raise ValueError('feature artifact size mismatch')\n"
            "        actual=hashlib.sha256(path.read_bytes()).hexdigest()\n"
            "        if str(artifact.get('sha256') or '').lower()!=actual: raise ValueError('feature artifact content hash mismatch')\n"
            "    if str(payload.get('feature_manifest_hash') or '').lower()!=str(manifest.get('manifest_hash') or '').lower(): raise ValueError('feature sidecar manifest hash mismatch')\n"
            "    return {**payload,'feature_manifest_hash':manifest['manifest_hash'],'feature_manifest':manifest}\n",
            encoding="utf-8",
        )

        data_manager = self.source_root / "data_manager.py"
        data_manager.write_text(
            "from pathlib import Path\n"
            "import hashlib,json\n"
            "import pandas as pd\n"
            "class DataManager:\n"
            "    def __init__(self, config, ib, sr_engine=None): self.base=Path(config['DATA_OUTPUT_DIR']); self.base.mkdir(parents=True,exist_ok=True)\n"
            "    def _dir(self,symbol): p=self.base/'stocks'/symbol; p.mkdir(parents=True,exist_ok=True); return p\n"
            "    def _path_for(self,asset_type,symbol,tf,features=False): return self._dir(symbol)/(tf+('.features.csv' if features else '.csv'))\n"
            "    def _aggregate_path(self,asset_type,symbol): return self._dir(symbol)/'aggregate.csv'\n"
            "    def _write(self,symbol,tf,frame):\n"
            "        raw=self._path_for('stocks',symbol,tf,False); feat=self._path_for('stocks',symbol,tf,True)\n"
            "        frame.to_csv(raw,index=False); frame.to_csv(feat,index=False)\n"
            "        semantic=hashlib.sha256(('semantic|'+tf).encode()).hexdigest(); manifest_hash=hashlib.sha256(('manifest|'+symbol+'|'+tf).encode()).hexdigest()\n"
            "        manifest={'contract_version':'feature_manifest.v2','manifest_hash':manifest_hash,'feature_semantic_hash':semantic,'features':[{'output_column':'close','identity_hash':hashlib.sha256(b'close').hexdigest()},{'output_column':'RSI','identity_hash':hashlib.sha256(b'RSI').hexdigest()}],'source_dataset_identity':{'provider':'governed_fixture','symbol':symbol,'timeframe':tf},'symbol_universe':[symbol],'source_timeframes':[tf],'target_timeframes':[tf],'alignment_rules':[{'mode':'asof'}],'warmup_policies':[{'bars':0}],'missing_value_policies':['drop'],'causal':True,'generation_identity':'fixture','consumer_identity':'canonical_data_materialize','feature_contract_mode':'canonical_compute','label_target_columns_excluded':[]}\n"
            "        sidecar=feat.with_suffix(feat.suffix+'.manifest.json')\n"
            "        sidecar.write_text(json.dumps({'contract_version':'feature_artifact_sidecar.v1','feature_manifest_hash':manifest_hash,'feature_manifest':manifest,'artifact':{'filename':feat.name,'sha256':hashlib.sha256(feat.read_bytes()).hexdigest(),'size_bytes':feat.stat().st_size}},sort_keys=True)+'\\n',encoding='utf-8')\n"
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

        strategies = self.source_root / "strategies"
        strategies.mkdir()
        strategy_init = strategies / "__init__.py"
        strategy_init.write_text(
            "class FakeStrategy:\n"
            "    def __init__(self, config=None): self.config=dict(config or {})\n"
            "    @classmethod\n"
            "    def parameter_schema(cls): return {'threshold':{'type':'float','default':1.0}}\n"
            "    @classmethod\n"
            "    def condition_spec(cls): return {'entry':'fixture'}\n"
            "    def evaluate(self, frame):\n"
            "        row=frame.iloc[-1].to_dict(); close=float(row.get('close') or 0)\n"
            "        signal='BUY' if close>=100 else 'HOLD'\n"
            "        meta={'reason':'native_fixture_signal','conditions':{'current_values':{'close':close},'entry_long':{'passed':signal=='BUY','items':[{'id':'native-entry','label':'close gate','left':'close','left_value':close,'operator':'>=','right_param':'threshold','right_value':100,'enabled':True,'passed':signal=='BUY'}]},'exit_long':{'passed':False,'items':[]}}}\n"
            "        return signal,meta\n"
            "REGISTRY={'crw_score_multi_mode':FakeStrategy,'test_strategy':FakeStrategy}\n"
            "def create(name, **kwargs):\n"
            "    cls=REGISTRY.get(str(name));\n"
            "    if cls is None: raise ValueError('Unknown strategy')\n"
            "    return cls(kwargs.get('config') or {})\n",
            encoding="utf-8",
        )
        event_bus = strategies / "event_bus.py"
        event_bus.write_text(
            "from types import SimpleNamespace\n"
            "def build_strategy_definition(strategy_id, config):\n"
            "    required=['close','RSI']\n"
            "    return SimpleNamespace(strategy_id=strategy_id,version='fixture_v1',required_indicators=required,warmup_bars=2,parameters=dict(config),feature_manifest={})\n",
            encoding="utf-8",
        )

        builder = self.source_root / "strategy_builder_condition_contract_14th31kn.py"
        builder.write_text(
            "RESERVED='__builder_condition_contract_14th31kn'\n"
            "def builder_condition_contract_from_payload(payload):\n"
            "    spec=dict(payload.get('strategy_spec') or {}); params=dict(spec.get('parameters') or {}); return dict(params.get(RESERVED) or {})\n"
            "def evaluate_builder_condition_contract(contract, *, feature_values, context_values):\n"
            "    threshold=float(contract.get('min_close') or 0); close=float(feature_values.get('close') or 0); passed=close>=threshold\n"
            "    return {'evaluation_ready':True,'signal':'SELL' if passed else 'HOLD','reason_code':'builder_fixture','missing_indicators':[],'entry':{'passed':passed},'context_digest':str(sorted(context_values))}\n",
            encoding="utf-8",
        )

        self.blobs = {
            "bridge": git_blob_sha1(bridge.read_bytes()),
            "feature": git_blob_sha1(feature_contract.read_bytes()),
            "data": git_blob_sha1(data_manager.read_bytes()),
            "strategies": git_blob_sha1(strategy_init.read_bytes()),
        }

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
            "timestamp,open,high,low,close,volume,RSI,VWAP\n"
            "2026-09-22T14:30:00Z,100,101,99,100.5,900,55,100.2\n"
            "2026-09-22T14:31:00Z,101,102,100,101.5,0,57,101.1\n",
            encoding="utf-8",
        )
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def _base(self, job_id: str, capability: str, path: str, module: str, callable_name: str, blob_sha: str, arguments: dict) -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": job_id,
            "capability_id": capability,
            "mmibkr": {"repository": mod.SOURCE_REPOSITORY, "commit": self.commit, "source_archive_sha256": self.archive},
            "entrypoint": {"path": path, "module": module, "callable": callable_name, "git_blob_sha1": blob_sha},
            "arguments": arguments,
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def data_request(self) -> dict:
        raw = self.dataset.read_bytes()
        return self._base(
            "data-preview", "CANONICAL_DATA_MATERIALIZE", "data_manager.py", "data_manager", "DataManager", self.blobs["data"],
            {"asset_type":"stocks","symbol":"AMAT","source_timeframe":"1Min","target_timeframes":["15Min"],"source_origin":"governed_fixture","dataset":{"relative_path":self.dataset.name,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}},
        )

    def feature_ref(self) -> tuple[dict, dict]:
        data = mod.execute_request(self.data_request(), source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root, receipt_dir=self.receipt_dir)["receipt"]
        row = next(x for x in data["result"]["frames"] if x["timeframe"] == "15Min")
        f = row["feature_artifact"]
        return row, {"scope":"receipt_artifact","job_fingerprint":data["job_fingerprint"],"relative_path":f["relative_path"],"sha256":f["sha256"],"bytes":f["bytes"]}

    def preview_request(self, ref: dict, *, strategy_id="crw_score_multi_mode", row_policy="latest_execution_safe", parameters=None, context=None) -> dict:
        return self._base(
            "preview-one", "STRATEGY_PREVIEW", "strategies/__init__.py", "strategies", "create", self.blobs["strategies"],
            {
                "strategy_spec":{"strategy_id":strategy_id,"symbol":"AMAT","timeframe":"15Min","asset_type":"stocks","parameters":dict(parameters or {})},
                "feature_artifact":ref,
                "row_policy":row_policy,
                "lookback_rows":12,
                "context_values":dict(context or {}),
                "expected_feature_semantic_hash":None,
            },
        )

    def test_full_chain_preview_uses_recent_safe_row_and_emits_no_operator_authority(self):
        row, ref = self.feature_ref()
        receipt = mod.execute_request(
            self.preview_request(ref),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            receipt_dir=self.receipt_dir,
        )["receipt"]
        result = receipt["result"]
        self.assertEqual(result["schema"], "mmibkr.strategy_preview.v1")
        self.assertEqual(result["strategy"]["strategy_id"], "crw_score_multi_mode")
        self.assertTrue(result["row_selection"]["used_fallback_row"])
        self.assertEqual(result["row_selection"]["selected_feature_timestamp"], "2026-09-22 14:30:00+00:00")
        self.assertIn("latest_zero_volume_bar_skipped", result["data_quality"]["warnings"])
        self.assertEqual(result["signal"]["raw_signal"], "BUY")
        self.assertEqual(result["strategy"]["missing_indicators"], [])
        self.assertEqual(result["feature_manifest_hash"], row["feature_manifest_hash"])
        self.assertRegex(result["strategy_spec_digest"], r"^[0-9a-f]{64}$")
        for key in ("position_snapshot_used","risk_preview_used","sizing_preview_used","broker_preview_used","order_intent_emitted","broker_submit","broker_cancel","broker_flatten","runtime_activation","live_trading"):
            self.assertFalse(result["safety"][key])
        rendered=json.dumps(receipt,sort_keys=True)
        self.assertNotIn(str(self.root),rendered)
        self.assertNotIn("order_intent", result)
        self.assertNotIn("broker_preview", result)
        self.assertNotIn("position_guard", result)
        self.assertNotIn("risk_result", result)
        self.assertNotIn("sizing_preview", result)

    def test_non_volume_fatal_does_not_fallback(self):
        _, ref = self.feature_ref()
        artifact_root = self.receipt_dir / "artifacts" / ref["job_fingerprint"]
        path = artifact_root / ref["relative_path"]
        rows = path.read_text(encoding="utf-8").splitlines()
        header = rows[0].split(",")
        close_idx = header.index("close")
        last = rows[-1].split(","); last[close_idx] = "0"; last[header.index("volume")] = "1000"
        path.write_text("\n".join(rows[:-1] + [",".join(last)]) + "\n", encoding="utf-8")
        ref["bytes"] = path.stat().st_size
        ref["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        sidecar = path.with_suffix(path.suffix+".manifest.json")
        payload=json.loads(sidecar.read_text(encoding="utf-8"))
        payload["artifact"]["size_bytes"]=path.stat().st_size
        payload["artifact"]["sha256"]=ref["sha256"]
        sidecar.write_text(json.dumps(payload,sort_keys=True)+"\n",encoding="utf-8")
        receipt=mod.execute_request(self.preview_request(ref),source_root=self.source_root,source_receipt=self.source_receipt,receipt_dir=self.receipt_dir)["receipt"]
        result=receipt["result"]
        self.assertFalse(result["row_selection"]["used_fallback_row"])
        self.assertIn("close <= 0", result["data_quality"]["fatal_reasons"])
        self.assertIn("latest_row_not_execution_safe", result["row_selection"]["blockers"])

    def test_manifest_symbol_and_timeframe_mismatch_fail_closed(self):
        _, ref = self.feature_ref()
        artifact_root=self.receipt_dir/"artifacts"/ref["job_fingerprint"]; path=artifact_root/ref["relative_path"]; sidecar=path.with_suffix(path.suffix+".manifest.json")
        original_sidecar=sidecar.read_text(encoding="utf-8")
        payload=json.loads(original_sidecar)
        payload["feature_manifest"]["symbol_universe"]=["APH"]
        sidecar.write_text(json.dumps(payload,sort_keys=True)+"\n",encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"symbol is not present"):
            mod.execute_request(self.preview_request(ref),source_root=self.source_root,source_receipt=self.source_receipt,receipt_dir=self.receipt_dir)
        sidecar.write_text(original_sidecar,encoding="utf-8")

        _, ref = self.feature_ref()
        artifact_root=self.receipt_dir/"artifacts"/ref["job_fingerprint"]; path=artifact_root/ref["relative_path"]; sidecar=path.with_suffix(path.suffix+".manifest.json")
        payload=json.loads(sidecar.read_text(encoding="utf-8"))
        payload["feature_manifest"]["target_timeframes"]=["1Hour"]
        sidecar.write_text(json.dumps(payload,sort_keys=True)+"\n",encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"timeframe is not present"):
            mod.execute_request(self.preview_request(ref),source_root=self.source_root,source_receipt=self.source_receipt,receipt_dir=self.receipt_dir)

    def test_builder_condition_override_preserves_native_registry_evaluation(self):
        _, ref = self.feature_ref()
        contract={"contract_hash":"c"*64,"min_close":100}
        receipt=mod.execute_request(
            self.preview_request(ref,strategy_id="test_strategy",parameters={"__builder_condition_contract_14th31kn":contract},context={"regime":"risk_on"}),
            source_root=self.source_root,source_receipt=self.source_receipt,receipt_dir=self.receipt_dir,
        )["receipt"]
        result=receipt["result"]
        self.assertEqual(result["signal"]["raw_signal"],"SELL")
        self.assertEqual(result["signal"]["reason"],"builder_fixture")
        builder=result["builder_condition_execution"]
        self.assertTrue(builder["evaluation_ready"])
        self.assertIn("strategy_builder_condition_contract_14th31kn.py",result["canonical_dependencies"])

    def test_execution_overlay_fields_are_rejected(self):
        _, ref = self.feature_ref()
        req=self.preview_request(ref)
        req["arguments"]["risk"]={"stop":1}
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"unexpected fields"):
            mod.execute_request(req,source_root=self.source_root,source_receipt=self.source_receipt,receipt_dir=self.receipt_dir)

    def test_manifest_semantic_expectation_is_bound(self):
        _, ref = self.feature_ref()
        req=self.preview_request(ref)
        req["arguments"]["expected_feature_semantic_hash"]="d"*64
        with self.assertRaisesRegex(mod.CanonicalDispatchError,"semantic hash mismatch"):
            mod.execute_request(req,source_root=self.source_root,source_receipt=self.source_receipt,receipt_dir=self.receipt_dir)


if __name__ == "__main__":
    unittest.main()
