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
import sys
from datetime import datetime, timezone
from pathlib import Path

# This file is intentionally executable directly (``python scripts/...py``) from
# CI/operator surfaces.  In that invocation Python places ``scripts/`` rather
# than the repository root on sys.path, so make the repo-owned ``research``
# package importable without depending on caller-specific PYTHONPATH state.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ib_insync import Contract, IB, Stock

from research.forward_bar_contract_v2 import ForwardBarContract, ibkr_bar_to_record, normalize_frame


def _jsonable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return value.item()
    except AttributeError:
        return value


CONTRACT_HINT_FIELDS = (
    "conId",
    "symbol",
    "secType",
    "exchange",
    "primaryExchange",
    "currency",
    "localSymbol",
    "tradingClass",
    "lastTradeDateOrContractMonth",
    "strike",
    "right",
    "multiplier",
    "includeExpired",
)
SUPPORTED_READ_SEC_TYPES = {"STK", "FUT", "OPT"}


def parse_contract_hints(raw: str) -> dict[str, dict[str, object]]:
    if not str(raw or "").strip():
        return {}
    try:
        node = json.loads(raw)
    except Exception as exc:
        raise RuntimeError("contract hints JSON is invalid") from exc
    if not isinstance(node, dict):
        raise RuntimeError("contract hints must be an object keyed by symbol")

    out: dict[str, dict[str, object]] = {}
    for raw_symbol, raw_hint in node.items():
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol or not isinstance(raw_hint, dict):
            raise RuntimeError("contract hint entry is invalid")
        hint_symbol = str(raw_hint.get("symbol") or symbol).strip().upper()
        if hint_symbol != symbol:
            raise RuntimeError(f"contract hint symbol mismatch for {symbol}")
        sec_type = str(raw_hint.get("secType") or "").strip().upper()
        if not sec_type:
            raise RuntimeError(f"contract hint secType required for {symbol}")
        if sec_type not in SUPPORTED_READ_SEC_TYPES:
            raise RuntimeError(f"contract hint secType unsupported for warm read {symbol}: {sec_type}")
        try:
            con_id = int(raw_hint.get("conId") or 0)
        except (TypeError, ValueError):
            con_id = 0
        if sec_type != "STK" and con_id <= 0:
            raise RuntimeError(f"explicit conId required for non-stock contract {symbol}")
        if sec_type == "OPT":
            right = str(raw_hint.get("right") or "").strip().upper()
            try:
                strike = float(raw_hint.get("strike"))
            except (TypeError, ValueError):
                strike = 0.0
            if right not in {"C", "P"} or strike <= 0:
                raise RuntimeError(f"exact option right/strike required for {symbol}")

        clean: dict[str, object] = {}
        for field in CONTRACT_HINT_FIELDS:
            value = raw_hint.get(field)
            if value not in (None, ""):
                clean[field] = value
        clean["symbol"] = symbol
        clean["secType"] = sec_type
        if con_id > 0:
            clean["conId"] = con_id
        out[symbol] = clean
    return out


def contract_request_for_symbol(
    symbol: str,
    hints: dict[str, dict[str, object]],
) -> tuple[Contract, dict[str, object]]:
    symbol = str(symbol or "").strip().upper()
    hint = hints.get(symbol)
    if not hint:
        return Stock(symbol, "SMART", "USD"), {
            "source": "public_stock_fallback",
            "symbol": symbol,
            "secType": "STK",
            "exchange": "SMART",
            "currency": "USD",
        }

    kwargs: dict[str, object] = {}
    for field in CONTRACT_HINT_FIELDS:
        value = hint.get(field)
        if value not in (None, ""):
            kwargs[field] = value
    kwargs["symbol"] = symbol
    kwargs["secType"] = str(hint.get("secType") or "").upper()
    return Contract(**kwargs), {
        "source": "mm_selected_runtime_execution_contract",
        **{k: v for k, v in kwargs.items() if v not in (None, "")},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=78)
    ap.add_argument("--symbols", default="AMAT,APH")
    ap.add_argument("--contracts-json", default="", help="Optional exact MM-selected execution contracts keyed by symbol")
    ap.add_argument("--output", required=True, help="Sanitized broker/session handoff JSON")
    ap.add_argument("--bars-output", required=True, help="Canonical research.forward_bar.v2 JSONL")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("at least one symbol is required")
    contract_hints = parse_contract_hints(args.contracts_json)
    unexpected_hints = sorted(set(contract_hints) - set(symbols))
    if unexpected_hints:
        raise RuntimeError("contract hints include unrequested symbols: " + ",".join(unexpected_hints))

    ib = IB()
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=10, readonly=True)
        if not ib.isConnected():
            raise RuntimeError("IBKR API connection did not become ready")

        managed_accounts = list(ib.managedAccounts())
        if not managed_accounts:
            raise RuntimeError("authenticated session exposed no managed account")
        paper_accounts = [a for a in managed_accounts if str(a).upper().startswith("DU")]
        if not paper_accounts:
            raise RuntimeError("authenticated session is not a DU paper account")

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
            contract, contract_request = contract_request_for_symbol(symbol, contract_hints)
            qualified = ib.qualifyContracts(contract)
            if not qualified:
                raise RuntimeError(f"contract qualification failed for {symbol}")
            resolved = qualified[0]
            if contract_request.get("source") == "mm_selected_runtime_execution_contract":
                requested_con_id = int(contract_request.get("conId") or 0)
                resolved_con_id = int(getattr(resolved, "conId", 0) or 0)
                if requested_con_id > 0 and resolved_con_id != requested_con_id:
                    raise RuntimeError(f"qualified contract conId mismatch for {symbol}")
                requested_sec_type = str(contract_request.get("secType") or "").upper()
                resolved_sec_type = str(getattr(resolved, "secType", "") or "").upper()
                if requested_sec_type and resolved_sec_type != requested_sec_type:
                    raise RuntimeError(f"qualified contract secType mismatch for {symbol}")
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
                    asset_type=str(getattr(resolved, "secType", "") or contract_request.get("secType") or "STK"),
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
                    "contract_source": contract_request.get("source"),
                    "requested_contract": contract_request,
                    "resolved_contract": {
                        "conId": int(getattr(resolved, "conId", 0) or 0),
                        "symbol": str(getattr(resolved, "symbol", "") or ""),
                        "secType": str(getattr(resolved, "secType", "") or ""),
                        "exchange": str(getattr(resolved, "exchange", "") or ""),
                        "currency": str(getattr(resolved, "currency", "") or ""),
                        "localSymbol": str(getattr(resolved, "localSymbol", "") or ""),
                        "tradingClass": str(getattr(resolved, "tradingClass", "") or ""),
                        "lastTradeDateOrContractMonth": str(getattr(resolved, "lastTradeDateOrContractMonth", "") or ""),
                        "strike": float(getattr(resolved, "strike", 0.0) or 0.0),
                        "right": str(getattr(resolved, "right", "") or ""),
                        "multiplier": str(getattr(resolved, "multiplier", "") or ""),
                    },
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
            "requested_symbols": symbols,
            "contract_hint_symbols": sorted(contract_hints),
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
