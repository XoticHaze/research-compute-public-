from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalModelLabFirstConsumerDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        operator = self.source_root / "scripts" / "operator"
        operator.mkdir(parents=True)
        (self.source_root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        (operator / "__init__.py").write_text("", encoding="utf-8")

        module = operator / "model_lab_xgboost_first_consumer.py"
        module.write_text(
            "from pathlib import Path\n"
            "def execute(args):\n"
            "    root=Path(args.data_root)\n"
            "    symbol=str(args.symbol).upper()\n"
            "    if args.asset_type=='futures':\n"
            "        stored=symbol[:-2] if symbol.endswith('1!') else symbol\n"
            "        directory=root/'futures'/f'{stored}-CONTINUOUS'\n"
            "    else:\n"
            "        directory=root/'stocks'/symbol\n"
            "    raw=directory/f'{args.timeframe}.csv'\n"
            "    features=directory/f'{args.timeframe}.features.csv'\n"
            "    sidecar=features.with_suffix(features.suffix+'.manifest.json')\n"
            "    assert raw.is_file() and features.is_file() and sidecar.is_file()\n"
            "    assert args.output is None\n"
            "    return {\n"
            "      'schema':'mm.model_lab_xgboost_first_consumer.v1',\n"
            "      'symbol':symbol,'timeframe':args.timeframe,'target_identity':'fixture-target',\n"
            "      'target_horizon_bars':args.horizon_bars,\n"
            "      'matched_window':{'first_timestamp':'2024-01-01T00:00:00+00:00','last_timestamp':'2025-01-01T00:00:00+00:00','oos_rows':500,'fold_count':2,'matrix_content_sha256':'a'*64,'oos_prediction_content_sha256':'b'*64},\n"
            "      'canonical_xgboost':{'metrics':{'mae':0.1,'rmse':0.2,'correlation':0.3},'training_evidence':{'raw_path':str(raw),'feature_path':str(features),'artifact_dir':'/private/model-lab','safety':{'runtime_authority':False}}},\n"
            "      'matched_zero_return_baseline':{'definition':'fixture','metrics':{'mae':0.2,'rmse':0.3,'correlation':None}},\n"
            "      'incremental_predictive_value':{'mae_delta_model_minus_baseline':-0.1,'rmse_delta_model_minus_baseline':-0.1,'interpretation':'negative deltas favor model'},\n"
            "      'economic_evidence':{'status':'EVIDENCE_GAP','reason':'predictive metrics are not capital alpha','promotion_allowed':False},\n"
            "      'safety':{'read_only':True,'runtime_authority':False,'strategy_spec_authority':False,'promotion_authority':False,'order_submission':False,'live_trading_change':False},\n"
            "    }\n",
            encoding="utf-8",
        )
        self.entry_blob = blob(module.read_bytes())

        for rel in (
            "model_lab_training_matrix.py",
            "model_lab_canonical_data.py",
            "model_lab_xgboost.py",
            "model_lab_canonical_trainer.py",
            "model_lab_validation.py",
            "feature_contract.py",
            "predictive_target_spec.py",
        ):
            path = self.source_root / rel
            path.write_text("# fixture dependency\n", encoding="utf-8")

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
        self.raw = self.input_root / "bars.csv"
        self.features = self.input_root / "features.csv"
        self.sidecar = self.input_root / "features-sidecar.json"
        self.raw.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2024-01-01T00:00:00Z,1,2,0,1,10\n",
            encoding="utf-8",
        )
        self.features.write_text(
            "timestamp,RSI_14\n2024-01-01T00:00:00Z,50\n",
            encoding="utf-8",
        )
        self.sidecar.write_text(
            json.dumps({"contract_version": "fixture", "artifact": {"filename": "12Min.features.csv"}}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.td.cleanup()

    def descriptor(self, path: Path) -> dict:
        raw = path.read_bytes()
        return {
            "relative_path": path.relative_to(self.input_root).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }

    def request(self, *, asset_type: str = "futures", symbol: str = "MNQ") -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "model-lab-one",
            "capability_id": "MODEL_LAB_FIRST_CONSUMER",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": "scripts/operator/model_lab_xgboost_first_consumer.py",
                "module": "scripts.operator.model_lab_xgboost_first_consumer",
                "callable": "execute",
                "git_blob_sha1": self.entry_blob,
            },
            "arguments": {
                "asset_type": asset_type,
                "symbol": symbol,
                "timeframe": "12Min",
                "horizon_bars": 5,
                "target_name": "forward_return_h5",
                "start_year": 2024,
                "test_span_years": 1,
                "min_test_rows": 200,
                "inputs": {
                    "raw": self.descriptor(self.raw),
                    "features": self.descriptor(self.features),
                    "feature_sidecar": self.descriptor(self.sidecar),
                },
            },
            "resources": {"max_wall_seconds": 300, "max_output_bytes": 500000},
            "authority": mod.AUTHORITY,
            "forbidden_authorities": dict(mod.FORBIDDEN_AUTHORITY_ASSERTIONS),
        }

    def test_futures_consumer_preserves_predictive_vs_economic_boundary(self):
        out = mod.execute_request(
            self.request(symbol="MNQ1!"),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
        )["receipt"]
        result = out["result"]
        self.assertEqual(out["capability_id"], "MODEL_LAB_FIRST_CONSUMER")
        self.assertEqual(result["economic_evidence"]["status"], "EVIDENCE_GAP")
        self.assertFalse(result["economic_evidence"]["promotion_allowed"])
        self.assertEqual(result["matched_window"]["oos_rows"], 500)
        self.assertEqual(result["governed_inputs"]["raw"]["sha256"], self.descriptor(self.raw)["sha256"])
        self.assertIn("model_lab_training_matrix.py", result["canonical_dependencies"])
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("/private/", encoded)
        self.assertNotIn("raw_path", encoded)
        self.assertNotIn("feature_path", encoded)
        self.assertNotIn("artifact_dir", encoded)
        for key in mod.FORBIDDEN_AUTHORITY_KEYS:
            self.assertFalse(out["authority"][key])

    def test_stock_consumer_reconstructs_stock_layout_without_caller_output_path(self):
        out = mod.execute_request(
            self.request(asset_type="stocks", symbol="AMAT"),
            source_root=self.source_root,
            source_receipt=self.source_receipt,
            input_root=self.input_root,
        )["receipt"]
        result = out["result"]
        self.assertEqual(result["symbol"], "AMAT")
        self.assertEqual(result["timeframe"], "12Min")
        self.assertEqual(set(result["governed_inputs"]), {"raw", "features", "feature_sidecar"})

    def test_input_digest_drift_fails_before_private_consumer(self):
        req = self.request()
        req["arguments"]["inputs"]["features"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_resource_and_model_contract_bounds_fail_closed(self):
        req = self.request()
        req["arguments"]["horizon_bars"] = 0
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "horizon_bars"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

        req = self.request()
        req["arguments"]["asset_type"] = "options"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "asset_type"):
            mod.execute_request(
                req,
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )


if __name__ == "__main__":
    unittest.main()
