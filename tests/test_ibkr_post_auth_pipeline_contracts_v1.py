from __future__ import annotations

import json
import unittest

from ib_insync import Stock

from scripts import ibkr_post_auth_pipeline_v1 as mod


class PostAuthPipelineContractTests(unittest.TestCase):
    def test_exact_mm_futures_contract_is_preserved(self):
        hints = mod.parse_contract_hints(json.dumps({
            "MNQ": {
                "conId": 793356225,
                "symbol": "MNQ",
                "secType": "FUT",
                "exchange": "CME",
                "currency": "USD",
                "localSymbol": "MNQU6",
            }
        }))
        contract, evidence = mod.contract_request_for_symbol("MNQ", hints)
        self.assertEqual(contract.conId, 793356225)
        self.assertEqual(contract.symbol, "MNQ")
        self.assertEqual(contract.secType, "FUT")
        self.assertEqual(contract.exchange, "CME")
        self.assertEqual(contract.currency, "USD")
        self.assertEqual(contract.localSymbol, "MNQU6")
        self.assertEqual(evidence["source"], "mm_exact_contract_hint")

    def test_equity_without_hint_retains_stock_fallback(self):
        contract, evidence = mod.contract_request_for_symbol("AMAT", {})
        self.assertIsInstance(contract, Stock)
        self.assertEqual(contract.symbol, "AMAT")
        self.assertEqual(contract.secType, "STK")
        self.assertEqual(contract.exchange, "SMART")
        self.assertEqual(evidence["source"], "public_stock_fallback")

    def test_exact_mm_option_contract_is_preserved(self):
        hints = mod.parse_contract_hints(json.dumps({
            "SPY": {
                "conId": 999001,
                "symbol": "SPY",
                "secType": "OPT",
                "exchange": "SMART",
                "currency": "USD",
                "lastTradeDateOrContractMonth": "20261016",
                "strike": 600.0,
                "right": "C",
                "multiplier": "100",
                "tradingClass": "SPY",
            }
        }))
        contract, evidence = mod.contract_request_for_symbol("SPY", hints)
        self.assertEqual(contract.conId, 999001)
        self.assertEqual(contract.secType, "OPT")
        self.assertEqual(contract.strike, 600.0)
        self.assertEqual(contract.right, "C")
        self.assertEqual(contract.multiplier, "100")
        self.assertEqual(contract.lastTradeDateOrContractMonth, "20261016")
        self.assertEqual(evidence["source"], "mm_exact_contract_hint")

    def test_option_hint_requires_exact_right_and_strike(self):
        with self.assertRaisesRegex(RuntimeError, "option right/strike"):
            mod.parse_contract_hints(json.dumps({
                "SPY": {
                    "conId": 999001,
                    "symbol": "SPY",
                    "secType": "OPT",
                    "exchange": "SMART",
                    "currency": "USD",
                    "lastTradeDateOrContractMonth": "20261016",
                }
            }))

    def test_non_stock_hint_requires_explicit_conid(self):
        with self.assertRaisesRegex(RuntimeError, "explicit conId required"):
            mod.parse_contract_hints(json.dumps({
                "MNQ": {
                    "symbol": "MNQ",
                    "secType": "FUT",
                    "exchange": "CME",
                    "currency": "USD",
                    "localSymbol": "MNQU6",
                }
            }))

    def test_hint_symbol_mismatch_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "symbol mismatch"):
            mod.parse_contract_hints(json.dumps({
                "MNQ": {
                    "symbol": "MES",
                    "secType": "FUT",
                    "conId": 123,
                }
            }))

    def test_exact_mm_bar_requests_preserve_source_target_and_ibkr_request(self):
        requests = mod.parse_bar_requests(json.dumps({
            "MNQ": [{
                "source_timeframe": "1Min",
                "target_timeframe": "12Min",
                "bar_size_setting": "1 min",
                "duration_str": "1 D",
            }],
            "AMAT": [{
                "source_timeframe": "15Min",
                "target_timeframe": "15Min",
                "bar_size_setting": "15 mins",
                "duration_str": "2 W",
            }],
        }), ["MNQ", "AMAT"])
        self.assertEqual(requests["MNQ"][0]["source_timeframe"], "1Min")
        self.assertEqual(requests["MNQ"][0]["target_timeframe"], "12Min")
        self.assertEqual(requests["MNQ"][0]["bar_size_setting"], "1 min")
        self.assertEqual(requests["MNQ"][0]["duration_str"], "1 D")
        self.assertEqual(requests["MNQ"][0]["end_date_time_utc"], "")
        self.assertEqual(requests["AMAT"][0]["bar_size_setting"], "15 mins")

    def test_exact_historical_chunk_end_times_allow_same_request_shape_at_distinct_boundaries(self):
        requests = mod.parse_bar_requests(json.dumps({
            "MNQ": [
                {
                    "source_timeframe": "1Min",
                    "target_timeframe": "12Min",
                    "bar_size_setting": "1 min",
                    "duration_str": "1 D",
                    "end_date_time_utc": "2026-09-17T21:00:00Z",
                },
                {
                    "source_timeframe": "1Min",
                    "target_timeframe": "12Min",
                    "bar_size_setting": "1 min",
                    "duration_str": "1 D",
                    "end_date_time_utc": "2026-09-18T21:00:00+00:00",
                },
            ],
        }), ["MNQ"])
        self.assertEqual(len(requests["MNQ"]), 2)
        self.assertEqual(
            requests["MNQ"][0]["end_date_time_utc"],
            "2026-09-17T21:00:00Z",
        )
        self.assertEqual(
            requests["MNQ"][1]["end_date_time_utc"],
            "2026-09-18T21:00:00Z",
        )
        end = mod._ibkr_history_end(requests["MNQ"][0]["end_date_time_utc"])
        self.assertEqual(end.isoformat(), "2026-09-17T21:00:00+00:00")

    def test_exact_historical_chunk_end_requires_timezone_and_remains_duplicate_safe(self):
        with self.assertRaisesRegex(RuntimeError, "explicit timezone"):
            mod.parse_bar_requests(json.dumps({
                "MNQ": [{
                    "source_timeframe": "1Min",
                    "target_timeframe": "12Min",
                    "bar_size_setting": "1 min",
                    "duration_str": "1 D",
                    "end_date_time_utc": "2026-09-17T21:00:00",
                }],
            }), ["MNQ"])

        duplicate = {
            "source_timeframe": "1Min",
            "target_timeframe": "12Min",
            "bar_size_setting": "1 min",
            "duration_str": "1 D",
            "end_date_time_utc": "2026-09-17T21:00:00Z",
        }
        with self.assertRaisesRegex(RuntimeError, "duplicate bar request"):
            mod.parse_bar_requests(
                json.dumps({"MNQ": [duplicate, dict(duplicate)]}),
                ["MNQ"],
            )

    def test_pipeline_uses_private_supplied_historical_end_without_public_time_selection(self):
        from pathlib import Path
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertIn('end_date_time_utc = str(bar_request.get("end_date_time_utc") or "")', source)
        self.assertIn("request_end = _ibkr_history_end(end_date_time_utc)", source)
        self.assertIn("endDateTime=request_end", source)

    def test_seconds_bar_requests_are_admitted_only_in_safe_step_size_pairs(self):
        requests = mod.parse_bar_requests(json.dumps({
            "MNQ": [{
                "source_timeframe": "1Min",
                "target_timeframe": "12Min",
                "bar_size_setting": "1 min",
                "duration_str": "120 S",
            }],
            "AMAT": [{
                "source_timeframe": "15Min",
                "target_timeframe": "15Min",
                "bar_size_setting": "15 mins",
                "duration_str": "1800 S",
            }],
        }), ["MNQ", "AMAT"])
        self.assertEqual(requests["MNQ"][0]["duration_str"], "120 S")
        self.assertEqual(requests["AMAT"][0]["duration_str"], "1800 S")

        with self.assertRaisesRegex(RuntimeError, "seconds duration/bar size combination rejected"):
            mod.parse_bar_requests(json.dumps({
                "AMAT": [{
                    "source_timeframe": "15Min",
                    "target_timeframe": "15Min",
                    "bar_size_setting": "15 mins",
                    "duration_str": "120 S",
                }]
            }), ["AMAT"])

        with self.assertRaisesRegex(RuntimeError, "duration rejected"):
            mod.parse_bar_requests(json.dumps({
                "MNQ": [{
                    "source_timeframe": "1Min",
                    "target_timeframe": "12Min",
                    "bar_size_setting": "1 min",
                    "duration_str": "61 S",
                }]
            }), ["MNQ"])

    def test_pipeline_source_emits_per_request_and_phase_latency_evidence(self):
        from pathlib import Path
        source = Path(mod.__file__).read_text(encoding="utf-8")
        for token in (
            "request_elapsed_ms",
            "contract_qualification_elapsed_ms",
            "symbol_elapsed_ms",
            '"latency_ms"',
            '"historical_market_data_sum"',
            '"pipeline_total"',
        ):
            self.assertIn(token, source)

    def test_explicit_bar_requests_fail_closed_on_missing_symbol_or_unsafe_window(self):
        with self.assertRaisesRegex(RuntimeError, "missing requested symbols"):
            mod.parse_bar_requests(json.dumps({
                "MNQ": [{
                    "source_timeframe": "1Min",
                    "target_timeframe": "12Min",
                    "bar_size_setting": "1 min",
                    "duration_str": "1 D",
                }]
            }), ["MNQ", "AMAT"])

        with self.assertRaisesRegex(RuntimeError, "duration rejected"):
            mod.parse_bar_requests(json.dumps({
                "MNQ": [{
                    "source_timeframe": "1Min",
                    "target_timeframe": "12Min",
                    "bar_size_setting": "1 min",
                    "duration_str": "99 Y",
                }]
            }), ["MNQ"])

    def test_bar_request_parser_rejects_unknown_fields_and_unrequested_symbol(self):
        with self.assertRaisesRegex(RuntimeError, "field set mismatch"):
            mod.parse_bar_requests(json.dumps({
                "MNQ": [{
                    "source_timeframe": "1Min",
                    "target_timeframe": "12Min",
                    "bar_size_setting": "1 min",
                    "duration_str": "1 D",
                    "action": "BUY",
                }]
            }), ["MNQ"])
        with self.assertRaisesRegex(RuntimeError, "unrequested symbol"):
            mod.parse_bar_requests(json.dumps({
                "MES": [{
                    "source_timeframe": "1Min",
                    "target_timeframe": "12Min",
                    "bar_size_setting": "1 min",
                    "duration_str": "1 D",
                }]
            }), ["MNQ"])

    def test_exact_contract_quote_reports_realtime_bid_ask_without_mutation(self):
        class Ticker:
            marketDataType = 1
            bid = 100.0
            ask = 100.25
            last = 100.1
            def marketPrice(self):
                return 100.125

        class FakeIB:
            def __init__(self):
                self.ticker = Ticker()
                self.requested_type = None
                self.requested_contract = None
                self.cancelled_contract = None
            def reqMarketDataType(self, value):
                self.requested_type = value
            def reqMktData(self, contract, generic, snapshot, regulatory):
                self.requested_contract = contract
                return self.ticker
            def sleep(self, seconds):
                return None
            def cancelMktData(self, contract):
                self.cancelled_contract = contract

        ib = FakeIB()
        contract = Stock("AMAT", "SMART", "USD")
        quote = mod.sample_exact_contract_quote(ib, contract, timeout_sec=0.2, poll_interval_sec=0.05)
        self.assertEqual(ib.requested_type, 1)
        self.assertIs(ib.requested_contract, contract)
        self.assertIs(ib.cancelled_contract, contract)
        self.assertEqual(quote["bid"], 100.0)
        self.assertEqual(quote["ask"], 100.25)
        self.assertTrue(quote["bid_ask_available"])
        self.assertTrue(quote["executable_quote_available"])
        self.assertFalse(quote["route_selected_by_public"])
        self.assertFalse(quote["contract_selected_by_public"])
        self.assertFalse(quote["broker_mutation"])
        self.assertGreaterEqual(quote["request_elapsed_ms"], 0.0)

    def test_delayed_bid_ask_is_diagnostic_not_executable(self):
        class Ticker:
            marketDataType = 3
            bid = 100.0
            ask = 100.25
            last = 100.1
            def marketPrice(self):
                return 100.125

        class FakeIB:
            def reqMarketDataType(self, value):
                pass
            def reqMktData(self, contract, generic, snapshot, regulatory):
                return Ticker()
            def sleep(self, seconds):
                pass
            def cancelMktData(self, contract):
                pass

        quote = mod.sample_exact_contract_quote(
            FakeIB(),
            Stock("AMAT", "SMART", "USD"),
            timeout_sec=0.2,
            poll_interval_sec=0.05,
        )
        self.assertTrue(quote["bid_ask_available"])
        self.assertFalse(quote["executable_quote_available"])
        self.assertEqual(quote["effective_market_data_type"], 3)

    def test_quote_sampler_source_has_no_order_or_route_selection(self):
        from pathlib import Path
        source = Path(mod.__file__).read_text(encoding="utf-8")
        start = source.index("def sample_exact_contract_quote(")
        end = source.index("\ndef main() -> int:", start)
        block = source[start:end]
        self.assertIn("reqMktData(", block)
        self.assertIn("cancelMktData(", block)
        self.assertNotIn("placeOrder(", block)
        self.assertNotIn("reqGlobalCancel", block)
        self.assertIn('"route_selected_by_public": False', block)
        self.assertIn('"contract_selected_by_public": False', block)

    def test_contract_hint_parser_rejects_non_object(self):
        with self.assertRaisesRegex(RuntimeError, "object keyed by symbol"):
            mod.parse_contract_hints("[]")


if __name__ == "__main__":
    unittest.main()
