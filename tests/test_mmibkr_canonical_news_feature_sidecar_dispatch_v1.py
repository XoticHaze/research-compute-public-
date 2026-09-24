from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


POLICY_SOURCE = """import json
DEFAULT_METHOD_WEIGHTS={
 'ticker':1.0,'labeled':1.0,'ibkr':1.0,'explicit_label':1.0,'provider_label':1.0,
 'alias':0.85,'company':0.75,'entity':0.7,'theme':0.25,'macro':0.15,'market':0.15,'sector':0.2,
}
DIRECT_METHODS={'ticker','labeled','ibkr','explicit_label','provider_label'}
ALIAS_METHODS={'alias','company','entity'}
MACRO_METHODS={'macro','market','sector'}
def _split_method_counts(method_counts):
    theme_counts={};direct=alias=macro=other=0;weighted=0.0
    for method,count in method_counts.items():
        m=str(method or '').strip(); low=m.lower(); count=int(count or 0)
        if low.startswith('theme:'):
            theme=m.split(':',1)[1].strip() or 'unknown'; theme_counts[theme]=theme_counts.get(theme,0)+count; weighted+=count*DEFAULT_METHOD_WEIGHTS['theme']
        elif low in DIRECT_METHODS:
            direct+=count; weighted+=count*DEFAULT_METHOD_WEIGHTS.get(low,1.0)
        elif low in ALIAS_METHODS:
            alias+=count; weighted+=count*DEFAULT_METHOD_WEIGHTS.get(low,0.85)
        elif low in MACRO_METHODS:
            macro+=count; weighted+=count*DEFAULT_METHOD_WEIGHTS.get(low,0.15)
        else:
            other+=count; weighted+=count*0.5
    return {'direct_count':direct,'alias_count':alias,'theme_count':sum(theme_counts.values()),'macro_count':macro,'other_count':other,'theme_counts':theme_counts,'weighted_evidence':round(weighted,4)}
def _policy_for_symbol(matched,direct,alias,theme,macro,other):
    evidence=direct+alias; ratio=theme/max(matched,1); theme_only=matched>0 and theme==matched and evidence==0
    if theme_only and matched>=3:return ('theme_context_only_require_direct_for_trade','theme-only multiple',True,True)
    if theme_only:return ('theme_context_only_review','theme-only low sample',True,True)
    if evidence>0 and ratio>=0.5:return ('allow_direct_signal_low_weight_theme_overlay','direct plus theme',False,False)
    if evidence>0:return ('allow_direct_or_alias_signal','direct or alias',False,False)
    if macro>0 and evidence==0:return ('macro_context_only','macro only',False,True)
    if other>0:return ('manual_review_unknown_method','unknown',False,True)
    return ('no_policy_needed','none',False,False)
"""

