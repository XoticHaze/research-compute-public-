from __future__ import annotations

"""Strict read-only IBKR broker/data acceptance probe.

Public output deliberately contains only proof metadata/counts. Account values,
positions, order details, and OHLC data are never printed by this probe.
"""

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from ib_insync import IB, Stock


def _positive_number(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def run_probe(*, host: str, port: int, client_id: int, symbol: str, output: Path) -> dict:
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=30, readonly=True)
        if not ib.isConnected():
            raise RuntimeError("ibkr_connect_not_ready")

        managed = list(ib.managedAccounts() or [])
        if not managed:
            raise RuntimeError("ibkr_managed_accounts_missing")
        all_paper_du = all(str(account).upper().startswith("DU") for account in managed)
        if not all_paper_du:
            raise RuntimeError("ibkr_non_paper_account_observed")

        broker_time = ib.reqCurrentTime()
        if broker_time is None:
            raise RuntimeError("ibkr_current_time_missing")

        summary = list(ib.accountSummary() or [])
        tags = {str(row.tag): row.value for row in summary if getattr(row, "tag", None)}
        if not _positive_number(tags.get("NetLiquidation")):
            raise RuntimeError("ibkr_net_liquidation_missing")

        positions = list(ib.positions() or [])
        open_orders = list(ib.openOrders() or [])

        contract = Stock(symbol.upper(), "SMART", "USD")
        qualified = ib.qualifyContracts(contract)
        if not qualified or not getattr(qualified[0], "conId", 0):
            raise RuntimeError("ibkr_history_contract_not_qualified")
        bars = ib.reqHistoricalData(
            qualified[0],
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="15 mins",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1,
            keepUpToDate=False,
            timeout=45,
        )
        if not bars:
            raise RuntimeError("ibkr_historical_bars_empty")

        receipt = {
            "schema": "mmibkr-ibkr-readonly-data-proof-v1",
            "ok": True,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "broker_session": {
                "connected": True,
                "readonly_client": True,
                "paper_accounts_only": True,
                "managed_account_count": len(managed),
                "broker_time_present": True,
                "account_summary_rows": len(summary),
                "net_liquidation_positive": True,
                "position_count": len(positions),
                "open_order_count": len(open_orders),
            },
            "historical_data": {
                "symbol": symbol.upper(),
                "qualified": True,
                "bar_size": "15 mins",
                "duration": "2 D",
                "bar_count": len(bars),
                "first_bar_time": str(bars[0].date),
                "last_bar_time": str(bars[-1].date),
                "ohlc_values_emitted": False,
            },
            "boundaries": {
                "paper_only": True,
                "read_only": True,
                "submit_called": False,
                "cancel_called": False,
                "flatten_called": False,
                "credentials_emitted": False,
                "account_values_emitted": False,
                "position_details_emitted": False,
            },
        }
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("IBKR_READONLY_DATA_PROOF=" + json.dumps(receipt, sort_keys=True))
        return receipt
    finally:
        if ib.isConnected():
            ib.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--client-id", type=int, default=78)
    parser.add_argument("--symbol", default="AMAT")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run_probe(host=args.host, port=args.port, client_id=args.client_id, symbol=args.symbol, output=Path(args.output))


if __name__ == "__main__":
    main()
