from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalOptionsSnapshotDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()
        scanner = self.source_root / "options_scanner.py"
        scanner.write_text(
            "class OptionsScanner:\n"
            "    calls=[]\n"
            "    @classmethod\n"
            "    def analyze_snapshot_rows(cls,rows,**kwargs):\n"
            "        cls.calls.append({'rows':rows,'kwargs':kwargs})\n"
            "        state=kwargs['snapshot_state']; empty=kwargs.get('empty_reason') or ''\n"
            "        if state in {'watch-only-no-history','no-snapshot'} and rows:\n"
            "            raise ValueError('options snapshot_state contradicts non-empty dataset')\n"
            "        if not rows and state in {'current-live','watch-only-last-known'} and not empty:\n"
            "            raise ValueError('options empty_reason is required for empty available-state snapshot')\n"
            "        if rows:\n"
            "            analyzed=[\n"
            "                {'row_index':0,'symbol':'AAPL','expiry':'20261016','expiry_utc':'2026-10-16T23:59:59Z','expiry_time_basis':'end_of_utc_day_assumption','strike':250.0,'right':'C','bid':5.0,'ask':5.4,'last':5.1,'price_basis':'bid_ask_mid','analysis_price':5.2,'volume':10,'notional_usd':5200.0,'underlying_price':248.0,'as_of_utc':kwargs['as_of_utc'],'time_to_expiry_years':0.06,'moneyness_pct':0.806452,'ib_iv':0.24,'calc_iv':0.25,'calc_delta':0.55,'calc_gamma':0.02,'calc_vega':12.0,'calc_theta':-3.0,'comparison':{'calc_iv_minus_ib_iv':0.01},'status':'analyzed','reason':None,'reasons':[]},\n"
            "                {'row_index':1,'symbol':'AAPL','expiry':None,'expiry_utc':'2026-10-16T20:00:00Z','expiry_time_basis':'exact','strike':245.0,'right':'P','bid':0.0,'ask':0.0,'last':4.2,'price_basis':'last','analysis_price':4.2,'volume':0,'notional_usd':420.0,'underlying_price':248.0,'as_of_utc':kwargs['as_of_utc'],'time_to_expiry_years':0.06,'moneyness_pct':-1.209677,'calc_iv':0.25,'calc_delta':-0.45,'calc_gamma':0.02,'calc_vega':12.0,'calc_theta':-3.0,'comparison':{},'status':'analyzed','reason':None,'reasons':[]},\n"
            "                {'row_index':2,'symbol':'AAPL','status':'unavailable','reason':'expired_at_as_of','reasons':['expired_at_as_of']},\n"
            "                {'row_index':3,'symbol':'AAPL','status':'unavailable','reason':'option_price_unavailable','reasons':['option_price_unavailable']},\n"
            "            ]\n"
            "        else: analyzed=[]\n"
            "        analyzed_count=sum(1 for r in analyzed if r.get('status')=='analyzed')\n"
            "        summary={'snapshot_state':state,'empty_reason':empty or None,'input_row_count':len(rows),'bounded_row_count':len(rows),'analyzed_row_count':analyzed_count,'unavailable_row_count':len(analyzed)-analyzed_count,'call_rows':2 if rows else 0,'put_rows':1 if rows else 0,'total_notional_usd':5620.0 if rows else 0.0,'average_calc_iv':0.25 if rows else None,'reason_counts':{},'capture_source':kwargs.get('capture_source'),'captured_at':kwargs.get('captured_at')}\n"
            "        return {'schema':'mmibkr.options_snapshot_analysis.v1','as_of_utc':kwargs['as_of_utc'],'risk_free_rate':kwargs['risk_free_rate'],'snapshot_state':state,'empty_reason':empty or None,'summary':summary,'rows':analyzed,'policy':{'snapshot_input_only':True,'deterministic_as_of':True,'ibkr_acquisition':False,'alpaca_acquisition':False,'network_acquisition':False,'expiry_without_exact_time':'end_of_utc_day_assumption'},'safety':{'research_only':True,'broker_submit':False,'broker_cancel':False,'broker_flatten':False,'strategy_spec_write':False,'runtime_activation':False,'promotion_mutation':False,'live_trading':False}}\n",
            encoding="utf-8",
        )
        self.entry_blob = git_blob_sha1(scanner.read_bytes())
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
        self.dataset = self.input_root / "options.json"
        self.dataset.write_text(json.dumps({
            "capture_source": "fixture-existing-snapshot",
            "ts": "2026-09-23T15:00:00Z",
            "rows": [
                {
                    "symbol":"AAPL","expiry":"20261016","strike":250.0,"right":"C",
                    "bid":5.0,"ask":5.4,"last":5.1,"volume":10,"undPrice":248.0,
                    "ib_iv":0.24,"ib_delta":0.54,"ib_gamma":0.019,"ib_vega":11.8,"ib_theta":-2.9,
                },
                {
                    "symbol":"AAPL","expiry_utc":"2026-10-16T20:00:00Z","strike":245.0,"right":"PUT",
                    "bid":0.0,"ask":0.0,"last":4.2,"volume":0,"underlying_price":248.0,
                },
                {
                    "symbol":"AAPL","expiry":"20260901","strike":250.0,"right":"C",
                    "bid":1.0,"ask":1.2,"last":1.1,"volume":2,"undPrice":248.0,
                },
                {
                    "symbol":"AAPL","expiry":"20261016","strike":260.0,"right":"C",
                    "bid":0.0,"ask":0.0,"last":0.0,"volume":0,"undPrice":248.0,
                },
            ],
        }), encoding="utf-8")
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self) -> dict:
        raw = self.dataset.read_bytes()
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "options-snapshot-fixture",
            "capability_id": "OPTIONS_SNAPSHOT_ANALYZE",
            "mmibkr": {
                "repository": mod.SOURCE_REPOSITORY,
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path":"options_scanner.py","module":"options_scanner","callable":"OptionsScanner",
                "git_blob_sha1": self.entry_blob,
            },
            "arguments": {
                "dataset": {
                    "relative_path": self.dataset.name,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                },
                "as_of_utc": "2026-09-23T15:30:00-05:00",
                "risk_free_rate": 0.04,
                "snapshot_state": "current-live",
                "empty_reason": "",
                "max_rows": 100,
            },
            "resources": {"max_wall_seconds":60,"max_output_bytes":500000},
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

    def test_snapshot_analysis_preserves_truth_and_computes_pure_analytics(self):
        out = self.execute()
        self.assertFalse(out["cache_hit"])
        receipt = out["receipt"]; result = receipt["result"]
        self.assertEqual(result["schema"], "mmibkr.options_snapshot_analysis.v1")
        self.assertEqual(result["as_of_utc"], "2026-09-23T20:30:00Z")
        self.assertEqual(result["snapshot_state"], "current-live")
        self.assertEqual(result["summary"]["capture_source"], "fixture-existing-snapshot")
        self.assertEqual(result["summary"]["input_row_count"], 4)
        self.assertEqual(result["summary"]["analyzed_row_count"], 2)
        self.assertEqual(result["summary"]["unavailable_row_count"], 2)
        first = result["row_sample"][0]
        self.assertEqual(first["price_basis"], "bid_ask_mid")
        self.assertEqual(first["analysis_price"], 5.2)
        self.assertEqual(first["notional_usd"], 5200.0)
        self.assertEqual(first["calc_iv"], 0.25)
        self.assertEqual(first["calc_delta"], 0.55)
        self.assertAlmostEqual(first["comparison"]["calc_iv_minus_ib_iv"], 0.01)
        self.assertEqual(first["expiry_time_basis"], "end_of_utc_day_assumption")
        second = result["row_sample"][1]
        self.assertEqual(second["right"], "P")
        self.assertEqual(second["price_basis"], "last")
        self.assertEqual(second["expiry_time_basis"], "exact")
        self.assertIn("expired_at_as_of", result["row_sample"][2]["reasons"])
        self.assertIn("option_price_unavailable", result["row_sample"][3]["reasons"])
        self.assertTrue(result["policy"]["snapshot_input_only"])
        self.assertFalse(result["policy"]["ibkr_acquisition"])
        self.assertFalse(result["policy"]["alpaca_acquisition"])
        self.assertFalse(result["safety"]["broker_submit"])
        self.assertRegex(result["canonical_dependencies"]["options_scanner.py"], r"^[0-9a-f]{40}$")
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        artifact_root = self.receipt_dir / "artifacts" / receipt["job_fingerprint"]
        self.assertEqual(len(result["artifacts"]), 2)
        for node in result["artifacts"]:
            path = artifact_root / node["relative_path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), node["sha256"])

    def test_public_adapter_delegates_analysis_policy_to_canonical_owner(self):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertIn("analyze_snapshot_rows", source)
        self.assertNotIn("def _options_quote_basis", source)
        self.assertNotIn("def _options_expiry_utc", source)
        self.assertNotIn("def _finite_number(value:Any)->float|None:", source)

        result = self.execute()["receipt"]["result"]
        self.assertEqual(result["summary"]["capture_source"], "fixture-existing-snapshot")
        self.assertEqual(result["summary"]["captured_at"], "2026-09-23T15:00:00Z")
        self.assertEqual(result["as_of_utc"], "2026-09-23T20:30:00Z")

    def test_canonical_owner_authority_drift_fails_closed(self):
        scanner = self.source_root / "options_scanner.py"
        text = scanner.read_text(encoding="utf-8")
        text = text.replace("'network_acquisition':False", "'network_acquisition':True")
        scanner.write_text(text, encoding="utf-8")
        req = self.request()
        req["entrypoint"]["git_blob_sha1"] = git_blob_sha1(scanner.read_bytes())
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "acquisition authority drift"):
            self.execute(req)

    def test_unavailable_truth_states_are_explicit_not_zero_filled(self):
        self.dataset.write_text(json.dumps({"capture_source":"none","rows":[]}), encoding="utf-8")
        req = self.request()
        req["arguments"]["snapshot_state"] = "no-snapshot"
        req["arguments"]["empty_reason"] = "provider snapshot has not been captured"
        raw = self.dataset.read_bytes()
        req["arguments"]["dataset"]["sha256"] = hashlib.sha256(raw).hexdigest()
        req["arguments"]["dataset"]["bytes"] = len(raw)
        result = self.execute(req)["receipt"]["result"]
        self.assertEqual(result["summary"]["input_row_count"], 0)
        self.assertEqual(result["summary"]["analyzed_row_count"], 0)
        self.assertEqual(result["snapshot_state"], "no-snapshot")
        self.assertEqual(result["empty_reason"], "provider snapshot has not been captured")

    def test_truth_state_contradiction_and_missing_empty_reason_fail_closed(self):
        req = self.request()
        req["arguments"]["snapshot_state"] = "no-snapshot"
        req["arguments"]["empty_reason"] = "none"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "contradicts non-empty"):
            self.execute(req)

        self.dataset.write_text("[]", encoding="utf-8")
        req = self.request()
        raw = self.dataset.read_bytes()
        req["arguments"]["dataset"]["sha256"] = hashlib.sha256(raw).hexdigest()
        req["arguments"]["dataset"]["bytes"] = len(raw)
        req["arguments"]["snapshot_state"] = "watch-only-last-known"
        req["arguments"]["empty_reason"] = ""
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "empty_reason is required"):
            self.execute(req)

    def test_acquisition_controls_are_not_request_fields_and_asof_must_be_zoned(self):
        req = self.request()
        req["arguments"]["reqMktData"] = True
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "unexpected fields"):
            self.execute(req)
        req = self.request()
        req["arguments"]["as_of_utc"] = "2026-09-23T20:30:00"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "must include timezone"):
            self.execute(req)

    def test_requires_receipt_storage_and_detects_cached_artifact_tamper(self):
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "requires receipt_dir"):
            mod.execute_request(
                self.request(), source_root=self.source_root,
                source_receipt=self.source_receipt, input_root=self.input_root,
            )
        first = self.execute()
        second = self.execute()
        self.assertTrue(second["cache_hit"])
        result = first["receipt"]["result"]
        artifact_root = self.receipt_dir / "artifacts" / first["receipt"]["job_fingerprint"]
        target = artifact_root / result["artifacts"][0]["relative_path"]
        target.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "artifact hash mismatch"):
            self.execute()


if __name__ == "__main__":
    unittest.main()
