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
        self.assertEqual(evidence["source"], "mm_selected_runtime_execution_contract")

    def test_equity_without_hint_retains_stock_fallback(self):
        contract, evidence = mod.contract_request_for_symbol("AMAT", {})
        self.assertIsInstance(contract, Stock)
        self.assertEqual(contract.symbol, "AMAT")
        self.assertEqual(contract.secType, "STK")
        self.assertEqual(contract.exchange, "SMART")
        self.assertEqual(evidence["source"], "public_stock_fallback")

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

    def test_contract_hint_parser_rejects_non_object(self):
        with self.assertRaisesRegex(RuntimeError, "object keyed by symbol"):
            mod.parse_contract_hints("[]")


if __name__ == "__main__":
    unittest.main()
