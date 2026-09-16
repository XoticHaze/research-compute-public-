#!/usr/bin/env python3
"""Prove the authenticated read-only IBKR session is usable by downstream consumers.

No orders are submitted and no raw market prices are persisted.  The output is a
sanitized capability/session receipt that can be used as the handoff boundary
for later research/market-data consumers in the same protected execution path.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ib_insync import IB, Stock


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=78)
    ap.add_argument("--symbols", default="AMAT,APH")
    ap.add_argument("--output", required=True)
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
        open_orders = list(ib.openOrders())

        symbol_receipts: list[dict[str, object]] = []
        for symbol in symbols:
            contract = Stock(symbol, "SMART", "USD")
            qualified = ib.qualifyContracts(contract)
            if not qualified:
                raise RuntimeError(f"contract qualification failed for {symbol}")
            bars = ib.reqHistoricalData(
                qualified[0],
                endDateTime="",
                durationStr="2 D",
                barSizeSetting="5 mins",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=1,
                keepUpToDate=False,
            )
            if not bars:
                raise RuntimeError(f"historical data returned no bars for {symbol}")
            symbol_receipts.append(
                {
                    "symbol": symbol,
                    "contract_qualified": True,
                    "historical_data_ready": True,
                    "historical_bar_count": len(bars),
                }
            )

        receipt = {
            "schema": "mmibkr-ibkr-post-auth-handoff-v1",
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
            "capabilities": {
                "account_state": True,
                "positions": True,
                "open_orders": True,
                "contract_qualification": True,
                "historical_market_data": True,
                "order_submission": False,
            },
            "raw_market_data_persisted": False,
            "consumer_ready": True,
        }
        Path(args.output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print("IBKR_POST_AUTH_PIPELINE=" + json.dumps(receipt, sort_keys=True))
        print("IBKR_CONSUMER_READY=1")
        return 0
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
