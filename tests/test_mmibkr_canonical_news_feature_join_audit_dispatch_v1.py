from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


JOIN_SOURCE = """import csv,json
from datetime import datetime,timezone
def _read_csv(path):
    with open(path,newline='',encoding='utf-8-sig') as h:return list(csv.DictReader(h))
def _dt_to_iso(dt):
    if dt is None:return ''
    if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def _parse_datetime(value):
    text=str(value or '').strip()
    if not text:return None
    try:
        dt=datetime.fromisoformat(text.replace('Z','+00:00'))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:return None
def _extract_ts_from_row(row):
    for key in ('timestamp','datetime','date','time','ts'):
        if key in row:
            dt=_parse_datetime(row.get(key))
            if dt is not None:return dt
    return None
def _read_bar_timestamps(path,max_rows):
    ext=path.suffix.lower();rows_seen=0;timestamps=[]
    if ext=='.csv':
        with open(path,newline='',encoding='utf-8-sig') as h:
            for row in csv.DictReader(h):
                if rows_seen>=max_rows:break
                rows_seen+=1;dt=_extract_ts_from_row(row)
                if dt is not None:timestamps.append(dt)
        status='readable_with_timestamps' if timestamps else 'readable_no_timestamps'
        return timestamps,{'status':status,'rows_seen':rows_seen,'timestamps_seen':len(timestamps),'notes':''}
    if ext=='.json':
        try:payload=json.loads(path.read_text(encoding='utf-8'))
        except Exception:return [],{'status':'parse_error','rows_seen':0,'timestamps_seen':0,'notes':'invalid json'}
        if isinstance(payload,dict):payload=payload.get('rows') or payload.get('data') or []
        if not isinstance(payload,list):payload=[]
        for row in payload[:max_rows]:
            if isinstance(row,dict):
                rows_seen+=1;dt=_extract_ts_from_row(row)
                if dt is not None:timestamps.append(dt)
        status='readable_with_timestamps' if timestamps else 'readable_no_timestamps'
        return timestamps,{'status':status,'rows_seen':rows_seen,'timestamps_seen':len(timestamps),'notes':''}
    return [],{'status':'unsupported_extension','rows_seen':0,'timestamps_seen':0,'notes':'unsupported'}
def _group_sidecar_rows(rows):
    out={}
    for row in rows:
        symbol=str(row.get('SYMBOL') or row.get('symbol') or '').upper().strip()
        if symbol:out.setdefault(symbol,[]).append(row)
    return out
def _to_float(v,default=0.0):
    try:return float(v)
    except Exception:return default
def _representative_sidecar_row(rows):
    return sorted(rows,key=lambda r:(-_to_float(r.get('NEWS_COMPOSITE_SCORE_24H')),-_to_float(r.get('NEWS_MACRO_CONTEXT_SCORE_24H')),str(r.get('SYMBOL'))))[0]
def _build_contract():
    return {
      'schema_version':'news_backtest_join_contract_14nj.v1','review_only':True,
      'join_rule':'FEATURE_ASOF_UTC <= bar timestamp',
      'primary_news_key':['FEATURE_ASOF_UTC','SOURCE_RUN_ID','SYMBOL'],
      'candidate_join_key':['SYMBOL','FEATURE_ASOF_UTC'],
      'downstream_requirement':'use only rows with FEATURE_ASOF_UTC less than or equal to bar timestamp',
      'no_lookahead_warning':'Never forward-fill into earlier bars.'
    }
"""


class CanonicalNewsFeatureJoinAuditDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        op = self.source_root / "scripts" / "operator"
        op.mkdir(parents=True)
        (self.source_root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        (op / "__init__.py").write_text("", encoding="utf-8")
        join = op / "news_feature_backtest_join_audit_14nj.py"
        join.write_text(JOIN_SOURCE, encoding="utf-8")
        self.entry_blob = git_blob_sha1(join.read_bytes())
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
        self.receipt_dir = self.root / "runtime-state"

        self.sidecar_fp = "c" * 64
        sidecar_root = self.receipt_dir / "artifacts" / self.sidecar_fp / "news_feature_sidecar"
        sidecar_root.mkdir(parents=True)
        self.sidecar = sidecar_root / "news_feature_sidecar.json"
        self.sidecar.write_text(json.dumps([
            {
                "FEATURE_ASOF_UTC":"2026-09-23T17:05:00Z","SOURCE_RUN_ID":"20260923T170500Z","SYMBOL":"NVDA",
                "NEWS_COMPOSITE_SCORE_24H":1.25,"NEWS_MACRO_CONTEXT_SCORE_24H":0.25,
                "NEWS_THEME_ONLY_FLAG":False,"NEWS_DIRECT_REQUIRED_FLAG":False,"NEWS_POLICY":"allow_direct_signal_low_weight_theme_overlay",
            },
            {
                "FEATURE_ASOF_UTC":"2026-09-23T17:05:00Z","SOURCE_RUN_ID":"20260923T170500Z","SYMBOL":"XLE",
                "NEWS_COMPOSITE_SCORE_24H":0.0,"NEWS_MACRO_CONTEXT_SCORE_24H":0.75,
                "NEWS_THEME_ONLY_FLAG":True,"NEWS_DIRECT_REQUIRED_FLAG":True,"NEWS_POLICY":"theme_context_only_require_direct_for_trade",
            },
            {
                "FEATURE_ASOF_UTC":"2026-09-23T17:05:00Z","SOURCE_RUN_ID":"20260923T170500Z","SYMBOL":"AMD",
                "NEWS_COMPOSITE_SCORE_24H":0.85,"NEWS_MACRO_CONTEXT_SCORE_24H":0.0,
                "NEWS_THEME_ONLY_FLAG":False,"NEWS_DIRECT_REQUIRED_FLAG":False,"NEWS_POLICY":"allow_direct_or_alias_signal",
            },
        ]), encoding="utf-8")

        self.nvda = self.input_root / "NVDA-15Min.csv"
        self.nvda.write_text(
            "timestamp,open,close\n"
            "2026-09-23T17:00:00Z,1,2\n"
            "2026-09-23T17:10:00Z,2,3\n"
            "2026-09-23T17:20:00Z,3,4\n",
            encoding="utf-8",
        )
        self.xle = self.input_root / "XLE-15Min.csv"
        self.xle.write_text(
            "timestamp,open,close\n"
            "2026-09-23T16:00:00Z,1,2\n"
            "2026-09-23T16:30:00Z,2,3\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.td.cleanup()

    def input_ref(self, path: Path) -> dict:
        raw = path.read_bytes()
        return {"scope":"input_root","relative_path":path.name,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}

    def sidecar_ref(self) -> dict:
        raw = self.sidecar.read_bytes()
        return {
            "scope":"receipt_artifact",
            "job_fingerprint":self.sidecar_fp,
            "relative_path":"news_feature_sidecar/news_feature_sidecar.json",
            "sha256":hashlib.sha256(raw).hexdigest(),
            "bytes":len(raw),
        }

    def request(self) -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "news-feature-join-fixture",
            "capability_id": "NEWS_FEATURE_JOIN_AUDIT",
            "mmibkr": {"repository":mod.SOURCE_REPOSITORY,"commit":self.commit,"source_archive_sha256":self.archive},
            "entrypoint": {
                "path":"scripts/operator/news_feature_backtest_join_audit_14nj.py",
                "module":"scripts.operator.news_feature_backtest_join_audit_14nj",
                "callable":"_read_bar_timestamps",
                "git_blob_sha1":self.entry_blob,
            },
            "arguments": {
                "sidecar":self.sidecar_ref(),
                "bars":{"NVDA":[self.input_ref(self.nvda)],"XLE":[self.input_ref(self.xle)]},
                "max_rows_per_file":1000,
                "preview_limit":10,
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

    def test_join_audit_distinguishes_ready_before_only_and_missing_bars(self):
        out = self.execute()
        self.assertFalse(out["cache_hit"])
        receipt = out["receipt"]; result = receipt["result"]
        self.assertEqual(result["schema"], "mmibkr.news_feature_join_audit.v1")
        self.assertEqual(result["symbol_count"], 3)
        self.assertEqual(result["join_ready_count"], 1)
        self.assertEqual(result["not_ready_count"], 2)
        by_symbol = {row["symbol"]:row for row in result["readiness"]}
        self.assertTrue(by_symbol["NVDA"]["join_ready"])
        self.assertEqual(by_symbol["NVDA"]["join_status"], "join_ready")
        self.assertEqual(by_symbol["NVDA"]["bars_before_asof"], 1)
        self.assertEqual(by_symbol["NVDA"]["bars_at_or_after_asof"], 2)
        self.assertEqual(by_symbol["NVDA"]["first_joinable_bar_utc"], "2026-09-23T17:10:00Z")
        self.assertFalse(by_symbol["XLE"]["join_ready"])
        self.assertEqual(by_symbol["XLE"]["join_status"], "bars_exist_but_all_before_feature_asof")
        self.assertFalse(by_symbol["AMD"]["join_ready"])
        self.assertEqual(by_symbol["AMD"]["join_status"], "no_candidate_bar_files")
        self.assertEqual(len(result["preview"]), 2)
        for row in result["preview"]:
            self.assertTrue(row["join_rule_ok"])
            self.assertGreaterEqual(
                datetime.fromisoformat(row["bar_timestamp_utc"].replace("Z","+00:00")),
                datetime.fromisoformat(row["feature_asof_utc"].replace("Z","+00:00")),
            )
        self.assertEqual(result["join_contract"]["join_rule"], "FEATURE_ASOF_UTC <= bar timestamp")
        self.assertFalse(result["no_lookahead"]["strategy_execution"])
        self.assertFalse(result["no_lookahead"]["labels_read"])
        self.assertFalse(result["no_lookahead"]["bar_acquisition"])
        self.assertFalse(result["safety"]["feature_recompute"])
        self.assertFalse(result["safety"]["live_trading"])
        self.assertRegex(result["canonical_dependencies"]["scripts/operator/news_feature_backtest_join_audit_14nj.py"], r"^[0-9a-f]{40}$")
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        artifact_root = self.receipt_dir / "artifacts" / receipt["job_fingerprint"]
        self.assertEqual(len(result["artifacts"]), 5)
        for node in result["artifacts"]:
            target = artifact_root / node["relative_path"]
            self.assertTrue(target.is_file())
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), node["sha256"])

    def test_bar_digest_and_sidecar_digest_drift_fail_closed(self):
        req = self.request()
        req["arguments"]["bars"]["NVDA"][0]["sha256"] = "d" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            self.execute(req)
        req = self.request()
        req["arguments"]["sidecar"]["sha256"] = "e" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            self.execute(req)

    def test_execution_inputs_and_receipt_storage_are_fail_closed(self):
        req = self.request()
        req["arguments"]["strategy_spec"] = {"strategy_id":"forbidden"}
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "unexpected fields"):
            self.execute(req)
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "receipt_artifact scope requires receipt_dir"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_cached_join_artifact_tamper_is_detected(self):
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
