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
import math
import re
import sys
import time
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
BAR_REQUEST_FIELDS = {
    "source_timeframe",
    "target_timeframe",
    "bar_size_setting",
    "duration_str",
}
BAR_REQUEST_OPTIONAL_FIELDS = {
    "end_date_time_utc",
    "allow_empty",
}
BAR_SIZE_RE = re.compile(r"^(?:[1-9][0-9]{0,2}) (?:sec|secs|min|mins|hour|hours|day|week|month)$")
DURATION_RE = re.compile(r"^(?:[1-9][0-9]{0,5}) [SDWMY]$")
SAFE_SECONDS_MAX_BAR = {
    60: 60,
    120: 120,
    1800: 1800,
    3600: 3600,
    14400: 10800,
    28800: 28800,
}
SAFE_SECONDS_DURATIONS = set(SAFE_SECONDS_MAX_BAR)
MAX_BAR_REQUESTS = 50
HISTORICAL_CHUNK_PACE_SEC = 0.4


def _bar_size_seconds(value: str) -> int | None:
    match = re.fullmatch(
        r"([1-9][0-9]{0,2}) (sec|secs|min|mins|hour|hours|day|week|month)",
        str(value or "").strip(),
    )
    if not match:
        return None
    count = int(match.group(1))
    unit = match.group(2)
    multiplier = {
        "sec": 1,
        "secs": 1,
        "min": 60,
        "mins": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "week": 7 * 86400,
        "month": 30 * 86400,
    }[unit]
    return count * multiplier


def _seconds_duration_bar_compatible(duration: str, bar_size: str) -> bool:
    raw = str(duration or "").strip()
    if not raw.endswith(" S"):
        return True
    try:
        count = int(raw.split()[0])
    except Exception:
        return False
    bar_seconds = _bar_size_seconds(bar_size)
    return (
        count in SAFE_SECONDS_MAX_BAR
        and bar_seconds is not None
        and bar_seconds <= SAFE_SECONDS_MAX_BAR[count]
    )


def _bounded_duration(value: str) -> bool:
    match = DURATION_RE.fullmatch(str(value or "").strip())
    if not match:
        return False
    count_text, unit = str(value).split()
    count = int(count_text)
    if unit == "S":
        return count in SAFE_SECONDS_DURATIONS
    limits = {"D": 30, "W": 8, "M": 12, "Y": 7}
    return 1 <= count <= limits[unit]


