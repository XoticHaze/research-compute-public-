from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from scripts import ibkr_b1_market_bars_return_v1 as producer
from scripts import ibkr_b1_market_bars_consumer_v1 as consumer
from tests.test_ibkr_b1_market_bars_return_v1 import fixture, RUN, HEAD


class PrivateMarketBarConsumerTests(unittest.TestCase):
    def prepared(self, root, typ="FUT", symbol="MNQ"):
        handoff, rows = fixture(typ, symbol)
        payload = producer.build_payload(handoff=handoff, rows=rows, run_id=RUN, public_head=HEAD)
        private = x25519.X25519PrivateKey.generate()
        raw_private = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                            serialization.NoEncryption())
        public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        private_path = Path(root) / "recipient.private"
        private_path.write_text(base64.b64encode(raw_private).decode("ascii"))
        private_path.chmod(0o600)
        return_dir = Path(root) / "encrypted"
        envelope = producer.encrypt_payload(
            payload=payload, recipient_b64=base64.b64encode(public).decode("ascii"),
            recipient_key_id="sha256:" + hashlib.sha256(public).hexdigest(),
            run_id=RUN, output_dir=return_dir)
        return private_path, return_dir, envelope

    def decode(self, private_path, return_dir, symbol="MNQ", contract="conid:202", **kwargs):
        return consumer.decode(
            folder=return_dir, private_key_file=private_path,
            expected_run_id=kwargs.pop("run", RUN),
            expected_public_head=kwargs.pop("head", HEAD),
            expected_symbols=(symbol,), expected_contract_ids={symbol: [contract]}, **kwargs)

    def test_consume_bars_only_for_stock_future_option(self):
        for typ, sym in (("STK", "AMAT"), ("FUT", "MNQ"), ("OPT", "NVDA")):
            with self.subTest(typ=typ), tempfile.TemporaryDirectory() as root:
                key, folder, _ = self.prepared(root, typ, sym)
                decoded = self.decode(key, folder, symbol=sym)
                self.assertEqual(decoded["row_count"], 2)
                self.assertEqual(decoded["bars"][1]["close"], 102.8)
                self.assertNotIn("account_summary", decoded)
                self.assertTrue(decoded["read_only"])
                output = Path(root) / "bars.private.jsonl"
                consumer.store_private_rows(decoded, output)
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                self.assertEqual(len(output.read_text().strip().splitlines()), 2)
                self.assertEqual(json.loads(output.read_text().splitlines()[0])["contract_id"], "conid:202")

    def test_wrong_run_or_head_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            key, folder, _ = self.prepared(root)
            with self.assertRaisesRegex(ValueError, "envelope_run_mismatch"):
                self.decode(key, folder, run="44500000124")
            with self.assertRaisesRegex(ValueError, "payload_identity_invalid"):
                self.decode(key, folder, head="a" * 40)

    def test_wrong_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            key, folder, _ = self.prepared(root)
            with self.assertRaisesRegex(ValueError, "exact_contract_id_mismatch"):
                self.decode(key, folder, contract="conid:203")

    def test_tampered_chunk_rejected_before_decryption(self):
        with tempfile.TemporaryDirectory() as root:
            key, folder, env = self.prepared(root)
            chunk = folder / env["chunks"][0]["local_name"]
            chunk.write_text(chunk.read_text().replace("A", "B", 1) + "X")
            with self.assertRaises(ValueError):
                self.decode(key, folder)

    def test_key_file_must_be_private_and_correct(self):
        with tempfile.TemporaryDirectory() as root:
            key, folder, _ = self.prepared(root)
            key.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "recipient_file_untrusted"):
                self.decode(key, folder)
            key.chmod(0o600)
            other = x25519.X25519PrivateKey.generate().private_bytes(
                serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                serialization.NoEncryption())
            key.write_text(base64.b64encode(other).decode("ascii"))
            with self.assertRaisesRegex(ValueError, "recipient_fingerprint_mismatch"):
                self.decode(key, folder)

    def test_replay_cannot_overwrite_private_output(self):
        with tempfile.TemporaryDirectory() as root:
            key, folder, _ = self.prepared(root)
            payload = self.decode(key, folder)
            output = Path(root) / "result.jsonl"
            consumer.store_private_rows(payload, output)
            original = output.read_bytes()
            with self.assertRaises(FileExistsError):
                consumer.store_private_rows(payload, output)
            self.assertEqual(output.read_bytes(), original)

    def test_untrusted_output_parent_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            key, folder, _ = self.prepared(root)
            payload = self.decode(key, folder)
            parent = Path(root) / "unsafe"
            parent.mkdir()
            parent.chmod(0o777)
            with self.assertRaisesRegex(ValueError, "output_parent_untrusted"):
                consumer.store_private_rows(payload, parent / "output.jsonl")


if __name__ == "__main__":
    unittest.main()
