#!/usr/bin/env python3
"""Materialize the first canonical downstream boundary from an authenticated IBKR session.

This is deliberately broader than a connectivity probe: it proves paper/read-only
broker state access, position/order readability, contract resolution, and emits
IBKR history through the existing ``research.forward_bar.v2`` contract.  It does
not submit orders and does not pretend broker bars are completed-trade evidence;
trade pairing / Strategy Health ingestion remains downstream of this boundary.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ib_insync import IB, Stock

from research.forward_bar_contract_v2 import ForwardBarContract, ibkr_bar_to_record, normalize_frame


def _jsonable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return value.item()
    except AttributeError:
        return value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=78)
    ap.add_argument("--symbols", default="AMAT,APH")
    ap.add_argument("--output", required=True, help="Sanitized broker/session handoff JSON")
    ap.add_argument("--bars-output", required=True, help="Canonical research.forward_bar.v2 JSONL")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("at least one symbol is required")

    ib = IB()
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=10, readonly=True)
        if not ib.isConnected():
            raise RuntimeError("IBKR API connection did not become ready")

        managed_accounts = list(ib.managedAccounts())
        if not managed_accounts:
            raise RuntimeError("authenticated session exposed no managed account")
        paper_accounts = [a for a in managed_accounts if a.upper().startswith("D")]
        if not paper_accounts:
            raise RuntimeError("authenticated session is not a paper account")

        current_time = ib.reqCurrentTime()
        account_summary = list(ib.accountSummary())
        positions = list(ib.positions())
        # Request the account-wide open-order view.  This is still read-only and
        # proves the consumer can inspect execution state without submitting.
        ib.reqAllOpenOrders()
        ib.sleep(1)
        open_orders = list(ib.openOrders())

        symbol_receipts: list[dict[str, object]] = []
        records: list[dict[str, object]] = []
        for symbol in symbols:
            contract = Stock(symbol, "SMART", "USD")
            qualified = ib.qualifyContracts(contract)
            if not qualified:
                raise RuntimeError(f"contract qualification failed for {symbol}")
            resolved = qualified[0]
            bars = ib.reqHistoricalData(
                resolved,
                endDateTime="",
                durationStr="2 D",
                barSizeSetting="5 mins",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=2,
                keepUpToDate=False,
            )
            if not bars:
                raise RuntimeError(f"historical data returned no bars for {symbol}")
            records.extend(
                ibkr_bar_to_record(
                    bar,
                    resolved,
                    symbol=symbol,
                    asset_type="STK",
                    bar_size="5 mins",
                    session="all",
                    source="ibkr",
                )
                for bar in bars
            )
            symbol_receipts.append(
                {
                    "symbol": symbol,
                    "contract_qualified": True,
                    "contract_id": f"conid:{resolved.conId}" if resolved.conId else (resolved.localSymbol or symbol),
                    "historical_data_ready": True,
                    "historical_bar_count": len(bars),
                }
            )

        frame = normalize_frame(records)
        bars_path = Path(args.bars_output)
        with bars_path.open("w", encoding="utf-8") as fh:
            for row in frame.to_dict(orient="records"):
                fh.write(json.dumps({k: _jsonable(v) for k, v in row.items()}, sort_keys=True) + "\n")

        receipt = {
            "schema": "mmibkr-ibkr-post-auth-handoff-v2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trading_mode": "paper",
            "read_only": True,
            "api_connected": True,
            "authenticated_session": True,
            "paper_account_verified": True,
            "managed_account_count": len(managed_accounts),
            "account_summary_readable": bool(account_summary),
            "account_summary_field_count": len(account_summary),
            "positions_readable": True,
            "position_count": len(positions),
            "open_orders_readable": True,
            "open_order_count": len(open_orders),
            "broker_time_readable": current_time is not None,
            "symbols": symbol_receipts,
            "forward_bar_contract": ForwardBarContract().schema,
            "forward_bar_count": int(len(frame)),
            "forward_bar_symbols": sorted(frame["symbol"].unique().tolist()),
            "capabilities": {
                "account_state": True,
                "positions": True,
                "open_orders": True,
                "contract_qualification": True,
                "historical_market_data": True,
                "canonical_forward_bar_materialization": True,
                "order_submission": False,
            },
            "completed_trade_evidence_materialized": False,
            "consumer_ready": True,
        }
        Path(args.output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print("IBKR_POST_AUTH_PIPELINE=" + json.dumps(receipt, sort_keys=True))
        print("IBKR_FORWARD_BAR_V2_READY=1")
        print("IBKR_CONSUMER_READY=1")
        return 0
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