def _normalize_history_end_utc(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception as exc:
        raise RuntimeError("bar request end_date_time_utc is invalid") from exc
    if parsed.tzinfo is None:
        raise RuntimeError("bar request end_date_time_utc requires explicit timezone")
    parsed = parsed.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if parsed.timestamp() > now.timestamp() + 300:
        raise RuntimeError("bar request end_date_time_utc is too far in the future")
    return parsed.isoformat().replace("+00:00", "Z")


def _ibkr_history_end(value: str):
    normalized = _normalize_history_end_utc(value)
    if not normalized:
        return ""
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def _normalize_allow_empty(value: object) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    raise RuntimeError("bar request allow_empty must be boolean")


def parse_bar_requests(raw: str, symbols: list[str]) -> dict[str, list[dict[str, str]]]:
    """Validate exact MM-supplied history requests without choosing a timeframe."""
    if not str(raw or "").strip():
        return {}
    try:
        node = json.loads(raw)
    except Exception as exc:
        raise RuntimeError("bar requests JSON is invalid") from exc
    if not isinstance(node, dict):
        raise RuntimeError("bar requests must be an object keyed by symbol")

    requested_symbols = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
    normalized: dict[str, list[dict[str, str]]] = {}
    total = 0
    for raw_symbol, rows in node.items():
        symbol = str(raw_symbol or "").strip().upper()
        if symbol not in requested_symbols:
            raise RuntimeError(f"bar requests include unrequested symbol: {symbol or 'blank'}")
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"bar requests require a non-empty list for {symbol}")
        clean_rows: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                raise RuntimeError(f"bar request field set mismatch for {symbol}")
            fields = set(raw_row)
            if not BAR_REQUEST_FIELDS.issubset(fields) or not fields.issubset(
                BAR_REQUEST_FIELDS | BAR_REQUEST_OPTIONAL_FIELDS
            ):
                raise RuntimeError(f"bar request field set mismatch for {symbol}")
            row = {key: str(raw_row.get(key) or "").strip() for key in BAR_REQUEST_FIELDS}
            row["end_date_time_utc"] = _normalize_history_end_utc(
                raw_row.get("end_date_time_utc")
            )
            row["allow_empty"] = _normalize_allow_empty(raw_row.get("allow_empty"))
            if not row["source_timeframe"] or not row["target_timeframe"]:
                raise RuntimeError(f"bar request timeframe identity missing for {symbol}")
            if not BAR_SIZE_RE.fullmatch(row["bar_size_setting"]):
                raise RuntimeError(f"bar request bar size rejected for {symbol}")
            if not _bounded_duration(row["duration_str"]):
                raise RuntimeError(f"bar request duration rejected for {symbol}")
            if not _seconds_duration_bar_compatible(
                row["duration_str"],
                row["bar_size_setting"],
            ):
                raise RuntimeError(
                    f"bar request seconds duration/bar size combination rejected for {symbol}"
                )
            identity = (
                row["source_timeframe"],
                row["target_timeframe"],
                row["bar_size_setting"],
                row["duration_str"],
                row["end_date_time_utc"],
                "1" if row["allow_empty"] else "0",
            )
            if identity in seen:
                raise RuntimeError(f"duplicate bar request for {symbol}")
            seen.add(identity)
            clean_rows.append(row)
            total += 1
            if total > MAX_BAR_REQUESTS:
                raise RuntimeError("bar request count exceeds safe bound")
        normalized[symbol] = clean_rows

    missing = sorted(requested_symbols - set(normalized))
    if missing:
        raise RuntimeError("bar requests missing requested symbols: " + ",".join(missing))
    return normalized


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
        if sec_type == "FUT" and con_id <= 0:
            expiry = str(raw_hint.get("lastTradeDateOrContractMonth") or "").strip()
            exchange = str(raw_hint.get("exchange") or "").strip()
            currency = str(raw_hint.get("currency") or "").strip()
            if not re.fullmatch(r"\\d{6}(?:\\d{2})?", expiry) or not exchange or not currency:
                raise RuntimeError(
                    f"futures read contract without conId requires exact expiry/exchange/currency for {symbol}"
                )
        elif sec_type != "STK" and con_id <= 0:
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
    source = (
        "mm_expiry_qualified_read_contract"
        if str(kwargs.get("secType") or "").upper() == "FUT" and not int(kwargs.get("conId") or 0)
        else "mm_exact_contract_hint"
    )
    return Contract(**kwargs), {
        "source": source,
        **{k: v for k, v in kwargs.items() if v not in (None, "")},
    }


def _positive_float(value):
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) and number > 0 else None


def sample_exact_contract_quote(
    ib: IB,
    contract: Contract,
    *,
    timeout_sec: float = 2.5,
    poll_interval_sec: float = 0.2,
) -> dict[str, object]:
    """Read one exact-contract quote without selecting a route or mutating broker state."""
    started = time.perf_counter()
    ticker = None
    error = None
    bid = ask = last = market_price = None
    effective_type = None
    try:
        ib.reqMarketDataType(1)
        ticker = ib.reqMktData(contract, "", False, False)
        deadline = time.monotonic() + max(0.2, min(float(timeout_sec), 10.0))
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            ib.sleep(min(max(0.05, float(poll_interval_sec)), max(0.05, remaining)))
            bid = _positive_float(getattr(ticker, "bid", None))
            ask = _positive_float(getattr(ticker, "ask", None))
            last = _positive_float(getattr(ticker, "last", None))
            try:
                market_price = _positive_float(ticker.marketPrice())
            except Exception:
                market_price = None
            effective_type = getattr(ticker, "marketDataType", None)
            if bid is not None and ask is not None:
                break
    except Exception as exc:
        error = repr(exc)
    finally:
        if ticker is not None:
            try:
                ib.cancelMktData(contract)
            except Exception:
                pass

    bid_ask = bool(bid is not None and ask is not None and bid <= ask)
    executable = bool(bid_ask and effective_type == 1)
    received = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "source": "ibkr_exact_mm_contract_reqMktData",
        "requested_market_data_type": 1,
        "effective_market_data_type": effective_type,
        "bid": bid,
        "ask": ask,
        "last": last,
        "marketPrice": market_price,
        "bid_ask_available": bid_ask,
        "executable_quote_available": executable,
        "quote_received_at_utc": received,
        "quote_age_at_response_sec": 0.0,
        "request_error": error,
        "request_elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        "route_selected_by_public": False,
        "contract_selected_by_public": False,
        "broker_mutation": False,
    }