SIDECAR_SOURCE = """import json
DEFAULT_METHOD_WEIGHTS={
 'ticker':1.0,'labeled':1.0,'ibkr':1.0,'explicit_label':1.0,'provider_label':1.0,
 'alias':0.85,'company':0.75,'entity':0.7,'theme':0.25,'macro':0.15,'market':0.15,'sector':0.2,
}
FEATURE_COLUMNS=[
 'FEATURE_ASOF_UTC','SOURCE_RUN_ID','SYMBOL','NEWS_ARTICLE_COUNT_24H','NEWS_DIRECT_ARTICLE_COUNT_24H',
 'NEWS_ALIAS_ARTICLE_COUNT_24H','NEWS_THEME_ARTICLE_COUNT_24H','NEWS_MACRO_ARTICLE_COUNT_24H',
 'NEWS_DIRECT_SCORE_24H','NEWS_ALIAS_SCORE_24H','NEWS_THEME_SCORE_24H','NEWS_MACRO_CONTEXT_SCORE_24H',
 'NEWS_COMPOSITE_SCORE_24H','NEWS_WEIGHTED_EVIDENCE_24H','NEWS_THEME_ONLY_FLAG','NEWS_DIRECT_REQUIRED_FLAG',
 'NEWS_POLICY','NEWS_TOP_THEME','NEWS_TOP_SOURCE_TYPE','NEWS_TOP_PROVIDER','NEWS_EXAMPLE_TITLES',
]
def _counts(v):
    if isinstance(v,dict):return {str(k):int(x) for k,x in v.items()}
    try:
        x=json.loads(str(v or '')); return {str(k):int(y) for k,y in x.items()} if isinstance(x,dict) else {}
    except Exception:return {}
def _top(v):
    return sorted(v.items(),key=lambda kv:(-int(kv[1]),str(kv[0])))[0][0] if v else ''
def _score_row(row,policy_stub,feature_asof_utc,source_run_id):
    weights=dict(DEFAULT_METHOD_WEIGHTS);weights.update(policy_stub.get('default_method_weights') or {})
    symbol=str(row.get('symbol') or '').upper(); p=(policy_stub.get('symbol_policies') or {}).get(symbol,{})
    matched=int(row.get('matched_articles') or 0); direct=int(row.get('direct_articles') or 0); alias=int(row.get('alias_articles') or 0)
    theme=int(row.get('theme_articles') or 0); macro=int(row.get('macro_articles') or 0)
    theme_only=bool(p.get('theme_only_flag',row.get('theme_only_flag'))); direct_required=bool(p.get('direct_required_for_trade_signal',row.get('direct_required_flag')))
    direct_score=round(direct*weights.get('ticker',1.0),6); alias_score=round(alias*weights.get('alias',0.85),6); theme_score=round(theme*weights.get('theme',0.25),6)
    context=round(theme_score+macro*weights.get('macro',0.15),6)
    composite=direct_score+alias_score
    if theme>0 and not theme_only and not direct_required:composite+=theme_score
    return {
      'FEATURE_ASOF_UTC':feature_asof_utc,'SOURCE_RUN_ID':source_run_id,'SYMBOL':symbol,
      'NEWS_ARTICLE_COUNT_24H':matched,'NEWS_DIRECT_ARTICLE_COUNT_24H':direct,'NEWS_ALIAS_ARTICLE_COUNT_24H':alias,
      'NEWS_THEME_ARTICLE_COUNT_24H':theme,'NEWS_MACRO_ARTICLE_COUNT_24H':macro,
      'NEWS_DIRECT_SCORE_24H':round(direct_score,6),'NEWS_ALIAS_SCORE_24H':round(alias_score,6),
      'NEWS_THEME_SCORE_24H':round(theme_score,6),'NEWS_MACRO_CONTEXT_SCORE_24H':context,
      'NEWS_COMPOSITE_SCORE_24H':round(composite,6),'NEWS_WEIGHTED_EVIDENCE_24H':float(row.get('weighted_evidence') or 0),
      'NEWS_THEME_ONLY_FLAG':theme_only,'NEWS_DIRECT_REQUIRED_FLAG':direct_required,'NEWS_POLICY':str(p.get('policy') or row.get('policy') or ''),
      'NEWS_TOP_THEME':_top(_counts(row.get('theme_counts'))),'NEWS_TOP_SOURCE_TYPE':_top(_counts(row.get('source_types'))),
      'NEWS_TOP_PROVIDER':_top(_counts(row.get('providers'))),'NEWS_EXAMPLE_TITLES':row.get('example_titles',''),
    }
def _build_contract(policy_stub,feature_window_hours):
    return {
      'schema_version':'news_feature_column_contract_14ni.v1','review_only':True,'feature_window_hours':feature_window_hours,
      'primary_key':['FEATURE_ASOF_UTC','SOURCE_RUN_ID','SYMBOL'],'join_key_candidate':['SYMBOL','FEATURE_ASOF_UTC'],
      'time_semantics':{'no_lookahead_rule':'A downstream backtest may use a row only when FEATURE_ASOF_UTC <= bar timestamp.'},
      'method_weights':policy_stub.get('default_method_weights') or {},'do_not_apply_blindly':True,
    }
"""


class CanonicalNewsFeatureSidecarDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        op = self.source_root / "scripts" / "operator"
        op.mkdir(parents=True)
        (self.source_root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
        (op / "__init__.py").write_text("", encoding="utf-8")
        policy = op / "news_theme_weight_review_probe_14nh.py"
        sidecar = op / "news_feature_sidecar_probe_14ni.py"
        policy.write_text(POLICY_SOURCE, encoding="utf-8")
        sidecar.write_text(SIDECAR_SOURCE, encoding="utf-8")
        self.entry_blob = git_blob_sha1(sidecar.read_bytes())
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
        self.articles = self.input_root / "articles.json"
        self.rows = [
            {"symbol":"NVDA","title":"NVDA direct","match_method":"ticker","source_type":"rss","provider":"Reuters"},
            {"symbol":"NVDA","title":"AI theme","match_method":"theme:Crypto","source_type":"rss","provider":"Reuters"},
            {"symbol":"AMD","title":"Advanced Micro Devices","match_method":"alias","source_type":"rss","provider":"AP"},
            {"symbol":"XLE","title":"Energy one","match_method":"theme:Energy","source_type":"rss"},
            {"symbol":"XLE","title":"Energy two","match_method":"theme:Energy","source_type":"rss"},
            {"symbol":"XLE","title":"Energy three","match_method":"theme:Energy","source_type":"rss"},
        ]
        self.articles.write_text(json.dumps(self.rows), encoding="utf-8")
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def descriptor(self, *, scope="input_root", path=None, job_fingerprint=None) -> dict:
        path = path or self.articles
        raw = path.read_bytes()
        node = {
            "scope": scope,
            "relative_path": path.name if scope == "input_root" else "news_replay/articles.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
        if job_fingerprint is not None:
            node["job_fingerprint"] = job_fingerprint
        return node

    def request(self, articles=None) -> dict:
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "news-feature-sidecar-fixture",
            "capability_id": "NEWS_FEATURE_SIDECAR_BUILD",
            "mmibkr": {"repository":mod.SOURCE_REPOSITORY,"commit":self.commit,"source_archive_sha256":self.archive},
            "entrypoint": {
                "path":"scripts/operator/news_feature_sidecar_probe_14ni.py",
                "module":"scripts.operator.news_feature_sidecar_probe_14ni",
                "callable":"_score_row",
                "git_blob_sha1":self.entry_blob,
            },
            "arguments": {
                "articles": articles or self.descriptor(),
                "source_run_id": "20260923T120000Z",
                "feature_asof_utc": "2026-09-23T12:05:00-05:00",
                "feature_window_hours": 24,
                "max_article_rows": 100,
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

    def test_sidecar_preserves_theme_only_safety_and_no_lookahead_contract(self):
        out = self.execute()
        self.assertFalse(out["cache_hit"])
        receipt = out["receipt"]; result = receipt["result"]
        self.assertEqual(result["schema"], "mmibkr.news_feature_sidecar.v1")
        self.assertEqual(result["feature_asof_utc"], "2026-09-23T17:05:00Z")
        self.assertEqual(result["article_row_count"], 6)
        self.assertEqual(result["feature_row_count"], 3)
        self.assertEqual(result["trade_signal_eligible_rows"], 2)
        self.assertEqual(result["context_only_rows"], 1)
        by_symbol = {row["SYMBOL"]: row for row in result["feature_row_sample"]}
        self.assertEqual(by_symbol["NVDA"]["NEWS_COMPOSITE_SCORE_24H"], 1.25)
        self.assertEqual(by_symbol["AMD"]["NEWS_COMPOSITE_SCORE_24H"], 0.85)
        self.assertEqual(by_symbol["XLE"]["NEWS_COMPOSITE_SCORE_24H"], 0.0)
        self.assertTrue(by_symbol["XLE"]["NEWS_THEME_ONLY_FLAG"])
        self.assertTrue(by_symbol["XLE"]["NEWS_DIRECT_REQUIRED_FLAG"])
        self.assertEqual(by_symbol["XLE"]["NEWS_POLICY"], "theme_context_only_require_direct_for_trade")
        self.assertEqual(result["no_lookahead"]["rule"], "FEATURE_ASOF_UTC <= bar_timestamp")
        for key in ("price_bars_read","labels_read","fills_read","pnl_read","backtest_outcomes_read","broker_state_read"):
            self.assertFalse(result["no_lookahead"][key])
        self.assertFalse(result["safety"]["provider_acquisition"])
        self.assertFalse(result["safety"]["strategy_spec_write"])
        self.assertFalse(result["safety"]["live_trading"])
        self.assertRegex(result["canonical_dependencies"]["scripts/operator/news_theme_weight_review_probe_14nh.py"], r"^[0-9a-f]{40}$")
        self.assertRegex(result["canonical_dependencies"]["scripts/operator/news_feature_sidecar_probe_14ni.py"], r"^[0-9a-f]{40}$")
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        artifact_root = self.receipt_dir / "artifacts" / receipt["job_fingerprint"]
        self.assertEqual(len(result["artifacts"]), 6)
        for node in result["artifacts"]:
            target = artifact_root / node["relative_path"]
            self.assertTrue(target.is_file())
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), node["sha256"])

    def test_receipt_artifact_scope_consumes_exact_prior_news_artifact(self):
        fp = "c" * 64
        root = self.receipt_dir / "artifacts" / fp / "news_replay"
        root.mkdir(parents=True)
        path = root / "articles.json"
        path.write_text(json.dumps(self.rows), encoding="utf-8")
        ref = self.descriptor(scope="receipt_artifact", path=path, job_fingerprint=fp)
        result = self.execute(self.request(ref))["receipt"]["result"]
        self.assertEqual(result["source_articles"]["scope"], "receipt_artifact")
        self.assertEqual(result["source_articles"]["job_fingerprint"], fp)
        self.assertEqual(result["feature_row_count"], 3)

    def test_article_digest_path_and_row_bounds_fail_closed(self):
        req = self.request()
        req["arguments"]["articles"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            self.execute(req)

        req = self.request()
        req["arguments"]["articles"]["relative_path"] = "../escape.json"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "relative_path rejected"):
            self.execute(req)

        req = self.request()
        req["arguments"]["max_article_rows"] = 5
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "article row bound exceeded"):
            self.execute(req)

    def test_requires_timezone_receipt_storage_and_rejects_bar_inputs(self):
        req = self.request()
        req["arguments"]["feature_asof_utc"] = "2026-09-23T17:05:00"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "must include timezone"):
            self.execute(req)

        req = self.request()
        req["arguments"]["bar_data"] = {"relative_path":"bars.csv"}
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "unexpected fields"):
            self.execute(req)

        with self.assertRaisesRegex(mod.CanonicalDispatchError, "requires receipt_dir"):
            mod.execute_request(
                self.request(),
                source_root=self.source_root,
                source_receipt=self.source_receipt,
                input_root=self.input_root,
            )

    def test_cached_feature_artifact_tamper_is_detected(self):
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
