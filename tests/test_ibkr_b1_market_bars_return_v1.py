from __future__ import annotations
import base64
import hashlib
import json
import os
import tempfile
import unittest
import zlib
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts import ibkr_b1_market_bars_return_v1 as mod

RUN = "44500000123"
HEAD = "d" * 40


def fixture(typ="FUT", symbol="MNQ"):
    con_id = 202
    resolved = {
        "symbol": symbol, "secType": typ, "conId": con_id,
        "exchange": "CME" if typ == "FUT" else "SMART", "currency": "USD",
        "lastTradeDateOrContractMonth": "20261218" if typ != "STK" else "",
        "strike": 160.0 if typ == "OPT" else 0.0,
        "right": "C" if typ == "OPT" else "",
        "multiplier": "100" if typ == "OPT" else "2" if typ == "FUT" else "",
    }
    rec = {
        "symbol": symbol, "contract_qualified": True,
        "historical_data_ready": True,
        "bar_requests": [{
            "bar_size_setting": "5 mins", "duration_str": "2 D",
            "historical_bar_count": 2, "history_contract_id": f"conid:{con_id}",
            "resolved_history_contract": resolved,
        }],
    }
    handoff = {
        "schema": "mmibkr-ibkr-post-auth-handoff-v2",
        "trading_mode": "paper", "read_only": True,
        "paper_account_verified": True, "consumer_ready": True,
        "bar_requests_explicit": True,
        "forward_bar_contract": "research.forward_bar.v2",
        "forward_bar_count": 2,
        "requested_symbols": [symbol],
        "symbols": [rec],
        "account_summary": [{"account": "DU1234567", "value": "123456"}],
        "positions": [{"account": "DU1234567", "qty": 100}],
        "capabilities": {
            "historical_market_data": True,
            "canonical_forward_bar_materialization": True,
            "order_submission": False,
        },
    }
    bar = {
        "symbol": symbol, "source": "ibkr", "asset_type": typ,
        "bar_size": "5 mins", "session": "all", "contract_id": f"conid:{con_id}",
        "volume": 145.0, "wap": 100.0, "bar_count": 22,
    }
    rows = [
        {**bar, "timestamp": "2026-11-19T09:55:00Z", "open": 100.0, "high": 102.0, "low": 99.5, "close": 101.5},
        {**bar, "timestamp": "2026-11-19T10:00:00Z", "open": 101.5, "high": 103.0, "low": 101.2, "close": 102.8},
    ]
    return handoff, rows


class MarketBarsOnlyReturnTests(unittest.TestCase):
    def test_stock_future_and_option_have_real_qualified_contracts(self):
        for typ, symbol in (("STK", "AMAT"), ("FUT", "MNQ"), ("OPT", "NVDA")):
            with self.subTest(typ=typ):
                handoff, rows = fixture(typ, symbol)
                payload = mod.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)
                self.assertEqual(payload["row_count"], 2)
                self.assertEqual(payload["contracts"][0]["asset_type"], typ)
                self.assertEqual(payload["bars"][1]["close"], 102.8)
                self.assertEqual(payload["bars"][1]["contract_id"], "conid:202")
                self.assertTrue(payload["read_only"])
                self.assertFalse(payload["broker_mutation_authority"])
                self.assertNotIn("account_summary", payload)
                self.assertNotIn("positions", payload)
                self.assertNotIn("fills", payload)

    def test_wrong_contract_or_source_rejected(self):
        handoff, rows = fixture()
        rows[0]["contract_id"] = "conid:999"
        with self.assertRaisesRegex(ValueError, "contract_identity_drift"):
            mod.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)
        _, rows = fixture()
        rows[0]["source"] = "synthetic"
        with self.assertRaisesRegex(ValueError, "non_ibkr_source"):
            mod.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)

    def test_duplicate_bar_rejected(self):
        handoff, rows = fixture()
        rows[1] = dict(rows[0])
        with self.assertRaisesRegex(ValueError, "duplicate normalized bars"):
            mod.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)

    def test_account_submit_or_implicit_stock_fallback_rejected(self):
        handoff, rows = fixture()
        handoff["capabilities"]["order_submission"] = True
        with self.assertRaisesRegex(ValueError, "broker_readonly"):
            mod.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)
        handoff, rows = fixture()
        handoff["bar_requests_explicit"] = False
        with self.assertRaisesRegex(ValueError, "broker_handoff"):
            mod.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)

    def test_compressed_encrypted_roundtrip_is_bars_only(self):
        handoff, rows = fixture("OPT", "NVDA")
        payload = mod.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)
        private = x25519.X25519PrivateKey.generate()
        public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        key_id = "sha256:" + hashlib.sha256(public).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "private"
            envelope = mod.encrypt_payload(
                payload=payload,
                recipient_b64=base64.b64encode(public).decode(),
                recipient_key_id=key_id, run_id=RUN, output_dir=folder)
            self.assertFalse("plaintext_sha256" in envelope)
            self.assertEqual(envelope["compression"], "zlib")
            self.assertTrue(envelope["chunks"])
            self.assertEqual(os.stat(folder).st_mode & 0o777, 0o700)
            chunks = "".join((folder / x["local_name"]).read_text() for x in envelope["chunks"])
            ciphertext = base64.b64decode(chunks)
            self.assertEqual(hashlib.sha256(ciphertext).hexdigest(), envelope["ciphertext_sha256"])
            aad = mod._aad(run_id=RUN, recipient_key_id=key_id)
            sender = x25519.X25519PublicKey.from_public_bytes(base64.b64decode(envelope["sender_public_b64"]))
            key = HKDF(algorithm=hashes.SHA256(), length=32,
                       salt=hashlib.sha256(aad).digest(), info=mod.TRANSPORT_INFO).derive(private.exchange(sender))
            decoded = json.loads(zlib.decompress(ChaCha20Poly1305(key).decrypt(
                base64.b64decode(envelope["nonce_b64"]), ciphertext, aad)))
            self.assertEqual(decoded["bars"], payload["bars"])
            self.assertNotIn("account_summary", json.dumps(decoded))
            self.assertNotIn("DU1234567", json.dumps(decoded))
            self.assertEqual(os.stat(folder / "ibkr-warm-read-envelope.json").st_mode & 0o777, 0o600)
            with self.assertRaises(Exception):
                ChaCha20Poly1305(key).decrypt(base64.b64decode(envelope["nonce_b64"]),
                                              ciphertext[:-1] + b"\x00", aad)

    def test_unencrypted_or_wrong_recipient_not_accepted(self):
        handoff, rows = fixture()
        payload = mod.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "recipient"):
                mod.encrypt_payload(payload=payload, recipient_b64="",
                                    recipient_key_id="sha256:" + "0"*64,
                                    run_id=RUN, output_dir=Path(root))

    def test_file_loader_avoids_extra_metadata(self):
        handoff, rows = fixture()
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "rows.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            got = mod._read_rows(path)
            self.assertEqual(len(got), 2)
            got[0]["account_id"] = "DU1"
            path.write_text("\n".join(json.dumps(r) for r in got))
            with self.assertRaisesRegex(ValueError, "forward_fields"):
                mod._read_rows(path)


if __name__ == "__main__":
    unittest.main()
