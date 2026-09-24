from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_canonical_workload_dispatch_v1 as mod


def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class CanonicalNewsReplayDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.source_root = self.root / "mm-source"
        self.source_root.mkdir()
        engine = self.source_root / "news_engine.py"
        engine.write_text(
            "from pathlib import Path\n"
            "class NewsEngine:\n"
            "    def __init__(self,config,data_root):\n"
            "        self.config=config; self.data_root=Path(data_root); self.data_root.mkdir(parents=True,exist_ok=True)\n"
            "    def _normalize_raw_item(self,item):\n"
            "        title=str(item.get('title') or item.get('headline') or '').strip(); url=str(item.get('url') or '')\n"
            "        if not title and not url:return None\n"
            "        out={'title':title,'url':url,'source':str(item.get('source') or 'fixture'),'published_at':item.get('published_at'),'text_snip':str(item.get('summary') or item.get('text_snip') or '')}\n"
            "        if item.get('symbols') is not None:out['symbols']=item.get('symbols')\n"
            "        if item.get('source_type') is not None:out['source_type']=item.get('source_type')\n"
            "        return out\n"
            "    def _load_symbol_universe(self):return sorted(set(self.config.get('NEWS_SYMBOL_UNIVERSE') or []))\n"
            "    def _load_symbol_aliases(self):return dict(self.config.get('NEWS_SYMBOL_ALIASES') or {})\n"
            "    def _load_theme_ticker_map(self):return dict(self.config.get('NEWS_THEME_TICKER_MAP') or {})\n"
            "    def _build_symbol_patterns(self,universe):return {s:[s] for s in universe}\n"
            "    def _build_alias_patterns(self,aliases,universe):return aliases\n"
            "    def _compile_articles(self,entries,patterns,alias_patterns,aliases,themes,universe,max_total):\n"
            "        mapped={s:[] for s in universe}; matched=[]; unmatched=[]\n"
            "        for idx,item in enumerate(entries[:max_total]):\n"
            "            text=(str(item.get('title') or '')+' '+str(item.get('text_snip') or '')).upper(); syms=[]\n"
            "            labeled=item.get('symbols') or []\n"
            "            if isinstance(labeled,str):labeled=[labeled]\n"
            "            for sym in labeled:\n"
            "                sym=str(sym).upper()\n"
            "                if sym in universe and sym not in syms:syms.append(sym)\n"
            "            if not syms:\n"
            "                for sym in universe:\n"
            "                    if sym in text:syms.append(sym)\n"
            "            if not syms:\n"
            "                for sym,vals in aliases.items():\n"
            "                    if sym in universe and any(str(v).upper() in text for v in vals):syms.append(sym)\n"
            "            if not syms:\n"
            "                unmatched.append({'title':item.get('title'),'url':item.get('url'),'source':item.get('source'),'published_at':item.get('published_at')}); continue\n"
            "            matched.append({'title':item.get('title'),'url':item.get('url'),'source':item.get('source'),'published_at':item.get('published_at'),'symbols':syms,'match_methods':['ticker']})\n"
            "            for sym in syms:\n"
            "                mapped.setdefault(sym,[]).append({'id':f'{idx}-{sym}','symbol':sym,'title':item.get('title'),'url':item.get('url'),'source':item.get('source'),'published_at':item.get('published_at'),'text_snip':item.get('text_snip'),'mention_count':1,'source_domain':'example.com','match_method':'ticker','match_confidence':0.9,'macro_spillover':False})\n"
            "        return mapped,{'matched_items_total':len(matched),'unmatched_items_total':len(unmatched),'matched_items':matched,'unmatched_items':unmatched,'top_unmatched_entities':[{'entity':'Macro','count':len(unmatched)}] if unmatched else []}\n"
            "    def _score_sentiment(self,text):\n"
            "        low=text.lower(); score=9.0 if 'beats' in low or 'raises' in low else (1.0 if 'cuts' in low else 5.0); label='Positive' if score>=6 else ('Negative' if score<=4 else 'Neutral'); return score,label,int(score>5),int(score<5)\n"
            "    def _score_impact(self,text,mention_count,domain):return 8.0 if 'earnings' in text.lower() else 4.0\n"
            "    def _score_confidence(self,text,mention_count,domain):return 0.9\n"
            "    def _relevance_profile(self,method,mention_count,match_confidence=None):return {'relevance_class':'direct','relevance_label':'direct-linked','relevance_action':'full','relevance_weight':1.0,'match_confidence':float(match_confidence or 0.8)}\n"
            "    def _article_quality_score(self,sentiment,impact,confidence):return round((sentiment+impact)/2,2)\n"
            "    def _themes_for_text(self,text):return ['Earnings'] if 'earnings' in text.lower() else []\n"
            "    def _deterministic_summary(self,title,text):return (title or text)[:120]\n"
            "    def _symbol_relevance_reason(self,row):return 'Direct ticker mention; counted fully.'\n"
            "    def _comparison_fields(self,row):return {'deterministic_score_raw':row['article_quality_score'],'blended_score':row['article_quality_score'],'score_delta':None,'impact_delta':None,'confidence_delta':None}\n"
            "    def _generate_scorecards(self,by_symbol):\n"
            "        rows=[]\n"
            "        for sym,items in by_symbol.items():\n"
            "            if not items:continue\n"
            "            score=round(sum(float(x.get('score') or 0) for x in items)/len(items),2)\n"
            "            rows.append({'symbol':sym,'articles':len(items),'score':score,'avg_relevance':1.0,'avg_match_confidence':0.9,'summary_source':'deterministic','updated_at':'volatile'})\n"
            "        rows.sort(key=lambda x:x['score'],reverse=True)\n"
            "        for i,row in enumerate(rows,1):row['rank']=i;row['percentile']=100.0 if len(rows)==1 else round(((len(rows)-i)/(len(rows)-1))*100,1)\n"
            "        return rows\n",
            encoding="utf-8",
        )
        (self.source_root / "news_publication_time.py").write_text("UNKNOWN_PUBLICATION_IDENTITY='published_at:unknown'\n", encoding="utf-8")
        op = self.source_root / "scripts" / "operator"
        op.mkdir(parents=True)
        (op / "news_replay_probe_14nf.py").write_text("READ_ONLY=True\n", encoding="utf-8")
        self.entry_blob = git_blob_sha1(engine.read_bytes())
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
        self.dataset = self.input_root / "news.json"
        self.dataset.write_text(json.dumps([
            {"title":"NVDA earnings beats estimates","url":"https://example.com/a","source":"Example","published_at":"2026-09-23T12:00:00Z"},
            {"title":"Nvidia raises outlook","url":"https://example.com/b","source":"Example","published_at":"2026-09-23T12:05:00Z"},
            {"title":"Macro rates discussion","url":"https://example.com/c","source":"Example","published_at":"2026-09-23T12:10:00Z"},
            {"title":"Explicit outside universe","url":"https://example.com/d","source":"Example","published_at":"2026-09-23T12:15:00Z","symbols":["TSLA"]},
        ]), encoding="utf-8")
        self.receipt_dir = self.root / "runtime-state"

    def tearDown(self) -> None:
        self.td.cleanup()

    def request(self) -> dict:
        raw = self.dataset.read_bytes()
        return {
            "schema": mod.REQUEST_SCHEMA,
            "job_id": "news-replay-fixture",
            "capability_id": "NEWS_REPLAY_ANALYZE",
            "mmibkr": {"repository": mod.SOURCE_REPOSITORY, "commit": self.commit, "source_archive_sha256": self.archive},
            "entrypoint": {"path":"news_engine.py","module":"news_engine","callable":"NewsEngine","git_blob_sha1":self.entry_blob},
            "arguments": {
                "dataset": {"relative_path":self.dataset.name,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)},
                "symbols": ["NVDA"],
                "symbol_aliases": {"NVDA":["Nvidia"]},
                "theme_ticker_map": {},
                "max_items": 100,
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

    def test_news_replay_emits_deterministic_scorecard_and_hashed_artifacts(self):
        out = self.execute()
        self.assertFalse(out["cache_hit"])
        receipt = out["receipt"]; result = receipt["result"]
        self.assertEqual(result["schema"], "mmibkr.news_replay_analysis.v1")
        self.assertEqual(result["matched_item_count"], 2)
        self.assertEqual(result["unmatched_item_count"], 2)
        self.assertEqual(result["scorecard_count"], 1)
        self.assertEqual(result["scorecards"][0]["symbol"], "NVDA")
        self.assertEqual(result["scorecards"][0]["summary_source"], "deterministic")
        self.assertNotIn("updated_at", result["scorecards"][0])
        self.assertTrue(result["policy"]["deterministic_only"])
        self.assertFalse(result["policy"]["provider_or_rss_acquisition"])
        self.assertFalse(result["policy"]["llm_enrichment"])
        self.assertFalse(result["safety"]["network_acquisition"])
        self.assertFalse(result["safety"]["broker_submit"])
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(str(self.input_root), rendered)
        artifact_root = self.receipt_dir / "artifacts" / receipt["job_fingerprint"]
        self.assertEqual(len(result["artifacts"]), 4)
        for node in result["artifacts"]:
            target = artifact_root / node["relative_path"]
            self.assertTrue(target.is_file())
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), node["sha256"])
        self.assertRegex(result["canonical_dependencies"]["news_engine.py"], r"^[0-9a-f]{40}$")
        self.assertRegex(result["canonical_dependencies"]["news_publication_time.py"], r"^[0-9a-f]{40}$")

    def test_news_replay_requires_receipt_artifact_storage(self):
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "requires receipt_dir"):
            mod.execute_request(
                self.request(), source_root=self.source_root, source_receipt=self.source_receipt, input_root=self.input_root
            )

    def test_network_or_provider_controls_are_not_request_fields(self):
        req = self.request()
        req["arguments"]["rss_url"] = "https://example.com/feed"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "unexpected fields"):
            self.execute(req)

    def test_input_digest_and_path_drift_fail_closed(self):
        req = self.request()
        req["arguments"]["dataset"]["sha256"] = "c" * 64
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "sha256 mismatch"):
            self.execute(req)
        req = self.request()
        req["arguments"]["dataset"]["relative_path"] = "../escape.json"
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "relative_path rejected"):
            self.execute(req)

    def test_alias_and_theme_maps_cannot_escape_explicit_universe(self):
        req = self.request()
        req["arguments"]["symbol_aliases"] = {"TSLA":["Tesla"]}
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "outside universe"):
            self.execute(req)
        req = self.request()
        req["arguments"]["theme_ticker_map"] = {"EV":["TSLA"]}
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "outside universe"):
            self.execute(req)

    def test_cached_news_artifact_tamper_is_detected(self):
        first = self.execute()
        result = first["receipt"]["result"]
        artifact_root = self.receipt_dir / "artifacts" / first["receipt"]["job_fingerprint"]
        second = self.execute()
        self.assertTrue(second["cache_hit"])
        target = artifact_root / result["artifacts"][0]["relative_path"]
        target.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(mod.CanonicalDispatchError, "artifact hash mismatch"):
            self.execute()


if __name__ == "__main__":
    unittest.main()