def _dedupe_identical_history_records(records: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    """Collapse exact overlap from adjacent private-owned history chunks.

    Conflicting rows for the same normalized bar identity are intentionally
    retained so research.forward_bar.v2 rejects them as duplicate/conflicting
    source truth rather than silently choosing a price.
    """
    out: list[dict[str, object]] = []
    first_by_identity: dict[tuple[str, str, str, str], dict[str, object]] = {}
    dropped = 0
    for raw in records:
        row = dict(raw)
        timestamp = row.get("timestamp")
        timestamp_key = (
            timestamp.isoformat()
            if hasattr(timestamp, "isoformat")
            else str(timestamp)
        )
        identity = (
            str(row.get("symbol") or ""),
            timestamp_key,
            str(row.get("contract_id") or ""),
            str(row.get("bar_size") or ""),
        )
        prior = first_by_identity.get(identity)
        if prior is None:
            first_by_identity[identity] = row
            out.append(row)
            continue

        comparable_prior = {key: _jsonable(value) for key, value in prior.items()}
        comparable_row = {key: _jsonable(value) for key, value in row.items()}
        if comparable_prior == comparable_row:
            dropped += 1
            continue

        # Preserve the conflict. normalize_frame() must fail on duplicate bar
        # identity so public compute never decides which OHLC is authoritative.
        out.append(row)
    return out, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--client-id", type=int, default=78)
    ap.add_argument("--symbols", default="AMAT,APH")
    ap.add_argument("--contracts-json", default="", help="Optional exact MM-selected execution contracts keyed by symbol")
    ap.add_argument("--bar-requests-json", default="", help="Optional exact MM-owned history requests keyed by symbol")
    ap.add_argument("--include-quotes", action="store_true", help="Sample exact-contract real-time bid/ask alongside bars")
    ap.add_argument("--output", required=True, help="Sanitized broker/session handoff JSON")
    ap.add_argument("--bars-output", required=True, help="Canonical research.forward_bar.v2 JSONL")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise SystemExit("at least one symbol is required")
    contract_hints = parse_contract_hints(args.contracts_json)
    bar_requests = parse_bar_requests(args.bar_requests_json, symbols)
    unexpected_hints = sorted(set(contract_hints) - set(symbols))
    if unexpected_hints:
        raise RuntimeError("contract hints include unrequested symbols: " + ",".join(unexpected_hints))

    ib = IB()
    pipeline_started = time.perf_counter()
    connect_elapsed_ms = None
    account_state_elapsed_ms = None
    market_data_elapsed_ms = 0.0
    try:
        connect_started = time.perf_counter()
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=10, readonly=True)
        connect_elapsed_ms = round((time.perf_counter() - connect_started) * 1000.0, 3)
        if not ib.isConnected():
            raise RuntimeError("IBKR API connection did not become ready")

        managed_accounts = list(ib.managedAccounts())
        if not managed_accounts:
            raise RuntimeError("authenticated session exposed no managed account")
        paper_accounts = [a for a in managed_accounts if str(a).upper().startswith("DU")]
        if not paper_accounts:
            raise RuntimeError("authenticated session is not a DU paper account")

        account_started = time.perf_counter()
        current_time = ib.reqCurrentTime()
        account_summary = list(ib.accountSummary())
        positions = list(ib.positions())
        # Request the account-wide open-order view.  This is still read-only and
        # proves the consumer can inspect execution state without submitting.
        ib.reqAllOpenOrders()
        ib.sleep(1)
        open_orders = list(ib.openOrders())
        account_state_elapsed_ms = round((time.perf_counter() - account_started) * 1000.0, 3)

        symbol_receipts: list[dict[str, object]] = []
        records: list[dict[str, object]] = []
        for symbol in symbols:
            symbol_started = time.perf_counter()
            contract, contract_request = contract_request_for_symbol(symbol, contract_hints)
            qualify_started = time.perf_counter()
            qualified = ib.qualifyContracts(contract)
            contract_qualification_elapsed_ms = round(
                (time.perf_counter() - qualify_started) * 1000.0,
                3,
            )
            if not qualified:
                raise RuntimeError(f"contract qualification failed for {symbol}")
            resolved = qualified[0]
            if contract_request.get("source") in {
                "mm_exact_contract_hint",
                "mm_expiry_qualified_read_contract",
            }:
                requested_con_id = int(contract_request.get("conId") or 0)
                resolved_con_id = int(getattr(resolved, "conId", 0) or 0)
                if requested_con_id > 0 and resolved_con_id != requested_con_id:
                    raise RuntimeError(f"qualified contract conId mismatch for {symbol}")
                requested_sec_type = str(contract_request.get("secType") or "").upper()
                resolved_sec_type = str(getattr(resolved, "secType", "") or "").upper()
                if requested_sec_type and resolved_sec_type != requested_sec_type:
                    raise RuntimeError(f"qualified contract secType mismatch for {symbol}")
                requested_expiry = str(
                    contract_request.get("lastTradeDateOrContractMonth") or ""
                ).strip()
                resolved_expiry = str(
                    getattr(resolved, "lastTradeDateOrContractMonth", "") or ""
                ).strip()
                if (
                    requested_expiry
                    and resolved_expiry
                    and not resolved_expiry.startswith(requested_expiry[:6])
                ):
                    raise RuntimeError(f"qualified contract expiry mismatch for {symbol}")
            effective_requests = bar_requests.get(symbol) or [{
                "source_timeframe": "5Min",
                "target_timeframe": "5Min",
                "bar_size_setting": "5 mins",
                "duration_str": "2 D",
                "end_date_time_utc": "",
                "allow_empty": False,
            }]
            request_receipts: list[dict[str, object]] = []
            historical_bar_count = 0
            for bar_request in effective_requests:
                bar_size = str(bar_request["bar_size_setting"])
                duration = str(bar_request["duration_str"])
                end_date_time_utc = str(bar_request.get("end_date_time_utc") or "")
                allow_empty = bool(bar_request.get("allow_empty"))
                request_end = _ibkr_history_end(end_date_time_utc)
                request_started = time.perf_counter()
                bars = ib.reqHistoricalData(
                    resolved,
                    endDateTime=request_end,
                    durationStr=duration,
                    barSizeSetting=bar_size,
                    whatToShow="TRADES",
                    useRTH=False,
                    formatDate=2,
                    keepUpToDate=False,
                )
                if not bars and not allow_empty:
                    raise RuntimeError(
                        f"historical data returned no bars for {symbol} "
                        f"{bar_request['source_timeframe']}"
                    )
                bars = list(bars or [])
                historical_bar_count += len(bars)
                records.extend(
                    ibkr_bar_to_record(
                        bar,
                        resolved,
                        symbol=symbol,
                        asset_type=str(getattr(resolved, "secType", "") or contract_request.get("secType") or "STK"),
                        bar_size=bar_size,
                        session="all",
                        source="ibkr",
                    )
                    for bar in bars
                )
                request_elapsed_ms = round(
                    (time.perf_counter() - request_started) * 1000.0,
                    3,
                )
                market_data_elapsed_ms += request_elapsed_ms
                request_receipts.append({
                    **dict(bar_request),
                    "historical_bar_count": len(bars),
                    "request_elapsed_ms": request_elapsed_ms,
                    "maintenance_pacing_sec": (
                        HISTORICAL_CHUNK_PACE_SEC if end_date_time_utc else 0.0
                    ),
                })
                if end_date_time_utc:
                    ib.sleep(HISTORICAL_CHUNK_PACE_SEC)
            quote_snapshot = None
            if args.include_quotes:
                quote_snapshot = sample_exact_contract_quote(ib, resolved)
            symbol_receipts.append(
                {
                    "symbol": symbol,
                    "contract_qualified": True,
                    "contract_id": f"conid:{resolved.conId}" if resolved.conId else (resolved.localSymbol or symbol),
                    "historical_data_ready": True,
                    "historical_bar_count": historical_bar_count,
                    "bar_request_source": "mm_exact_bar_requests" if symbol in bar_requests else "compatibility_default_5min",
                    "bar_requests": request_receipts,
                    "quote_snapshot_requested": bool(args.include_quotes),
                    "quote_snapshot": quote_snapshot,
                    "quote_request_elapsed_ms": (
                        quote_snapshot.get("request_elapsed_ms")
                        if isinstance(quote_snapshot, dict)
                        else 0.0
                    ),
                    "contract_qualification_elapsed_ms": contract_qualification_elapsed_ms,
                    "symbol_elapsed_ms": round((time.perf_counter() - symbol_started) * 1000.0, 3),
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

        deduped_records, identical_overlap_rows_dropped = _dedupe_identical_history_records(records)
        frame = normalize_frame(deduped_records)
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
            "bar_request_symbols": sorted(bar_requests),
            "bar_requests_explicit": bool(bar_requests),
            "symbols": symbol_receipts,
            "forward_bar_contract": ForwardBarContract().schema,
            "forward_bar_count": int(len(frame)),
            "forward_bar_symbols": sorted(frame["symbol"].unique().tolist()),
            "identical_history_overlap_rows_dropped": int(identical_overlap_rows_dropped),
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
            "quote_snapshot_requested": bool(args.include_quotes),
            "latency_ms": {
                "connect": connect_elapsed_ms,
                "account_state_and_open_orders": account_state_elapsed_ms,
                "historical_market_data_sum": round(market_data_elapsed_ms, 3),
                "pipeline_total": round((time.perf_counter() - pipeline_started) * 1000.0, 3),
            },
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
