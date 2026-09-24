from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import mmibkr_intelligence_report_materialize_v1 as mod


class IntelligenceReportMaterializeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.receipt_dir = self.root / "runtime-state"
        self.output_dir = self.root / "report"
        self.commit = "a" * 40
        self.archive = "b" * 64
        self.news_fp = "1" * 64
        self.options_fp = "2" * 64
        self.plan_path = self.receipt_dir / "plan-g13-fixture.json"
        self._build_fixture()

    def tearDown(self) -> None:
        self.td.cleanup()

    def _write_json(self, path: Path, node) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(mod.json_file_bytes(node))

    def _artifact(self, fp: str, relative_path: str, node) -> dict:
        path = self.receipt_dir / "artifacts" / fp / relative_path
        self._write_json(path, node)
        return {
            "relative_path": relative_path,
            "sha256": mod.file_sha256(path),
            "bytes": path.stat().st_size,
        }

    def _job_receipt(self, job_id: str, fp: str, capability: str, result: dict) -> dict:
        receipt = {
            "schema": mod.JOB_SCHEMA,
            "job_id": job_id,
            "job_fingerprint": fp,
            "capability_id": capability,
            "status": "completed",
            "authority": dict(mod.EXPECTED_AUTHORITY),
            "mmibkr": {
                "repository": "XoticHaze/mm-IBKR",
                "commit": self.commit,
                "source_archive_sha256": self.archive,
            },
            "entrypoint": {
                "path": "fixture.py",
                "module": "fixture",
                "callable": "execute",
                "git_blob_sha1": "c" * 40,
            },
            "resources": {"max_wall_seconds": 60, "max_output_bytes": 500000},
            "result_sha256": mod.canonical_sha256(result),
            "result": result,
        }
        self._write_json(self.receipt_dir / "receipts" / f"{fp}.json", receipt)
        return receipt

    def _build_fixture(self, *, options_state: str = "current-live", empty_reason=None) -> None:
        news_articles = [
            {
                "symbol": "NVDA",
                "title": "NVDA earnings beats estimates",
                "source": "Reuters",
                "published_at": "2026-09-23T12:00:00Z",
                "match_method": "ticker",
                "match_confidence": 0.95,
                "relevance_class": "direct",
                "relevance_label": "direct-linked",
                "relevance_action": "full",
                "relevance_weight": 1.0,
                "symbol_relevance_reason": "Direct ticker mention; counted fully.",
                "sentiment_score": 9.0,
                "sentiment_label": "Positive",
                "impact_score": 8.0,
                "confidence": 0.9,
                "score": 8.5,
                "themes": ["Earnings"],
                "summary": "NVDA earnings beats estimates",
                "summary_source": "deterministic",
            }
        ]
        news_scorecards = [
            {
                "symbol": "NVDA",
                "articles": 1,
                "score": 8.5,
                "avg_relevance": 1.0,
                "avg_match_confidence": 0.95,
                "summary_source": "deterministic",
                "rank": 1,
                "percentile": 100.0,
            }
        ]
        news_unmatched = [{"title": "Macro rates discussion", "source": "Reuters"}]
        news_match_summary = {
            "matched_items_total": 1,
            "unmatched_items_total": 1,
            "top_unmatched_entities": [{"entity": "Macro", "count": 1}],
        }
        news_desc = {
            "articles.json": self._artifact(self.news_fp, "news_replay/articles.json", news_articles),
            "scorecards.json": self._artifact(self.news_fp, "news_replay/scorecards.json", news_scorecards),
            "unmatched.json": self._artifact(self.news_fp, "news_replay/unmatched.json", news_unmatched),
            "match_summary.json": self._artifact(
                self.news_fp, "news_replay/match_summary.json", news_match_summary
            ),
        }
        news_result = {
            "schema": "mmibkr.news_replay_analysis.v1",
            "dataset": {"relative_path": "news.json", "sha256": "d" * 64, "bytes": 123},
            "symbols": ["NVDA"],
            "input_item_count": 2,
            "bounded_item_count": 2,
            "normalized_item_count": 2,
            "matched_item_count": 1,
            "unmatched_item_count": 1,
            "matched_article_symbol_rows": 1,
            "scorecard_count": 1,
            "scorecards": news_scorecards,
            "scorecards_sha256": mod.canonical_sha256(news_scorecards),
            "articles_sha256": mod.canonical_sha256(news_articles),
            "top_unmatched_entities": news_match_summary["top_unmatched_entities"],
            "artifact_map": news_desc,
            "artifacts": list(news_desc.values()),
            "canonical_dependencies": {"news_engine.py": "e" * 40},
            "policy": {
                "deterministic_only": True,
                "cross_run_dedupe_applied": False,
                "provider_or_rss_acquisition": False,
                "llm_enrichment": False,
                "labeled_outside_universe": False,
            },
            "safety": {
                "research_only": True,
                "network_acquisition": False,
                **{key: False for key in mod.FORBIDDEN_AUTHORITY_KEYS},
            },
        }

        if options_state == "no-snapshot":
            option_rows = []
            option_summary = {
                "snapshot_state": "no-snapshot",
                "empty_reason": empty_reason,
                "input_row_count": 0,
                "bounded_row_count": 0,
                "analyzed_row_count": 0,
                "unavailable_row_count": 0,
                "call_rows": 0,
                "put_rows": 0,
                "total_notional_usd": 0.0,
                "average_calc_iv": None,
                "reason_counts": {},
                "capture_source": "provider-cache",
                "captured_at": None,
            }
        else:
            option_rows = [
                {
                    "symbol": "AAPL",
                    "expiry": "20261016",
                    "expiry_utc": "2026-10-16T23:59:59Z",
                    "expiry_time_basis": "end_of_utc_day_assumption",
                    "strike": 250.0,
                    "right": "C",
                    "bid": 5.0,
                    "ask": 5.4,
                    "last": 5.1,
                    "price_basis": "bid_ask_mid",
                    "analysis_price": 5.2,
                    "volume": 10,
                    "notional_usd": 5200.0,
                    "underlying_price": 248.0,
                    "as_of_utc": "2026-09-23T20:30:00Z",
                    "time_to_expiry_years": 0.063,
                    "moneyness_pct": 0.806452,
                    "ib_iv": 0.24,
                    "ib_delta": 0.54,
                    "ib_gamma": 0.019,
                    "ib_vega": 11.8,
                    "ib_theta": -2.9,
                    "calc_iv": 0.25,
                    "calc_delta": 0.55,
                    "calc_gamma": 0.02,
                    "calc_vega": 12.0,
                    "calc_theta": -3.0,
                    "comparison": {"calc_iv_minus_ib_iv": 0.01},
                    "status": "analyzed",
                    "reason": None,
                    "reasons": [],
                }
            ]
            option_summary = {
                "snapshot_state": "current-live",
                "empty_reason": None,
                "input_row_count": 1,
                "bounded_row_count": 1,
                "analyzed_row_count": 1,
                "unavailable_row_count": 0,
                "call_rows": 1,
                "put_rows": 0,
                "total_notional_usd": 5200.0,
                "average_calc_iv": 0.25,
                "reason_counts": {},
                "capture_source": "fixture-existing-snapshot",
                "captured_at": "2026-09-23T15:00:00Z",
            }
        option_desc = [
            self._artifact(self.options_fp, "options_snapshot/analytics.json", option_rows),
            self._artifact(self.options_fp, "options_snapshot/summary.json", option_summary),
        ]
        options_result = {
            "schema": "mmibkr.options_snapshot_analysis.v1",
            "dataset": {"relative_path": "options.json", "sha256": "f" * 64, "bytes": 456},
            "as_of_utc": "2026-09-23T20:30:00Z",
            "risk_free_rate": 0.04,
            "snapshot_state": options_state,
            "empty_reason": empty_reason,
            "summary": option_summary,
            "row_sample": option_rows,
            "analytics_sha256": mod.canonical_sha256(option_rows),
            "artifacts": option_desc,
            "canonical_dependencies": {"options_scanner.py": "9" * 40},
            "policy": {
                "snapshot_input_only": True,
                "deterministic_as_of": True,
                "ibkr_acquisition": False,
                "alpaca_acquisition": False,
                "network_acquisition": False,
                "expiry_without_exact_time": "end_of_utc_day_assumption",
            },
            "safety": {
                "research_only": True,
                **{key: False for key in mod.FORBIDDEN_AUTHORITY_KEYS},
            },
        }

        news_receipt = self._job_receipt(
            "news-job", self.news_fp, "NEWS_REPLAY_ANALYZE", news_result
        )
        options_receipt = self._job_receipt(
            "options-job", self.options_fp, "OPTIONS_SNAPSHOT_ANALYZE", options_result
        )
        plan = {
            "schema": mod.PLAN_SCHEMA,
            "plan_id": "g13-fixture",
            "status": "completed",
            "max_parallel": 2,
            "waves": [["news-job", "options-job"]],
            "jobs": {
                "news-job": {
                    "state": "completed",
                    "cache_hit": False,
                    "job_fingerprint": self.news_fp,
                    "receipt_sha256": mod.canonical_sha256(news_receipt),
                },
                "options-job": {
                    "state": "completed",
                    "cache_hit": False,
                    "job_fingerprint": self.options_fp,
                    "receipt_sha256": mod.canonical_sha256(options_receipt),
                },
            },
            "authority": dict(mod.EXPECTED_AUTHORITY),
        }
        self._write_json(self.plan_path, plan)

    def test_materializes_human_readable_deterministic_news_and_options(self):
        receipt = mod.materialize_report(
            plan_receipt_path=self.plan_path,
            receipt_dir=self.receipt_dir,
            output_dir=self.output_dir,
        )
        self.assertEqual(receipt["schema"], mod.MATERIALIZATION_SCHEMA)
        self.assertEqual(receipt["llm_sidecar"]["status"], "not_provided")
        report_path = self.output_dir / "intelligence_report.json"
        html_path = self.output_dir / "intelligence_report.html"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        rendered = html_path.read_text(encoding="utf-8")

        self.assertEqual(report["schema"], mod.REPORT_SCHEMA)
        self.assertEqual(len(report["news"]), 1)
        self.assertEqual(len(report["options"]), 1)
        self.assertFalse(report["designated_llm_policy"]["deterministic_fields_overwritable"])
        self.assertEqual(report["news"][0]["article_evidence"][0]["source"], "Reuters")
        self.assertEqual(report["options"][0]["snapshot_state"], "current-live")
        self.assertEqual(report["options"][0]["analytics_rows"][0]["calc_iv"], 0.25)

        for text in (
            "Reuters",
            "Direct ticker mention; counted fully.",
            "Positive",
            "current-live",
            "Calc IV",
            "0.25",
            "Not provided",
            self.commit,
            self.archive,
        ):
            self.assertIn(text, rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(str(self.root), report_path.read_text(encoding="utf-8"))

        for key, filename in (
            ("deterministic_report", "intelligence_report.json"),
            ("rendered_html", "intelligence_report.html"),
        ):
            node = receipt[key]
            target = self.output_dir / filename
            self.assertEqual(node["bytes"], target.stat().st_size)
            self.assertEqual(node["sha256"], mod.file_sha256(target))

        render_output = os.environ.get("MMIBKR_G13_RENDER_OUTPUT")
        if render_output:
            target = Path(render_output)
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(report_path, target / report_path.name)
            shutil.copy2(html_path, target / html_path.name)
            shutil.copy2(
                self.output_dir / "intelligence_report_materialization.json",
                target / "intelligence_report_materialization.json",
            )

    def test_designated_llm_sidecar_is_hash_bound_separate_and_escaped(self):
        first = mod.materialize_report(
            plan_receipt_path=self.plan_path,
            receipt_dir=self.receipt_dir,
            output_dir=self.output_dir / "without-llm",
        )
        report_sha = first["deterministic_report"]["sha256"]
        llm = {
            "schema": mod.LLM_SCHEMA,
            "deterministic_report_sha256": report_sha,
            "provider": "designated-provider",
            "model": "designated-model",
            "generated_at": "2026-09-24T05:00:00Z",
            "sections": {
                "overview": "Narrative only. <script>alert('x')</script>",
                "risks": "Do not overwrite deterministic evidence.",
            },
        }
        llm_path = self.root / "llm-sidecar.json"
        self._write_json(llm_path, llm)
        second = mod.materialize_report(
            plan_receipt_path=self.plan_path,
            receipt_dir=self.receipt_dir,
            output_dir=self.output_dir / "with-llm",
            llm_sidecar_path=llm_path,
            llm_sidecar_sha256=mod.file_sha256(llm_path),
        )
        self.assertEqual(second["deterministic_report"]["sha256"], report_sha)
        self.assertEqual(second["llm_sidecar"]["status"], "provided")
        deterministic = (self.output_dir / "with-llm" / "intelligence_report.json").read_text(
            encoding="utf-8"
        )
        rendered = (self.output_dir / "with-llm" / "intelligence_report.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Narrative only", deterministic)
        self.assertIn("Narrative only.", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("cannot overwrite deterministic fields", rendered)

    def test_receipt_artifact_and_result_authority_drift_fail_closed(self):
        article_path = self.receipt_dir / "artifacts" / self.news_fp / "news_replay" / "articles.json"
        article_path.write_text("tampered\\n", encoding="utf-8")
        with self.assertRaisesRegex(mod.IntelligenceReportError, "artifact .* mismatch"):
            mod.materialize_report(
                plan_receipt_path=self.plan_path,
                receipt_dir=self.receipt_dir,
                output_dir=self.output_dir,
            )

        self.receipt_dir.unlink(missing_ok=True) if self.receipt_dir.is_file() else None

    def test_options_acquisition_policy_drift_fails_even_with_rehashed_receipt(self):
        receipt_path = self.receipt_dir / "receipts" / f"{self.options_fp}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["result"]["policy"]["ibkr_acquisition"] = True
        receipt["result_sha256"] = mod.canonical_sha256(receipt["result"])
        self._write_json(receipt_path, receipt)

        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        plan["jobs"]["options-job"]["receipt_sha256"] = mod.canonical_sha256(receipt)
        self._write_json(self.plan_path, plan)

        with self.assertRaisesRegex(mod.IntelligenceReportError, "Options snapshot/acquisition policy drift"):
            mod.materialize_report(
                plan_receipt_path=self.plan_path,
                receipt_dir=self.receipt_dir,
                output_dir=self.output_dir,
            )

    def test_unavailable_options_truth_is_rendered_with_reason(self):
        self.receipt_dir = self.root / "runtime-state-unavailable"
        self.output_dir = self.root / "report-unavailable"
        self.plan_path = self.receipt_dir / "plan-g13-fixture.json"
        self._build_fixture(
            options_state="no-snapshot",
            empty_reason="provider snapshot has not been captured",
        )
        mod.materialize_report(
            plan_receipt_path=self.plan_path,
            receipt_dir=self.receipt_dir,
            output_dir=self.output_dir,
        )
        rendered = (self.output_dir / "intelligence_report.html").read_text(encoding="utf-8")
        self.assertIn("no-snapshot", rendered)
        self.assertIn("provider snapshot has not been captured", rendered)

    def test_llm_binding_and_plan_authority_fail_closed(self):
        first = mod.materialize_report(
            plan_receipt_path=self.plan_path,
            receipt_dir=self.receipt_dir,
            output_dir=self.output_dir / "baseline",
        )
        llm = {
            "schema": mod.LLM_SCHEMA,
            "deterministic_report_sha256": "0" * 64,
            "provider": "designated-provider",
            "model": "designated-model",
            "generated_at": "",
            "sections": {"overview": "wrong binding"},
        }
        llm_path = self.root / "bad-llm.json"
        self._write_json(llm_path, llm)
        with self.assertRaisesRegex(mod.IntelligenceReportError, "binding mismatch"):
            mod.materialize_report(
                plan_receipt_path=self.plan_path,
                receipt_dir=self.receipt_dir,
                output_dir=self.output_dir / "bad-llm",
                llm_sidecar_path=llm_path,
                llm_sidecar_sha256=mod.file_sha256(llm_path),
            )

        plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        plan["authority"]["live_trading"] = True
        self._write_json(self.plan_path, plan)
        with self.assertRaisesRegex(mod.IntelligenceReportError, "authority drift"):
            mod.materialize_report(
                plan_receipt_path=self.plan_path,
                receipt_dir=self.receipt_dir,
                output_dir=self.output_dir / "bad-authority",
            )
        self.assertRegex(first["deterministic_report"]["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
