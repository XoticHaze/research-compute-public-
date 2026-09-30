from __future__ import annotations

import asyncio
import ast
import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import ibkr_remote_forward_exact_ticks_v1 as mod


class FakeIB:
    def run(self, awaitable):
        return asyncio.run(awaitable)


class FakeProducer:
    PRODUCER_SCHEMA = mod.PRODUCER_SCHEMA

    async def produce_historical_tick_evidence(self, ib, plan):
        return {
            "schema": mod.EVIDENCE_SCHEMA,
            "producer_schema": mod.PRODUCER_SCHEMA,
            "pair_id": plan["pair_id"],
            "identity": dict(plan["identity"]),
            "historical_tick_domain": "IBKR_TRADES",
            "timestamp_resolution": "seconds",
            "boundaries": {
                "entry": {
                    "coverage_complete": True,
                    "producer_inference": False,
                    "broker_order_action": False,
                    "ticks": [{"time": "2026-09-29T12:00:00Z", "price": 24500.0, "size": 1.0}],
                },
                "exit": {
                    "coverage_complete": True,
                    "producer_inference": False,
                    "broker_order_action": False,
                    "ticks": [{"time": "2026-09-29T12:05:00Z", "price": 24510.0, "size": 2.0}],
                },
            },
            "producer_inference": False,
            "broker_order_action": False,
            "broker_submission": False,
            "runtime_authority_change": False,
            "strategy_spec_mutation": False,
            "live_execution_allowed": False,
        }


class ForwardExactTicksTests(unittest.TestCase):
    def test_ib_insync_is_runtime_lazy_import_only(self):
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        offenders = [
            ast.unparse(node)
            for node in tree.body
            if (
                isinstance(node, ast.Import)
                and any(alias.name == "ib_insync" or alias.name.startswith("ib_insync.") for alias in node.names)
            )
            or (
                isinstance(node, ast.ImportFrom)
                and bool(node.module)
                and (node.module == "ib_insync" or node.module.startswith("ib_insync."))
            )
        ]
        self.assertEqual(offenders, [])

    def plan(self):
        return {
            "schema": "mmibkr.selected_runtime_forward_exact_extrema_tick_request_plan.v1",
            "state": "TICK_REQUEST_PLAN_READY",
            "pair_id": "pair-1",
            "identity": {
                "runtime_id": "mnq-runtime",
                "strategy_id": "crw_score_multi_mode",
                "strategy_spec_digest": "spec-1",
                "symbol": "MNQ",
                "timeframe": "12Min",
            },
            "requests": [{"boundary_kind": "entry"}, {"boundary_kind": "exit"}],
            "broker_submission": False,
            "live_execution_allowed": False,
        }

    def runtime(self, root):
        return {
            "mode": mod.MODE,
            "paper_only": True,
            "live_trading_change": False,
            "read_only_api": "yes",
            "private_repository_token_used": False,
            "source_transport": "fleet_private_attested_source_v1",
            "source_root": str(root),
            "mmibkr_head": "a" * 40,
            "source_archive_sha256": "b" * 64,
            "command_id": "sha256:" + "c" * 64,
        }

    def request(self):
        return {
            "command_id": "sha256:" + "c" * 64,
            "source_ref": "forward-pair:pair-1",
            "source_sha": "a" * 40,
            "tick_plan": self.plan(),
        }

    def test_collect_preserves_private_identity_and_read_only_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            receipt=mod.collect_with_connected_ib(
                runtime=self.runtime(root),
                request=self.request(),
                ib=FakeIB(),
                producer=FakeProducer(),
                run_id="123",
                public_head="d" * 40,
            )
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["evidence"]["pair_id"], "pair-1")
        self.assertEqual(
            receipt["evidence"]["identity"]["strategy_spec_digest"],
            "spec-1",
        )
        self.assertTrue(receipt["authority"]["read_only_ibkr_historical_ticks"])
        self.assertFalse(receipt["authority"]["public_producer_inference"])
        self.assertFalse(receipt["authority"]["broker_order_action"])
        self.assertFalse(receipt["authority"]["broker_submission"])
        self.assertFalse(receipt["authority"]["live_execution_allowed"])

    def test_runtime_rejects_non_read_only_or_non_attested_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            request=self.request()
            request["source_sha"]="d" * 40
            with self.assertRaisesRegex(RuntimeError, "source identity"):
                mod.validate_runtime(self.runtime(root),request)

            runtime=self.runtime(root)
            runtime["read_only_api"]="no"
            with self.assertRaisesRegex(RuntimeError, "read-only"):
                mod.validate_runtime(runtime,self.request())

            runtime=self.runtime(root)
            runtime["private_repository_token_used"]=True
            with self.assertRaisesRegex(RuntimeError, "attested private source"):
                mod.validate_runtime(runtime,self.request())

    def test_evidence_identity_and_authority_fail_closed(self):
        plan=self.plan()
        evidence=asyncio.run(FakeProducer().produce_historical_tick_evidence(None,plan))
        bad=json.loads(json.dumps(evidence))
        bad["pair_id"]="other"
        with self.assertRaisesRegex(RuntimeError, "pair identity"):
            mod.validate_evidence(bad,plan)

        bad=json.loads(json.dumps(evidence))
        bad["broker_order_action"]=True
        with self.assertRaisesRegex(RuntimeError, "authority boundary"):
            mod.validate_evidence(bad,plan)

    def test_encrypted_return_contains_ciphertext_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            receipt=mod.collect_with_connected_ib(
                runtime=self.runtime(root),
                request=self.request(),
                ib=FakeIB(),
                producer=FakeProducer(),
                run_id="123",
                public_head="d" * 40,
            )
            recipient_raw=bytes(range(32))
            recipient={
                "schema":mod.RETURN_RECIPIENT_SCHEMA,
                "recipient_b64":base64.b64encode(recipient_raw).decode("ascii"),
                "recipient_key_id":"sha256:"+hashlib.sha256(recipient_raw).hexdigest(),
            }
            out=root/"return"
            envelope=mod.encrypt_receipt(
                receipt=receipt,
                recipient=recipient,
                run_id="123",
                output_dir=out,
            )
            self.assertEqual(envelope["schema"],mod.RETURN_ENVELOPE_SCHEMA)
            self.assertGreater(len(envelope["chunks"]),0)
            raw="".join((out/node["local_name"]).read_text() for node in envelope["chunks"])
            self.assertNotIn("MNQ",raw)
            self.assertNotIn("24500",raw)


if __name__=="__main__":
    unittest.main()
