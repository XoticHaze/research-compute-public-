from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest

from scripts.mmibkr_gh_gateway_readonly_client_v1 import (
    account_receipt,
    contract_scope,
    gateway_name,
)
from scripts.mmibkr_split_gateway_tcp_relay_v1 import (
    bridge,
    validate_tailnet_ip,
)


class ReadOnlyFakeBroker:
    """No order mutation or login methods exist on this fake."""

    def managedAccounts(self):
        return ["U-EXPECTED", "DU-PAPER"]

    def reqPositions(self):
        return [SimpleNamespace(account="U-EXPECTED"), SimpleNamespace(account="DU-PAPER")]

    def reqAllOpenOrders(self):
        return [SimpleNamespace(order=SimpleNamespace(account="U-EXPECTED"))]

    def reqExecutions(self):
        return [SimpleNamespace(execution=SimpleNamespace(acctNumber="U-EXPECTED"))]


class GatewayPoolContractTests(unittest.TestCase):
    def test_relay_accepts_only_numeric_private_tailnet_ip(self):
        for good in ("100.64.0.1", "100.120.1.4", "100.127.255.254"):
            self.assertEqual(validate_tailnet_ip(good), good)
        for bad in ("10.0.0.1", "127.0.0.1", "0.0.0.0",
                    "8.8.8.8", "192.168.0.1", "::1", "gateway.example.com"):
            with self.assertRaises(ValueError):
                validate_tailnet_ip(bad)

    def test_exact_owner_run_is_part_of_gateway_hostname(self):
        self.assertEqual(gateway_name("39499524894"), "mmibkr-gw-39499524894")
        for bad in ("", "abc", "1", "1.2.3", "00000abc", "2"*25):
            with self.assertRaises(ValueError):
                gateway_name(bad)

    def test_existing_account_read_no_mutation_surface(self):
        r=account_receipt(ReadOnlyFakeBroker(),"U-EXPECTED",
                          run_id="39499524894",phase="A",client_id=101,specs=[])
        self.assertTrue(r["ok"])
        self.assertTrue(r["account_matched"])
        self.assertEqual(r["account_positions"],1)
        self.assertEqual(r["account_orders"],1)
        self.assertEqual(r["account_executions"],1)
        self.assertEqual(r["broker_mutations_attempted"],False)
        self.assertFalse(r["ibkey_prompt_absence_independently_verified"])
        self.assertFalse(r["canonical_submit_gate_acceptance_proven"])
        self.assertNotIn("U-EXPECTED",str(r))

    def test_account_mismatch_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"expected_live_account_mismatch"):
            account_receipt(ReadOnlyFakeBroker(),"U-OTHER",
                            run_id="39499524894",phase="A",client_id=101,specs=[])

    def test_three_asset_class_descriptor_rules(self):
        rows=contract_scope([
            {"symbol":"AMAT","secType":"STK","conId":11},
            {"symbol":"MNQ","secType":"FUT","conId":22,"lastTradeDateOrContractMonth":"20261218"},
            {"symbol":"SPY","secType":"OPT","conId":33,"lastTradeDateOrContractMonth":"20261120",
             "right":"C","strike":500.0,"multiplier":"100"},
        ])
        self.assertEqual([r["secType"] for r in rows],["STK","FUT","OPT"])

    def test_never_autoselect_option_or_futures_contract(self):
        for row in (
            {"symbol":"MNQ","secType":"FUT","conId":22},
            {"symbol":"MNQ","secType":"FUT","conId":22,"lastTradeDateOrContractMonth":"202612"},
            {"symbol":"SPY","secType":"OPT","conId":33},
            {"symbol":"SPY","secType":"OPT","conId":0,"lastTradeDateOrContractMonth":"20261120",
             "right":"C","strike":500.0,"multiplier":"100"},
            {"symbol":"TSLA","secType":"STK"},
        ):
            with self.assertRaises(ValueError):
                contract_scope([row])

    def test_public_actions_holder_is_explicit_no_order_mode(self):
        owner=(Path(__file__).resolve().parents[1]/
               ".github/workflows/mmibkr-selected-runtime-live-owner-r1.yml").read_text()
        self.assertIn("gateway_pool_5h",owner)
        self.assertIn("read_only_api=yes",owner)
        self.assertIn("MMIBKR_GATEWAY_ONLY_POOL_READY=1",owner)
        self.assertIn("if: ${{ inputs.admission_only && inputs.warm_handoff_mode == 'gateway_pool_5h' }}",owner)
        self.assertIn('relogin_after_twofa_timeout=no',owner)
        self.assertIn("tag:mmibkr-gateway",owner)

    def test_independent_clients_do_not_dispatch_or_start_gateway(self):
        wf=(Path(__file__).resolve().parents[1]/
            ".github/workflows/mmibkr-gh-independent-readers-r1.yml").read_text()
        self.assertIn("tag:mmibkr-reader",wf)
        self.assertIn("gateway_run_id",wf)
        self.assertIn("REAL_API_CLIENT_OVERLAP_AND_A_TO_B_HANDOFF=PASS",wf)
        self.assertIn("MMIBKR_GATEWAY_POOL", wf.upper())
        for line in wf.splitlines():
            if "docker run" in line or "gh api -X POST" in line:
                raise AssertionError("independent runner must not start Gateway or dispatch work")


class GatewayTCPRelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_opaque_bytes_roundtrip_without_broker_logic(self):
        async def echo(r, w):
            try:
                while data := await r.read(65536):
                    w.write(data)
                    await w.drain()
            finally:
                w.close()
                await w.wait_closed()

        upstream = await asyncio.start_server(echo,"127.0.0.1",0)
        port=upstream.sockets[0].getsockname()[1]
        proxy = await asyncio.start_server(
            lambda r,w: bridge(r,w,upstream_port=port),"127.0.0.1",0)
        proxyport=proxy.sockets[0].getsockname()[1]
        try:
            reader,writer=await asyncio.open_connection("127.0.0.1",proxyport)
            payload=b"opaque\\x00IBKR\\xffrequest"
            writer.write(payload)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)),2),payload)
            writer.close()
            await writer.wait_closed()
        finally:
            proxy.close()
            upstream.close()
            await proxy.wait_closed()
            await upstream.wait_closed()


if __name__ == "__main__":
    unittest.main()
