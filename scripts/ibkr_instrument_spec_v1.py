#!/usr/bin/env python3
"""Explicit instrument authority for the IBKR post-auth materializer.

Equities may use the normal SMART/USD defaults. Futures deliberately require an
explicit dated/local contract identity supplied by an upstream registry or
operator authority; this module never guesses a front month or creates a new
roll policy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    asset_type: str
    exchange: str
    currency: str = "USD"
    contract_month: str | None = None
    local_symbol: str | None = None

    def validate(self) -> "InstrumentSpec":
        symbol = self.symbol.strip().upper()
        asset_type = self.asset_type.strip().upper()
        exchange = self.exchange.strip().upper()
        currency = self.currency.strip().upper()
        if not symbol:
            raise ValueError("instrument symbol is required")
        if asset_type not in {"STK", "FUT"}:
            raise ValueError(f"unsupported asset_type {asset_type!r}")
        if not exchange:
            raise ValueError("instrument exchange is required")
        if not currency:
            raise ValueError("instrument currency is required")
        if asset_type == "FUT" and not (self.contract_month or self.local_symbol):
            raise ValueError(
                f"future {symbol} requires explicit contract_month or local_symbol; implicit front-month selection is forbidden"
            )
        return InstrumentSpec(
            symbol=symbol,
            asset_type=asset_type,
            exchange=exchange,
            currency=currency,
            contract_month=self.contract_month.strip() if self.contract_month else None,
            local_symbol=self.local_symbol.strip().upper() if self.local_symbol else None,
        )

    def build_contract(self) -> Any:
        from ib_insync import Future, Stock

        spec = self.validate()
        if spec.asset_type == "STK":
            return Stock(spec.symbol, spec.exchange, spec.currency)
        return Future(
            symbol=spec.symbol,
            lastTradeDateOrContractMonth=spec.contract_month or "",
            exchange=spec.exchange,
            currency=spec.currency,
            localSymbol=spec.local_symbol or "",
        )

    def receipt(self) -> dict[str, object]:
        spec = self.validate()
        return {
            "symbol": spec.symbol,
            "asset_type": spec.asset_type,
            "exchange": spec.exchange,
            "currency": spec.currency,
            "contract_month": spec.contract_month,
            "local_symbol": spec.local_symbol,
            "implicit_roll_selection": False,
        }


def stock_specs(symbols: list[str]) -> list[InstrumentSpec]:
    return [InstrumentSpec(symbol=s, asset_type="STK", exchange="SMART").validate() for s in symbols]


def parse_instrument_specs(value: str) -> list[InstrumentSpec]:
    """Parse a JSON array or @path reference into validated specs."""
    raw = value.strip()
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text()
    node = json.loads(raw)
    if not isinstance(node, list) or not node:
        raise ValueError("instrument spec must be a non-empty JSON array")
    specs: list[InstrumentSpec] = []
    for item in node:
        if not isinstance(item, dict):
            raise ValueError("each instrument spec must be an object")
        specs.append(
            InstrumentSpec(
                symbol=str(item.get("symbol", "")),
                asset_type=str(item.get("asset_type", "")),
                exchange=str(item.get("exchange", "")),
                currency=str(item.get("currency", "USD")),
                contract_month=(str(item["contract_month"]) if item.get("contract_month") else None),
                local_symbol=(str(item["local_symbol"]) if item.get("local_symbol") else None),
            ).validate()
        )
    identities = [(s.symbol, s.asset_type, s.contract_month, s.local_symbol) for s in specs]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate instrument identities are not allowed")
    return specs
