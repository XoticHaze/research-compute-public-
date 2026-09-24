from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalCRWBacktestDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        operator = self.source_root / "scripts" / "operator"
        operator.mkdir(parents=True)
        (self.source_root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        (operator / "__init__.py").write_text("", encoding="utf-8")
        module = operator / "crw_backtest_summary_13z.py"
        module.write_text(
            "from pathlib import Path\n"
            "import hashlib, json\n"
            "def run_backtest(payload, data_root):\n"
            "    paths=payload.get('_verified_source_paths') or {}\n"
            "    symbol=(payload.get('symbols') or [payload.get('symbol')])[0]\n"
            "    p=Path(paths[symbol])\n"
            "    raw=p.read_bytes()\n"
            "    assert p.is_file() and Path(data_root).resolve() in p.resolve().parents\n"
            "    artifact_dir=Path(__file__).resolve().parents[2]/'artifacts'/'fixture'\n"
            "    artifact_dir.mkdir(parents=True,exist_ok=True)\n"
            "    (artifact_dir/'trade_rows.csv').write_text('id,entry_ts,exit_ts,net_pnl\\n1,2021-01-01,2021-01-02,10\\n2,2023-01-01,2023-01-02,22\\n',encoding='utf-8')\n"
            "    (artifact_dir/'condition_event_rows.csv').write_text('id,event\\n1,entry\\n2,hold\\n3,exit\\n',encoding='utf-8')\n"
            "    (artifact_dir/'simulation_trade_rows.csv').write_text('id,entry_ts,exit_ts,net_pnl\\n1,2021-01-01,2021-01-02,5\\n2,2023-01-01,2023-01-02,8\\n3,2025-01-01,2025-01-02,15\\n',encoding='utf-8')\n"
            "    (artifact_dir/'simulation_condition_event_rows.csv').write_text('id,event\\n1,entry\\n2,exit\\n',encoding='utf-8')\n"
            "    (artifact_dir/'dca_fill_rows.csv').write_text('tier,fill_ts\\n1,2021-01-01\\n2,2023-01-01\\n',encoding='utf-8')\n"
            "    return {\n"
            "      'contract_version':'crw_backtest_summary_13z.v1','ok':True,'status':'ok',\n"
            "      'strategy_id':payload['strategy_id'],'symbols':[symbol],'timeframe':payload['timeframe'],\n"
            "      'asset_type':payload.get('asset_type','futures'),'parameter_hash':'abc123',\n"
            "      'builder_condition_execution':False,'builder_condition_contract_hash':'','builder_condition_blockers':[],\n"
            "      'total_trades':2,'closed_trade_count':2,'open_trade_count':0,'open_trade_mark_to_market':0.0,\n"
            "      'win_rate':0.5,'profit_factor':1.25,'avg_win':120.0,'avg_loss':-80.0,'gross_pnl':40.0,'net_pnl':32.0,\n"
            "      'max_drawdown':-90.0,'exposure':0.3,'symbol_count':1,'trade_row_count':2,'event_row_count':3,\n"
            "      'data_coverage':[{'symbol':symbol,'source_path':str(p),'rows':3,'sha256':hashlib.sha256(raw).hexdigest()}],\n"
            "      'cost_model':{'commission_per_share':0.0},\n"
            "      'execution_views':{'tv_signal_close':{'execution_view':'tv_signal_close','net_pnl':32.0,'total_trades':2},'simulated_next_bar_open':{'execution_view':'simulated_next_bar_open','net_pnl':28.0,'total_trades':3,'max_drawdown':-70.0}},\n"
            "      'tv_net_pnl':32.0,'simulated_net_pnl':28.0,'simulated_minus_tv_net_pnl':-4.0,\n"
            "      'safety':{'broker_submit':False,'cancel':False,'replace':False,'live_unlock':False,'backtest_only':True},\n"
            "      'trade_rows':[{'id':1},{'id':2}],'condition_event_rows':[{'id':1},{'id':2},{'id':3}],\n"
            "      'simulation_trade_rows':[{'id':1}],'simulation_condition_event_rows':[{'id':1}],\n"
            "      'dca_fill_rows':[{'tier':1}],'chart_rows':[{'close':1.0}],\n"
            "      'symbol_rows':[{'symbol':symbol,'status':'ok','bar_count':77,'event_count':3,'total_trades':2,'net_pnl':32.0,'dca_enabled':True,'dca_trigger_mode':'tiered_previous_buy','data_info':{'source_path':str(p)}}],\n"
            "      'artifact_dir':'artifacts/fixture'\n"
            "    }\n",
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
        self.dataset = self.input_root / "mnq.csv"
        self.dataset.write_text("timestamp,open,high,low,close,volume\n2026-01-01,1,2,0,1,10\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self) -> dict:
        raw = self.dataset.read_bytes()
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "crw-one",
            "capability_id": "CRW_BACKTEST",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": "scripts/operator/crw_backtest_summary_13z.py",
                "module": "scripts.operator.crw_backtest_summary_13z",
                "callable": "run_backtest",
                "git_blob_sha1": self.entry_blob,
            },
            "arguments": {
                "payload": {
                    "strategy_id": "crw_score_multi_mode",
                    "symbols": ["MNQ"],
                    "timeframe": "12Min",
                    "asset_type": "futures",
                    "params": {"ENTRY_EXTREME": -2.8, "DCA_ENABLED": True},
                    "paper_only": True,
                    "live_allowed": False,
                },
                "datasets": {
                    "MNQ": {
                        "relative_path": "mnq.csv",
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw),
                    }
                },
            },
            "resources": {"max_wall_seconds": 300, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_crw_dispatch_verifies_governed_input_and_sanitizes_receipt(self):
        out = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
        )
        receipt = out["receipt"]
        self.assertEqual(receipt["capability_id"], "CRW_BACKTEST")
        result = receipt["result"]
        self.assertEqual(result["net_pnl"], 32.0)
        self.assertEqual(result["total_trades"], 2)
        self.assertEqual(result["governed_inputs"]["MNQ"]["relative_path"], "mnq.csv")
        self.assertNotIn(str(self.input_root), json.dumps(receipt))
        self.assertNotIn("artifact_dir", result)
        self.assertNotIn("source_path", json.dumps(result["data_coverage"]))
        self.assertEqual(result["row_artifact_counts"]["trade_rows"], 2)
        self.assertRegex(result["raw_result_sha256"], r"^[0-9a-f]{64}$")
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(receipt["authority"][key])

    def test_receipt_backed_crw_preserves_full_canonical_evidence_artifacts(self):
        receipt_dir = self.root / "runtime-state"
        first = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=receipt_dir,
        )
        receipt = first["receipt"]
        result = receipt["result"]
        self.assertEqual(result["row_artifact_counts"]["simulation_trade_rows"], 3)
        self.assertEqual(result["row_artifact_counts"]["trade_rows"], 2)
        self.assertEqual(result["symbol_support"][0]["bar_count"], 77)
        self.assertNotIn("data_info", result["symbol_support"][0])
        self.assertNotIn(str(self.input_root), json.dumps(receipt))
        self.assertEqual(set(result["row_artifacts"]), {
            "trade_rows",
            "condition_event_rows",
            "simulation_trade_rows",
            "simulation_condition_event_rows",
            "dca_fill_rows",
        })
        artifact_root = receipt_dir / "artifacts" / receipt["job_fingerprint"]
        for node in result["artifacts"]:
            path = artifact_root / node["relative_path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), node["sha256"])

        second = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
            receipt_dir=receipt_dir,
        )
        self.assertTrue(second["cache_hit"])

        sim = result["row_artifacts"]["simulation_trade_rows"]
        sim_path = artifact_root / sim["relative_path"]
        sim_path.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "artifact hash mismatch"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
                receipt_dir=receipt_dir,
            )

    def test_caller_verified_paths_are_rejected(self):
        req = self.request()
        req["arguments"]["payload"]["_verified_source_paths"] = {"MNQ": "/tmp/evil"}
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "caller-supplied"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)

    def test_dataset_path_traversal_and_digest_drift_fail_closed(self):
        req = self.request()
        req["arguments"]["datasets"]["MNQ"]["relative_path"] = "../mnq.csv"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "relative_path rejected"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)
        req = self.request()
        req["arguments"]["datasets"]["MNQ"]["sha256"] = "c" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)

    def test_requested_symbol_must_have_exact_governed_dataset(self):
        req = self.request()
        req["arguments"]["datasets"] = {"AMAT": req["arguments"]["datasets"]["MNQ"]}
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "missing governed datasets"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)

    def test_execution_authority_field_fails_closed(self):
        req = self.request()
        req["arguments"]["payload"]["live_allowed"] = True
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "forbids execution authority"):
            mod.execute_request(req, source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root)

    def test_nested_private_scripts_module_wins_over_public_scripts_package(self):
        out = mod.execute_request(
            self.request(),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
        )
        self.assertTrue(out["receipt"]["result"]["ok"])
        loaded = __import__("sys").modules.get("scripts.operator.crw_backtest_summary_13z")
        self.assertIsNotNone(loaded)
        self.assertEqual(Path(loaded.__file__).resolve(), (self.source_root / "scripts/operator/crw_backtest_summary_13z.py").resolve())


if __name__ == "__main__":
    unittest.main()
