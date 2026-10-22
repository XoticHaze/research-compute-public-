from __future__ import annotations

"""Read-only cross-GitHub-runner probe against the *same* authenticated Gateway.

No login, order, cancel, flatten, or whatIf paths. Gateway independently
enforces READ_ONLY_API=yes. This module does not handle credentials.
"""

import argparse
import ipaddress
import json
import os
from pathlib import Path
from time import sleep, time
from datetime import datetime, timezone

from scripts.mmibkr_gateway_account_attestor_v1 import attest_account


def reader_client_id(run_id: str, attempt: str, phase: str) -> int:
    """Give each isolated runner and GitHub retry a distinct broker client ID.

    A remote socket may disconnect while IBKR still retains the old client ID.
    Reusing it is not evidence that Gateway authentication has failed.
    """
    if not run_id.isascii() or not run_id.isdigit() or not attempt.isascii() or not attempt.isdigit():
        raise ValueError("exact_github_run_attempt_required")
    a = int(attempt)
    if not 1 <= a <= 99 or phase not in {"A", "B"}:
        raise ValueError("bounded_reader_client_identity_required")
    return (int(run_id) % 1_000_000) * 1000 + a * 2 + (0 if phase == "A" else 1)


def gateway_name(run_id: str) -> str:
    if not run_id.isascii() or not run_id.isdigit() or not 8 <= len(run_id) <= 24:
        raise ValueError("gateway_pool_exact_run_id_required")
    return "mmibkr-gw-" + run_id


def contract_scope(specs: list[dict]) -> list[dict]:
    """Demand fully specified IDs. Nothing is inferred from a symbol."""
    out = []
    for row in specs:
        if not isinstance(row, dict):
            raise ValueError("exact_contract_descriptor_required")
        typ = str(row.get("secType") or "").upper()
        conid = row.get("conId")
        symbol = str(row.get("symbol") or "")
        if typ not in {"STK", "FUT", "OPT"} or type(conid) is not int or conid <= 0 or not symbol:
            raise ValueError("exact_stock_future_option_identity_required")
        expiry = str(row.get("lastTradeDateOrContractMonth") or "")
        if typ in {"FUT", "OPT"} and (not expiry or not expiry.isdigit()):
            raise ValueError("exact_expiry_required")
        if typ == "FUT" and len(expiry) != 8:
            raise ValueError("exact_dated_futures_expiry_required")
        if typ == "OPT" and (
            str(row.get("right") or "").upper() not in {"C", "P"}
            or row.get("strike") is None or not row.get("multiplier")
        ):
            raise ValueError("full_option_identity_required")
        out.append(dict(row))
    return out


def verify_contracts(ib, specs):
    if not specs:
        return []
    from ib_insync import Contract
    ret = []
    for row in contract_scope(specs):
        contract = Contract(**row)
        details = list(ib.reqContractDetails(contract))
        def matches(c):
            if c.conId != row["conId"] or c.secType.upper() != row["secType"].upper():
                return False
            for field in ("symbol","localSymbol","lastTradeDateOrContractMonth","right","multiplier","tradingClass"):
                if field in row and str(getattr(c, field, "")) != str(row[field]):
                    return False
            if "strike" in row and abs(float(getattr(c, "strike", -1)) - float(row["strike"])) > 1e-7:
                return False
            return True
        found=[d for d in details if matches(d.contract)]
        ret.append({"asset_class":row["secType"],"symbol":row["symbol"],
                    "exact_con_id_matched":len(found)==1,
                    "qualified_contract_count":len(details)})
    return ret


