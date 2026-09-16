from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.ibkr_instrument_spec_v1 import InstrumentSpec, parse_instrument_specs, stock_specs


class InstrumentSpecTests(unittest.TestCase):
    def test_stock_defaults_do_not_create_roll_semantics(self):
        [spec] = stock_specs(["amat"])
        self.assertEqual(spec.symbol, "AMAT")
        self.assertEqual(spec.asset_type, "STK")
        self.assertEqual(spec.exchange, "SMART")
        self.assertFalse(spec.receipt()["implicit_roll_selection"])

    def test_future_requires_explicit_contract_identity(self):
        with self.assertRaisesRegex(ValueError, "implicit front-month selection is forbidden"):
            InstrumentSpec(symbol="MNQ", asset_type="FUT", exchange="CME").validate()

    def test_future_accepts_registry_supplied_contract_month(self):
        spec = InstrumentSpec(
            symbol="MNQ",
            asset_type="FUT",
            exchange="CME",
            contract_month="202609",
        ).validate()
        self.assertEqual(spec.contract_month, "202609")
        self.assertFalse(spec.receipt()["implicit_roll_selection"])

    def test_future_accepts_registry_supplied_local_symbol(self):
        spec = InstrumentSpec(
            symbol="MNQ",
            asset_type="FUT",
            exchange="CME",
            local_symbol="MNQU6",
        ).validate()
        self.assertEqual(spec.local_symbol, "MNQU6")

    def test_json_path_contract_is_supported(self):
        payload = [
            {"symbol": "AMAT", "asset_type": "STK", "exchange": "SMART"},
            {
                "symbol": "MNQ",
                "asset_type": "FUT",
                "exchange": "CME",
                "local_symbol": "MNQU6",
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "instruments.json"
            p.write_text(json.dumps(payload))
            specs = parse_instrument_specs("@" + str(p))
        self.assertEqual([(s.symbol, s.asset_type) for s in specs], [("AMAT", "STK"), ("MNQ", "FUT")])

    def test_duplicate_instrument_identity_is_rejected(self):
        payload = json.dumps([
            {"symbol": "AMAT", "asset_type": "STK", "exchange": "SMART"},
            {"symbol": "AMAT", "asset_type": "STK", "exchange": "SMART"},
        ])
        with self.assertRaisesRegex(ValueError, "duplicate instrument identities"):
            parse_instrument_specs(payload)


if __name__ == "__main__":
    unittest.main()
