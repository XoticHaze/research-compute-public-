from __future__ import annotations
import base64
import hashlib
import json
import unittest
from scripts.ibkr_b1_private_bars_mode_v1 import validate


class PrivateContractBarsContractTests(unittest.TestCase):
    def request(self, typ: str = "FUT"):
        conid = {"STK": 101, "FUT": 202, "OPT": 303}[typ]
        symbol = {"STK": "AMAT", "FUT": "MNQ", "OPT": "NVDA"}[typ]
        descriptor = {"symbol": symbol, "secType": typ, "conId": conid,
                      "currency": "USD", "exchange": "CME" if typ == "FUT" else "SMART"}
        if typ == "FUT":
            descriptor["lastTradeDateOrContractMonth"] = "20261218"
        if typ == "OPT":
            descriptor.update(lastTradeDateOrContractMonth="20261218", strike=150,
                              right="C", multiplier="100")
        key = bytes(range(32))
        return {
            "symbols": symbol,
            "contracts_json": json.dumps({symbol: descriptor}),
            "bar_requests_json": json.dumps({symbol: [{
                "source_timeframe": "5Min", "target_timeframe": "5Min",
                "bar_size_setting": "5 mins", "duration_str": "2 D"}]}),
            "recipient_b64": base64.b64encode(key).decode("ascii"),
            "recipient_key_id": "sha256:" + hashlib.sha256(key).hexdigest(),
            "profile": "v2",
        }

    def test_all_existing_reader_security_classes(self):
        for typ in ("STK", "FUT", "OPT"):
            with self.subTest(typ=typ):
                receipt = validate(**self.request(typ))
                self.assertEqual(receipt["security_types"], [typ])
                self.assertFalse(receipt["plaintext_artifact_allowed"])
                self.assertFalse(receipt["broker_mutation_authority"])

    def test_not_an_anonymous_stock_fallback(self):
        q = self.request("FUT")
        q["contracts_json"] = "{}"
        with self.assertRaises(ValueError):
            validate(**q)

    def test_option_identity_requires_expiry(self):
        q = self.request("OPT")
        hints = json.loads(q["contracts_json"])
        del hints["NVDA"]["lastTradeDateOrContractMonth"]
        q["contracts_json"] = json.dumps(hints)
        with self.assertRaises(ValueError):
            validate(**q)

    def test_missing_encrypted_recipient_fails(self):
        q = self.request()
        q["recipient_b64"] = ""
        with self.assertRaises(ValueError):
            validate(**q)

    def test_private_return_requires_v2_framing(self):
        q = self.request()
        q["profile"] = "v1"
        with self.assertRaises(ValueError):
            validate(**q)

    def test_unbounded_or_missing_history_rejected(self):
        q = self.request()
        q["bar_requests_json"] = json.dumps({"MNQ": [{
            "source_timeframe": "5Min", "target_timeframe": "5Min",
            "bar_size_setting": "5 mins", "duration_str": "80 D"}]})
        with self.assertRaises((ValueError, RuntimeError)):
            validate(**q)


if __name__ == "__main__":
    unittest.main()