def account_receipt(ib, expected: str, *, run_id: str, phase: str, client_id: int,
                    specs: list[dict], attestor=None) -> dict:
    accounts = [str(a) for a in ib.managedAccounts()]
    verified_by_owner = False
    if attestor is not None:
        # Owner-validated identity over the existing pinned SSH connection.
        # Multiple production accounts are ambiguous; never guess one.
        live = [a for a in accounts if a and not a.upper().startswith("DU")]
        if len(live) != 1:
            raise RuntimeError("gateway_pool_ambiguous_live_account_identity")
        expected = live[0]
        attestor(expected, run_id)
        verified_by_owner = True
    if not expected or expected.upper().startswith("DU") or expected not in accounts:
        raise RuntimeError("gateway_pool_expected_live_account_mismatch")
    positions = list(ib.reqPositions())
    orders = list(ib.reqAllOpenOrders())
    executions = list(ib.reqExecutions())
    posacc = [str(getattr(x,"account","")) for x in positions]
    ordacc = [str(getattr(getattr(x,"order",None),"account","")) for x in orders]
    execacc = [str(getattr(getattr(x,"execution",None),"acctNumber","")) for x in executions]
    if not all(posacc+ordacc+execacc):
        raise RuntimeError("gateway_pool_ambiguous_order_position_or_execution_account")
    if verified_by_owner and any(a != expected for a in posacc+ordacc+execacc):
        raise RuntimeError("gateway_pool_cross_account_records_rejected")
    contracts=verify_contracts(ib,specs)
    return {
        "schema":"mmibkr.github_split_gateway_api_readonly.v1",
        "at_utc":datetime.now(timezone.utc).isoformat(),
        "gateway_run_id":str(run_id),
        "phase":phase,
        "client_id":client_id,
        "ok":all(c["exact_con_id_matched"] for c in contracts),
        "account_matched":True,
        "owner_attested_account_match":verified_by_owner,
        "managed_account_count":len(accounts),
        "account_positions":posacc.count(expected),
        "account_orders":ordacc.count(expected),
        "account_executions":execacc.count(expected),
        "contracts":contracts,
        "broker_api_readonly_enforced_by_gateway":True,
        "broker_mutations_attempted":False,
        "ibkey_prompt_absence_independently_verified":False,
        "canonical_submit_gate_acceptance_proven":False,
    }


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--gateway-run-id",required=True)
    p.add_argument("--host",required=True)
    p.add_argument("--transport",choices=("tailscale","cloudflare_access_ssh"),default="tailscale")
    p.add_argument("--port",type=int,default=4001)
    p.add_argument("--phase",choices=["A","B","B_AFTER_A"],required=True)
    p.add_argument("--hold-seconds",type=int,default=0)
    p.add_argument("--output",required=True)
    p.add_argument("--contracts-file",default="")
    a=p.parse_args()
    if not 0 <= a.hold_seconds <= 420:
        raise SystemExit("invalid_hold_seconds")
    if a.transport == "tailscale":
        if a.host != gateway_name(a.gateway_run_id) or a.port != 4001:
            raise SystemExit("gateway_host_not_run_bound")
    else:
        if a.host != "127.0.0.1" or a.port != 14001:
            raise SystemExit("cloudflare_ssh_exact_local_forward_required")
        if os.getenv("MMIBKR_CF_SSH_FORWARD_ATTESTED") != "1":
            raise SystemExit("cloudflare_ssh_pinned_forward_required")
    attestor = None
    if a.transport == "cloudflare_access_ssh":
        if os.getenv("MMIBKR_CF_ACCOUNT_ATTESTOR_FORWARD") != "1":
            raise SystemExit("owner_account_attestor_forward_not_verified")
        expected = ""
        attestor = attest_account
    else:
        expected = os.environ.get("MMIBKR_PRODUCTION_LIVE_ACCOUNT","")
        if not expected or expected.upper().startswith("DU"):
            raise SystemExit("exact_live_account_secret_missing_or_paper")
    from ib_insync import IB
    specs=[]
    if a.contracts_file:
        specs=contract_scope(json.loads(Path(a.contracts_file).read_text(encoding="utf-8")))
    client_id=reader_client_id(os.environ["GITHUB_RUN_ID"],os.environ.get("GITHUB_RUN_ATTEMPT","1"),a.phase)
    ib=IB()
    results={}
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    try:
        ib.connect(a.host,a.port,clientId=client_id,readonly=True,timeout=20)
        if not ib.isConnected():
            raise RuntimeError("remote_broker_api_not_connected")
        results=account_receipt(ib,expected,run_id=a.gateway_run_id,
                                phase=a.phase,client_id=client_id,specs=specs,attestor=attestor)
        # Retain source-backed initial read evidence if the socket disconnects
        # during the hold. An interrupted hold is still a FAILED session.
        out.write_text(json.dumps(results,sort_keys=True,indent=2)+"\n")
        if a.hold_seconds:
            try:
                ib.sleep(a.hold_seconds)
            except Exception as exc:
                results["hold_interrupted_class"]=type(exc).__name__
                results["api_disconnected_utc"]=datetime.now(timezone.utc).isoformat()
                out.write_text(json.dumps(results,sort_keys=True,indent=2)+"\n")
                print("MMIBKR_SPLIT_POOL_HOLD_INTERRUPTED=1")
                raise
            results["post_hold"]=account_receipt(
                ib,expected,run_id=a.gateway_run_id,phase="B_AFTER_A" if a.phase == "B" else a.phase,
                client_id=client_id,specs=specs,attestor=attestor,
            )
    finally:
        if ib.isConnected():ib.disconnect()
    results["api_disconnected_utc"]=datetime.now(timezone.utc).isoformat()
    out.write_text(json.dumps(results,sort_keys=True,indent=2)+"\n")
    print(f"MMIBKR_SPLIT_POOL_{a.phase}_REMOTE_ACCOUNT_READ={'PASS' if results.get('ok') else 'FAIL'}")
    print("MMIBKR_SPLIT_POOL_BROKER_MUTATIONS=0")
    return 0 if results.get("ok") and results.get("post_hold",{}).get("ok",True) else 1


if __name__=="__main__":
    raise SystemExit(main())
