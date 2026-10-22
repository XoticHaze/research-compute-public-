from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import tempfile
import socket
import threading
import subprocess
import unittest

from scripts.mmibkr_gh_gateway_readonly_client_v1 import (
    account_receipt,
    contract_scope,
    gateway_name,
    reader_client_id,
)
from scripts.mmibkr_gateway_account_attestor_v1 import (
    SCHEMA, HOST, AccountOracle, attest_account, matched, read_expected,
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

    def test_github_reader_client_identity_is_attempt_and_phase_scoped(self):
        first_a=reader_client_id("39864112329","1","A")
        retry_a=reader_client_id("39864112329","2","A")
        first_b=reader_client_id("39864112329","1","B")
        self.assertEqual(len({first_a,retry_a,first_b}),3)
        self.assertLess(max(first_a,retry_a,first_b),2**31)
        for attempt in ("0","100","-1","abc"):
            with self.assertRaises(ValueError):
                reader_client_id("39864112329",attempt,"A")
        with self.assertRaises(ValueError):
            reader_client_id("39864112329","1","WRITE")

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

    def test_owner_attestation_preserves_existing_exact_account_fence(self):
        calls=[]
        def verify(candidate,run_id):
            calls.append((candidate,run_id))
        class SingleAccount(ReadOnlyFakeBroker):
            def managedAccounts(self):
                return ["U-EXPECTED"]
            def reqPositions(self):
                return [SimpleNamespace(account="U-EXPECTED")]
        r=account_receipt(SingleAccount(),"",
                          run_id="39499524894",phase="A",client_id=101,
                          specs=[],attestor=verify)
        self.assertTrue(r["owner_attested_account_match"])
        self.assertEqual(calls,[("U-EXPECTED","39499524894")])
        self.assertNotIn("U-EXPECTED",str(r))

    def test_owner_attestation_fails_closed_on_ambiguous_live_accounts(self):
        class Multiple(ReadOnlyFakeBroker):
            def managedAccounts(self):
                return ["U-EXPECTED","U-OTHER"]
        with self.assertRaisesRegex(RuntimeError,"ambiguous_live_account_identity"):
            account_receipt(Multiple(),"",run_id="39499524894",
                            phase="B",client_id=102,specs=[],
                            attestor=lambda *_: None)

    def test_owner_attestation_fails_on_other_account_positions(self):
        class OtherPositions(ReadOnlyFakeBroker):
            def reqPositions(self):
                return [SimpleNamespace(account="U-OTHER")]
        with self.assertRaisesRegex(RuntimeError,"cross_account_records_rejected"):
            account_receipt(OtherPositions(),"",run_id="39499524894",
                            phase="A",client_id=101,specs=[],
                            attestor=lambda *_: None)

    def test_identity_oracle_rejects_wrong_run_wrong_account_and_paper(self):
        good={"schema":SCHEMA,"gateway_run_id":"39499524894","candidate":"U-EXPECTED"}
        self.assertTrue(matched(good,run_id="39499524894",expected="U-EXPECTED"))
        for row in (
            {**good,"gateway_run_id":"39499524895"},
            {**good,"candidate":"U-OTHER"},
            {**good,"candidate":"DU123"},
            {**good,"extra":"leak"},
        ):
            self.assertFalse(matched(row,run_id="39499524894",expected="U-EXPECTED"))

    def test_identity_oracle_localhost_roundtrip_no_expected_disclosure(self):
        with AccountOracle((HOST,0),expected="U-EXPECTED",
                           run_id="39499524894") as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            port=server.server_address[1]
            try:
                attest_account("U-EXPECTED","39499524894",port=port)
                for value,owner in (("U-OTHER","39499524894"),("U-EXPECTED","39499524895")):
                    with self.assertRaisesRegex(RuntimeError,"expected_live_account_mismatch"):
                        attest_account(value,owner,port=port)
            finally:
                server.shutdown()
                thread.join(timeout=3)

    def test_owner_attestor_env_shape_and_permissions_contract(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"account.env"
            p.write_text("MMIBKR_PRODUCTION_LIVE_ACCOUNT=U-EXPECTED\n")
            self.assertEqual(read_expected(p),"U-EXPECTED")
            p.write_text("MMIBKR_PRODUCTION_LIVE_ACCOUNT=DU1\n")
            with self.assertRaisesRegex(ValueError,"live_expected_account_required"):
                read_expected(p)

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
        self.assertIn("MMIBKR_GATEWAY_POOL_BROKER_RECOVERY_BUDGET_EXPIRED=1",owner)
        self.assertIn("MMIBKR_READONLY_AB_DISPATCHED_EXACT_OWNER=1",owner)
        self.assertIn("actions: write",owner)
        self.assertIn("mmibkr_gateway_account_attestor_v1",owner)
        # CI must parse the exact holding shell, including heredoc and
        # branch-only reader dispatch, before we ask for attended IB Key.
        hold=owner.split("      - name: Hold one authenticated read-only Gateway for independent GitHub compute jobs",1)[1]
        hold=hold.split("      - name: Confirm no-order admission did not authorize live bot startup",1)[0]
        script=hold.split("        run: |",1)[1]
        source="\n".join(line[10:] if line.startswith("          ") else line
                           for line in script.splitlines())
        subprocess.run(["bash","-n"],input=source,text=True,check=True)
        assert 'inputs[network_transport]=cloudflare_access_ssh' in source
        assert 'inputs[gateway_run_id]=$GITHUB_RUN_ID' in source
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
        self.assertIn("MMIBKR_CF_ACCOUNT_ATTESTOR_FORWARD=1",wf)
        self.assertIn("MMIBKR_EXACT_ACTIVE_READONLY_OWNER_DISPATCHED=",wf)
        self.assertIn("READER_EXACT_NEW_REQUEST_INVALID=1",wf)
        fire=wf.split("  dispatch_readonly_reader:",1)[1].split("  contract:",1)[0]
        script=fire.split("        run: |",1)[1]
        source="\n".join(line[10:] if line.startswith("          ") else line for line in script.splitlines())
        subprocess.run(["bash","-n"],input=source,text=True,check=True)
        self.assertIn('test -n "$ACCOUNT" && test -n "$TS_ID"',wf)
        self.assertNotIn('test -n "$ACCOUNT"\\n          if',wf)
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
