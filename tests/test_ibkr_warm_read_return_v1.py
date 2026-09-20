from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from scripts import ibkr_warm_read_return_v1 as mod


class WarmReadReturnTests(unittest.TestCase):
    def _recipient(self):
        private = x25519.X25519PrivateKey.generate()
        public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return private, base64.b64encode(public_raw).decode("ascii"), "sha256:" + hashlib.sha256(public_raw).hexdigest()

    def _snapshot(self):
        return {
            "schema": mod.SNAPSHOT_SCHEMA,
            "generated_at": "2026-09-17T00:00:00+00:00",
            "run_id": "12345",
            "public_head": "a" * 40,
            "authority": mod.AUTHORITY,
            "harness": mod.HARNESS,
            "trading_mode": "paper",
            "read_only": True,
            "managed_accounts": ["DU123456"],
            "account_summary": [
                {"account": "DU123456", "tag": "NetLiquidation", "value": "100000", "currency": "USD", "model_code": ""}
            ],
            "positions": [
                {
                    "account": "DU123456",
                    "contract": {"conId": 266093, "symbol": "AMAT", "secType": "STK"},
                    "position": 2.0,
                    "avg_cost": 150.0,
                }
            ],
            "open_trades": [],
            "fills": [
                {
                    "contract": {"conId": 266093, "symbol": "AMAT", "secType": "STK"},
                    "execution": {
                        "execId": "exec-1",
                        "time": "2026-09-17T00:00:00Z",
                        "acctNumber": "DU123456",
                        "side": "BOT",
                        "shares": 2.0,
                        "price": 150.0,
                        "permId": 11,
                        "orderId": 12,
                    },
                    "commission_report": {
                        "execId": "exec-1",
                        "commission": 1.0,
                        "currency": "USD",
                        "realizedPNL": 0.0,
                    },
                }
            ],
            "completed_execution_evidence": {
                "requested": True,
                "req_executions_called": True,
                "source": "ibkr.reqExecutions",
                "returned_fill_count": 1,
                "requested_contract_fill_count": 1,
                "execution_ids": ["exec-1"],
                "request_elapsed_ms": 12.0,
                "complete_history_claimed": False,
                "broker_mutation_called": False,
                "global_cancel_called": False,
                "live_execution_allowed": False,
            },
            "broker_time": "2026-09-17T00:00:00+00:00",
            "post_auth_handoff": {"schema": "mmibkr-ibkr-post-auth-handoff-v2"},
            "requested_symbols": ["AMAT"],
            "forward_bar_symbols": ["AMAT"],
            "forward_bars": [{"symbol": "AMAT", "close": 151.0}],
            "capabilities": {
                "account_state": True,
                "positions": True,
                "open_orders": True,
                "historical_market_data": True,
                "completed_executions": True,
                "order_submission": False,
                "global_cancel": False,
                "live_execution": False,
            },
        }

    def test_encrypt_snapshot_round_trip_is_run_and_recipient_bound(self):
        private, recipient_b64, recipient_key_id = self._recipient()
        snapshot = self._snapshot()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            envelope = mod.encrypt_snapshot(
                snapshot=snapshot,
                recipient_b64=recipient_b64,
                recipient_key_id=recipient_key_id,
                run_id="12345",
                output_dir=root,
            )
            self.assertEqual(envelope["schema"], mod.RETURN_ENVELOPE_SCHEMA)
            self.assertEqual(envelope["run_id"], "12345")
            self.assertEqual(envelope["recipient_key_id"], recipient_key_id)
            self.assertEqual(mod.RETURN_INFO, b"mm-ibkr-warm-read-return-v1")
            self.assertGreater(len(envelope["chunks"]), 0)
            self.assertFalse((root / "ibkr-warm-read-snapshot.json").exists())

            pieces = []
            for node in envelope["chunks"]:
                raw = (root / node["local_name"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), node["sha256"])
                self.assertEqual(len(raw), node["chars"])
                self.assertTrue(node["path"].startswith("rendezvous/returns/12345/"))
                pieces.append(raw.decode("ascii"))
            ciphertext = base64.b64decode("".join(pieces).encode("ascii"), validate=True)
            self.assertEqual(hashlib.sha256(ciphertext).hexdigest(), envelope["ciphertext_sha256"])

            sender_raw = base64.b64decode(envelope["sender_public_b64"].encode("ascii"), validate=True)
            nonce = base64.b64decode(envelope["nonce_b64"].encode("ascii"), validate=True)
            aad = mod._aad(run_id="12345", recipient_key_id=recipient_key_id)
            shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(sender_raw))
            key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=hashlib.sha256(aad).digest(),
                info=mod.RETURN_INFO,
            ).derive(shared)
            plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)
            self.assertEqual(hashlib.sha256(plaintext).hexdigest(), envelope["plaintext_sha256"])
            self.assertEqual(json.loads(plaintext.decode("utf-8")), snapshot)

    def test_encrypt_snapshot_normalizes_nested_nonfinite_broker_values_to_null(self):
        private, recipient_b64, recipient_key_id = self._recipient()
        snapshot = self._snapshot()
        snapshot["post_auth_handoff"]["quote_snapshot"] = {
            "bid": float("nan"),
            "ask": float("inf"),
            "last": float("-inf"),
            "finite": 123.25,
        }
        snapshot["positions"][0]["avg_cost"] = float("nan")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            envelope = mod.encrypt_snapshot(
                snapshot=snapshot,
                recipient_b64=recipient_b64,
                recipient_key_id=recipient_key_id,
                run_id="12345",
                output_dir=root,
            )
            ciphertext = base64.b64decode(
                "".join(
                    (root / node["local_name"]).read_text(encoding="ascii")
                    for node in envelope["chunks"]
                ).encode("ascii"),
                validate=True,
            )
            sender_raw = base64.b64decode(
                envelope["sender_public_b64"].encode("ascii"),
                validate=True,
            )
            nonce = base64.b64decode(
                envelope["nonce_b64"].encode("ascii"),
                validate=True,
            )
            aad = mod._aad(run_id="12345", recipient_key_id=recipient_key_id)
            shared = private.exchange(
                x25519.X25519PublicKey.from_public_bytes(sender_raw)
            )
            key = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=hashlib.sha256(aad).digest(),
                info=mod.RETURN_INFO,
            ).derive(shared)
            plaintext = ChaCha20Poly1305(key).decrypt(
                nonce,
                ciphertext,
                aad,
            )
            decoded = json.loads(plaintext.decode("utf-8"))
        quote = decoded["post_auth_handoff"]["quote_snapshot"]
        self.assertIsNone(quote["bid"])
        self.assertIsNone(quote["ask"])
        self.assertIsNone(quote["last"])
        self.assertEqual(quote["finite"], 123.25)
        self.assertIsNone(decoded["positions"][0]["avg_cost"])

    def test_requested_fill_filter_keeps_only_exact_mm_contracts_and_managed_accounts(self):
        amat = {
            "contract": {"conId": 266093, "symbol": "AMAT", "secType": "STK"},
            "execution": {"execId": "amat-1", "acctNumber": "DU123456"},
        }
        other = {
            "contract": {"conId": 999, "symbol": "OTHER", "secType": "STK"},
            "execution": {"execId": "other-1", "acctNumber": "DU123456"},
        }
        handoff = {
            "symbols": [{
                "symbol": "AMAT",
                "resolved_contract": {
                    "conId": 266093,
                    "symbol": "AMAT",
                    "secType": "STK",
                    "localSymbol": "AMAT",
                },
            }]
        }
        rows, ids = mod._filter_requested_fills(
            [amat, other],
            handoff=handoff,
            managed_accounts=["DU123456"],
        )
        self.assertEqual(rows, [amat])
        self.assertEqual(ids, ["amat-1"])

        escaped = {
            "contract": {"conId": 266093, "symbol": "AMAT", "secType": "STK"},
            "execution": {"execId": "bad", "acctNumber": "U999"},
        }
        with self.assertRaisesRegex(RuntimeError, "escaped managed DU accounts"):
            mod._filter_requested_fills(
                [escaped],
                handoff=handoff,
                managed_accounts=["DU123456"],
            )

    def test_execution_fill_serializer_preserves_position_policy_fields(self):
        fill = SimpleNamespace(
            contract=SimpleNamespace(
                conId=793356225,
                symbol="MNQ",
                secType="FUT",
                exchange="CME",
                primaryExchange="",
                currency="USD",
                localSymbol="MNQU6",
                tradingClass="MNQ",
                lastTradeDateOrContractMonth="202609",
            ),
            execution=SimpleNamespace(
                execId="exec-mnq-1",
                time=__import__("datetime").datetime(
                    2026, 9, 18, 14, 0,
                    tzinfo=__import__("datetime").timezone.utc,
                ),
                acctNumber="DU123456",
                exchange="CME",
                side="BOT",
                shares=1.0,
                price=24000.25,
                permId=42,
                clientId=79,
                orderId=17,
                cumQty=1.0,
                avgPrice=24000.25,
                orderRef="MMIBKR",
            ),
            commissionReport=SimpleNamespace(
                execId="exec-mnq-1",
                commission=0.62,
                currency="USD",
                realizedPNL=0.0,
            ),
        )
        row = mod._execution_fill(fill)
        self.assertEqual(row["contract"]["conId"], 793356225)
        self.assertEqual(row["execution"]["side"], "BOT")
        self.assertEqual(row["execution"]["shares"], 1.0)
        self.assertEqual(row["execution"]["price"], 24000.25)
        self.assertEqual(row["execution"]["permId"], 42)
        self.assertEqual(row["execution"]["orderId"], 17)
        self.assertEqual(row["execution"]["execId"], "exec-mnq-1")
        self.assertEqual(row["execution"]["acctNumber"], "DU123456")

    def test_wrong_recipient_fingerprint_fails_closed(self):
        _, recipient_b64, _ = self._recipient()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "fingerprint mismatch"):
                mod.encrypt_snapshot(
                    snapshot=self._snapshot(),
                    recipient_b64=recipient_b64,
                    recipient_key_id="sha256:" + "0" * 64,
                    run_id="12345",
                    output_dir=Path(td),
                )

    def test_identity_and_mutation_boundaries_fail_closed(self):
        _, recipient_b64, recipient_key_id = self._recipient()
        bad_run = self._snapshot()
        bad_run["run_id"] = "999"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
                mod.encrypt_snapshot(
                    snapshot=bad_run,
                    recipient_b64=recipient_b64,
                    recipient_key_id=recipient_key_id,
                    run_id="12345",
                    output_dir=Path(td),
                )

        mutable = self._snapshot()
        mutable["capabilities"]["order_submission"] = True
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "mutation boundary"):
                mod.encrypt_snapshot(
                    snapshot=mutable,
                    recipient_b64=recipient_b64,
                    recipient_key_id=recipient_key_id,
                    run_id="12345",
                    output_dir=Path(td),
                )

    def test_non_du_account_fails_closed(self):
        _, recipient_b64, recipient_key_id = self._recipient()
        snapshot = self._snapshot()
        snapshot["managed_accounts"] = ["U123456"]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "DU paper-account boundary"):
                mod.encrypt_snapshot(
                    snapshot=snapshot,
                    recipient_b64=recipient_b64,
                    recipient_key_id=recipient_key_id,
                    run_id="12345",
                    output_dir=Path(td),
                )

    def test_incomplete_forward_bar_coverage_fails_closed(self):
        _, recipient_b64, recipient_key_id = self._recipient()
        snapshot = self._snapshot()
        snapshot["requested_symbols"] = ["AMAT", "APH"]
        snapshot["forward_bar_symbols"] = ["AMAT"]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "forward-bar coverage mismatch"):
                mod.encrypt_snapshot(
                    snapshot=snapshot,
                    recipient_b64=recipient_b64,
                    recipient_key_id=recipient_key_id,
                    run_id="12345",
                    output_dir=Path(td),
                )

    def test_missing_required_read_capability_fails_closed(self):
        _, recipient_b64, recipient_key_id = self._recipient()
        snapshot = self._snapshot()
        snapshot["capabilities"]["historical_market_data"] = False
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError, "required capability missing"):
                mod.encrypt_snapshot(
                    snapshot=snapshot,
                    recipient_b64=recipient_b64,
                    recipient_key_id=recipient_key_id,
                    run_id="12345",
                    output_dir=Path(td),
                )

    def test_source_has_readonly_connect_and_no_mutation_calls(self):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertIn("readonly=True", source)
        self.assertIn("ib.reqExecutions()", source)
        self.assertIn('"complete_history_claimed": False', source)
        self.assertNotIn("placeOrder(", source)
        self.assertNotIn("cancelOrder(", source)
        self.assertNotIn("reqGlobalCancel", source)
        self.assertNotIn("qualifyContracts(", source)
        self.assertIn('"order_submission": False', source)
        self.assertIn('"global_cancel": False', source)
        self.assertIn('"live_execution": False', source)


if __name__ == "__main__":
    unittest.main()
