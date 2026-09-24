from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalAutoTunerCampaignValidationDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()
        (self.source_root / "strategies/python").mkdir(parents=True)
        (self.source_root / "strategies/__init__.py").write_text("", encoding="utf-8")
        (self.source_root / "strategies/python/__init__.py").write_text("", encoding="utf-8")

        files = {
            "autotuner_strategy_bridge.py": (
                "import hashlib,json\n"
                "def normalize_strategy_spec(payload):\n"
                "    raw=dict(payload); spec=dict(raw.get('strategy_spec') or raw)\n"
                "    spec['strategy_id']=str(spec.get('strategy_id') or '')\n"
                "    spec['symbol']=str(spec.get('symbol') or '').upper()\n"
                "    spec['timeframe']=str(spec.get('timeframe') or '')\n"
                "    spec['parameters']=dict(spec.get('parameters') or {})\n"
                "    digest=hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest()\n"
                "    return {'strategy_spec':spec,'strategy_spec_digest':digest,'source_payload':raw}\n"
            ),
            "autotuner_campaign_planner.py": (
                "def new_campaign_state(digest):\n"
                "    return {'schema':'mm.autotuner_campaign_state.v1','campaign_id':'fixture','strategy_spec_digest':digest,'phase':'COARSE','planned_config_ids':[],'evaluated_config_ids':[]}\n"
            ),
            "autotuner_parameter_consumption.py": "# fixture dependency\n",
            "strategies/python/crw_score_multi_mode.py": (
                "class CrwScoreMultiModeStrategy:\n"
                "    @classmethod\n"
                "    def parameter_schema(cls): return {'ENTRY_EXTREME':{'type':'float','default':-2.8}}\n"
            ),
            "strategy_backtest_registry.py": (
                "def run_strategy_backtest(payload,data_root):\n"
                "    paths=payload.get('_verified_source_paths') or {}\n"
                "    assert paths.get('MNQ')\n"
                "    assert payload.get('asset_type')=='futures'\n"
                "    return {'ok':True,'status':'ok','total_trades':40,'profit_factor':1.4,'sortino':0.8,'max_drawdown':10.0,'net_pnl':12.0,'win_rate':0.6,'artifact_dir':'/private/artifacts','data_coverage':[{'source_path':paths['MNQ'],'rows':3}]}\n"
            ),
            "model_lab_validation.py": "# fixture dependency\n",
            "autotuner_campaign_runner.py": (
                "def run_campaign_iteration(*,strategy_payload,data_root,state,history,tune_parameters=None,advisory_suggestions=None,batch_size=12,coarse_points=5,score_tolerance_fraction=0.05,backtest_runner=None):\n"
                "    result=backtest_runner(strategy_payload,data_root)\n"
                "    report={'schema':'mm.autotuner_campaign_iteration.v1','state':'CAMPAIGN_ITERATION_EXECUTED','campaign_id':'fixture','strategy_spec_digest':state['strategy_spec_digest'],'strategy_spec':strategy_payload.get('strategy_spec'),'phase':'COARSE','iteration':1,'candidate_count':1,'baseline':{'metrics':result},'evaluations':[{'config_id':'c1','parameters':{'ENTRY_EXTREME':-3.0},'metrics':result,'error':'RuntimeError: /private/secret/path'}],'decision':{'research_evidence_only':True,'final_untouched_holdout_required':True,'human_review_before_strategy_spec_change':True,'automatic_promotion':False,'automatic_strategy_spec_write':False},'safety':{'backtest_only':True,'runtime_activation':False,'broker_submit':False,'live_unlock':False}}\n"
                "    next_state=dict(state); next_state['evaluated_config_ids']=['c1']\n"
                "    next_history={'schema':'mm.autotuner_campaign_history.v1','strategy_spec_digest':state['strategy_spec_digest'],'results':[{'config_id':'c1','score':1.0,'metrics':result,'error':'ValueError: /private/secret/path'}]}\n"
                "    return report,next_state,next_history\n"
            ),
            "autotuner_primary_validation_runner.py": (
                "def execute_primary_validation(staged_plan,strategy_spec_payload,dataset_path,*,split_policy,backtest_runner=None,split_builder=None):\n"
                "    from pathlib import Path\n"
                "    path=Path(dataset_path); assert path.is_file()\n"
                "    return {'schema':'mm.autotuner_primary_validation_execution.v1','state':'PRIMARY_VALIDATION_EXECUTED','strategy_spec_digest':staged_plan['strategy_spec_digest'],'candidate_label':'candidate_1','candidate_mutation':staged_plan['candidate_mutation'],'canonical_data_ref':staged_plan['canonical_data_ref'],'data_identity':{'dataset_sha256':staged_plan['canonical_data_ref']['dataset_sha256'],'dataset_path':str(path)},'canonical_replay':{'baseline_metrics':{'profit_factor':1.1},'candidate_metrics':{'profit_factor':1.3,'artifact_dir':'/private/a'}},'walk_forward':{'split_policy':split_policy,'fold_count':2,'fold_metrics':[{'fold_id':1,'candidate_metrics':{'profit_factor':1.2,'data_coverage':[{'source_path':str(path)}]}}]},'validation_trade_results':[{'entry_price':100,'net_pnl':2.0},{'entry_price':101,'net_pnl':3.0}],'next_required_checks':['AFTER_COST_ROBUSTNESS_CHECK','REGIME_AND_SAMPLE_COVERAGE_CHECK'],'human_review_required':True,'automatic_promotion':False,'automatic_strategy_spec_write':False,'runtime_activation':False,'broker_submit':False}\n"
            ),
        }
        self.blobs = {}
        for rel, text in files.items():
            path = self.source_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            self.blobs[rel] = blob(path.read_bytes())

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
        self.dataset = self.input_root / "mnq.csv"
        self.dataset.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2024-01-02T00:00:00+00:00,100,101,99,100,10\n"
            "2024-01-03T00:00:00+00:00,101,102,100,101,11\n"
            "2025-01-02T00:00:00+00:00,102,103,101,102,12\n",
            encoding="utf-8",
        )
        self.spec = {
            "strategy_spec": {
                "strategy_id": "crw_score_multi_mode",
                "symbol": "MNQ",
                "signal_symbol": "MNQ1!",
                "asset_type": "futures",
                "timeframe": "12Min",
                "parameters": {"ENTRY_EXTREME": -2.8},
            }
        }

    def tearDown(self) -> None:
        self.td.cleanup()

    def dataset_node(self) -> dict:
        raw = self.dataset.read_bytes()
        return {
            "relative_path": "mnq.csv",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }

    def base_request(self, capability: str, entry: str, callable_name: str, arguments: dict) -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "auto-job",
            "capability_id": capability,
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": entry,
                "module": entry[:-3].replace("/", "."),
                "callable": callable_name,
                "git_blob_sha1": self.blobs[entry],
            },
            "arguments": arguments,
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def campaign_request(self) -> dict:
        return self.base_request(
            "AUTOTUNER_CAMPAIGN",
            "autotuner_campaign_runner.py",
            "run_campaign_iteration",
            {
                "strategy_spec": self.spec,
                "dataset": self.dataset_node(),
                "tune_parameters": ["ENTRY_EXTREME"],
                "advisory_suggestions": [],
                "batch_size": 4,
                "coarse_points": 5,
                "score_tolerance_fraction": 0.05,
                "state": None,
                "history": None,
            },
        )

    def validation_request(self) -> dict:
        digest = hashlib.sha256(
            json.dumps(
                self.spec["strategy_spec"],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        data_sha = self.dataset_node()["sha256"]
        plan = {
            "schema": "mm.autotuner_governed_validation_staged_execution.v1",
            "state": "PRIMARY_VALIDATION_RUNNABLE",
            "strategy_spec_digest": digest,
            "candidate_label": "candidate_1",
            "candidate_mutation": {"parameter": "ENTRY_EXTREME", "from": -2.8, "to": -3.0},
            "canonical_data_ref": {"dataset_sha256": data_sha, "symbol": "MNQ", "timeframe": "12Min"},
            "runnable_jobs": [
                {"check": "REPLAY_ON_UNTOUCHED_CANONICAL_DATA"},
                {"check": "OUT_OF_SAMPLE_OR_WALK_FORWARD_CHECK"},
            ],
            "blocked_jobs": [],
            "automatic_promotion": False,
            "automatic_strategy_spec_write": False,
            "runtime_activation": False,
            "broker_submit": False,
        }
        return self.base_request(
            "AUTOTUNER_PRIMARY_VALIDATION",
            "autotuner_primary_validation_runner.py",
            "execute_primary_validation",
            {
                "strategy_spec": self.spec,
                "dataset": self.dataset_node(),
                "staged_plan": plan,
                "split_policy": {
                    "start_year": 2023,
                    "test_span_years": 1,
                    "embargo_bars": 1,
                    "purge_bars": 1,
                    "min_test_rows": 1,
                    "warmup_bars": 1,
                },
            },
        )

    def test_campaign_binds_dataset_and_sanitizes_paths_and_errors(self):
        out = mod.execute_request(
            self.campaign_request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
        )["receipt"]
        result = out["result"]
        self.assertEqual(out["capability_id"], "AUTOTUNER_CAMPAIGN")
        self.assertEqual(result["dataset"]["sha256"], self.dataset_node()["sha256"])
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("/private/", encoded)
        self.assertNotIn("artifact_dir", encoded)
        self.assertIn("error_class", encoded)
        self.assertEqual(result["report"]["evaluations"][0]["error_class"], "RuntimeError")
        self.assertEqual(result["next_history"]["results"][0]["error_class"], "ValueError")
        self.assertIn("strategy_backtest_registry.py", result["canonical_dependencies"])
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(out["authority"][key])

    def test_campaign_rejects_digest_drift_and_unbounded_batch(self):
        req = self.campaign_request()
        req["arguments"]["dataset"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)

        req = self.campaign_request()
        req["arguments"]["batch_size"] = 999
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "batch_size"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)

    def test_primary_validation_projects_metrics_but_hashes_raw_trade_rows(self):
        out = mod.execute_request(
            self.validation_request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
        )["receipt"]
        result = out["result"]
        self.assertEqual(out["capability_id"], "AUTOTUNER_PRIMARY_VALIDATION")
        self.assertEqual(result["validation_trade_result_count"], 2)
        self.assertRegex(result["validation_trade_results_sha256"], r"^[0-9a-f]{64}$")
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn("entry_price", encoded)
        self.assertNotIn("dataset_path", encoded)
        self.assertNotIn("artifact_dir", encoded)
        self.assertNotIn(str(self.root), encoded)
        self.assertEqual(result["dataset"]["sha256"], self.dataset_node()["sha256"])
        self.assertIn("model_lab_validation.py", result["canonical_dependencies"])
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(out["authority"][key])

    def test_primary_validation_rejects_plan_dataset_drift_and_split_bounds(self):
        req = self.validation_request()
        req["arguments"]["staged_plan"]["canonical_data_ref"]["dataset_sha256"] = "e" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "dataset identity mismatch"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)

        req = self.validation_request()
        req["arguments"]["split_policy"]["test_span_years"] = 0
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "outside bounds"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)


if __name__ == "__main__":
    unittest.main()
