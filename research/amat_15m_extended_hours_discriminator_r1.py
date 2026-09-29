from __future__ import annotations

"""Bounded read-only AMAT 15m historical TRADES extended-hours discriminator."""

import argparse
import json
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ib_insync import IB, Stock

SCHEMA = "market_research.amat_15m_userth_discriminator.r1"
NY = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def _bar_dt(value) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError("historical_bar_datetime_required")
    if value.tzinfo is None:
        raise RuntimeError("historical_bar_timezone_required")
    return value.astimezone(NY)


def summarize(bars, *, target_date: str) -> dict:
    target = datetime.fromisoformat(target_date).date()
    rows = [_bar_dt(getattr(bar, "date", None)) for bar in bars]
    rows = [dt for dt in rows if dt.date() == target]
    rth = [dt for dt in rows if RTH_OPEN <= dt.time().replace(tzinfo=None) < RTH_CLOSE]
    ext = [dt for dt in rows if not (RTH_OPEN <= dt.time().replace(tzinfo=None) < RTH_CLOSE)]
    return {
        "target_date": target.isoformat(),
        "bar_count": len(rows),
        "rth_clock_count": len(rth),
        "extended_clock_count": len(ext),
        "first_bar_time_et": rows[0].isoformat() if rows else None,
        "last_bar_time_et": rows[-1].isoformat() if rows else None,
    }


def run(*, host: str, port: int, client_id: int, symbol: str, target_date: str, output: Path) -> dict:
    target = datetime.fromisoformat(target_date).date()
    end = datetime.combine(target, time(23, 59), tzinfo=NY)
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=30, readonly=True)
        if not ib.isConnected():
            raise RuntimeError("ibkr_connect_not_ready")
        managed = list(ib.managedAccounts() or [])
        if not managed or not all(str(x).upper().startswith("DU") for x in managed):
            raise RuntimeError("paper_account_only_required")
        contract = Stock(symbol.upper(), "SMART", "USD")
        qualified = ib.qualifyContracts(contract)
        if not qualified or not getattr(qualified[0], "conId", 0):
            raise RuntimeError("contract_qualification_failed")

        unrestricted = ib.reqHistoricalData(
            qualified[0],
            endDateTime=end,
            durationStr="2 D",
            barSizeSetting="15 mins",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=2,
            keepUpToDate=False,
            timeout=60,
        )
        rth_only = ib.reqHistoricalData(
            qualified[0],
            endDateTime=end,
            durationStr="2 D",
            barSizeSetting="15 mins",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=2,
            keepUpToDate=False,
            timeout=60,
        )
        unrestricted_summary = summarize(unrestricted, target_date=target_date)
        rth_summary = summarize(rth_only, target_date=target_date)
        if unrestricted_summary["bar_count"] <= 0:
            raise RuntimeError("unrestricted_target_date_empty")
        if rth_summary["bar_count"] <= 0:
            raise RuntimeError("rth_target_date_empty")
        if unrestricted_summary["bar_count"] < rth_summary["bar_count"]:
            raise RuntimeError("unrestricted_bar_count_less_than_rth")
        if rth_summary["extended_clock_count"] != 0:
            raise RuntimeError("rth_response_contains_extended_clock_bars")

        receipt = {
            "schema": SCHEMA,
            "ok": True,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol.upper(),
            "target_date": target.isoformat(),
            "contract": {"qualified": True, "conId_present": True, "secType": "STK", "exchange": "SMART", "currency": "USD"},
            "request": {"bar_size": "15 mins", "what_to_show": "TRADES", "format_date": 2, "comparison": ["useRTH=false", "useRTH=true"]},
            "unrestricted": unrestricted_summary,
            "rth_only": rth_summary,
            "supports_non_rth_historical_trades": unrestricted_summary["extended_clock_count"] > 0,
            "boundaries": {
                "readonly_client": True, "paper_accounts_only": True, "broker_order_action": False,
                "submit_called": False, "cancel_called": False, "flatten_called": False,
                "ohlc_values_emitted": False, "account_values_emitted": False,
                "credentials_emitted": False, "live_execution_allowed": False,
            },
        }
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("AMAT_15M_EXTENDED_HOURS_DISCRIMINATOR=" + json.dumps(receipt, sort_keys=True))
        return receipt
    finally:
        if ib.isConnected():
            ib.disconnect()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=79)
    p.add_argument("--symbol", default="AMAT")
    p.add_argument("--target-date", default="2026-06-15")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    run(host=a.host, port=a.port, client_id=a.client_id, symbol=a.symbol, target_date=a.target_date, output=Path(a.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
