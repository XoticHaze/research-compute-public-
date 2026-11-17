#!/usr/bin/env python3
"""Validate an explicit, encrypted-only IBKR historical OHLCV read before broker auth.

No connection, new gateway, broker mutation, credentials, or account output.
The existing B1 post-auth reader is the sole history/contract implementation.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
import re
from typing import Any
from pathlib import Path
import sys
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.ibkr_post_auth_pipeline_v1 import parse_bar_requests, parse_contract_hints

SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,23}$")
MAX_SYMBOLS = 12


def validate(*, symbols: str, contracts_json: str, bar_requests_json: str,
             recipient_b64: str, recipient_key_id: str, profile: str) -> dict[str, Any]:
    names = [s.strip().upper() for s in str(symbols).split(",") if s.strip()]
    if not 1 <= len(names) <= MAX_SYMBOLS or len(set(names)) != len(names):
        raise ValueError("private_bars_unique_bounded_symbols_required")
    if any(not SYMBOL.fullmatch(name) for name in names):
        raise ValueError("private_bars_symbol_invalid")
    requested = set(names)
    hints = parse_contract_hints(contracts_json)
    windows = parse_bar_requests(bar_requests_json, names)
    if set(hints) != requested or set(windows) != requested:
        raise ValueError("private_bars_exact_contract_and_windows_required")
    for name in names:
        hint = hints[name]
        typ = str(hint.get("secType") or "").upper()
        if typ not in {"STK", "FUT", "OPT"}:
            raise ValueError("private_bars_security_type_rejected")
        conid = int(hint.get("conId") or 0)
        if typ == "STK":
            if conid <= 0 and not all(hint.get(k) for k in ("exchange", "currency")):
                raise ValueError("private_bars_stock_contract_underspecified")
        elif typ == "FUT":
            if not (hint.get("exchange") and hint.get("currency") and
                    hint.get("lastTradeDateOrContractMonth")):
                raise ValueError("private_bars_future_dated_contract_required")
        else:
            try:
                strike = float(hint.get("strike"))
            except (TypeError, ValueError):
                strike = 0
            if not (conid > 0 and hint.get("exchange") and hint.get("currency") and
                    hint.get("lastTradeDateOrContractMonth") and hint.get("multiplier") and
                    str(hint.get("right") or "").upper() in {"C", "P"} and
                    math.isfinite(strike) and strike > 0):
                raise ValueError("private_bars_option_full_identity_required")
        for request in windows[name]:
            alternate = request.get("history_contract")
            if isinstance(alternate, dict):
                alt_type = str(alternate.get("secType") or "").upper()
                if alt_type != typ:
                    raise ValueError("private_bars_history_contract_type_drift")
    if profile != "v2":
        raise ValueError("private_bars_encrypted_return_v2_required")
    try:
        raw = base64.b64decode(str(recipient_b64), validate=True)
    except Exception as exc:
        raise ValueError("private_bars_recipient_not_base64") from exc
    if len(raw) != 32 or recipient_key_id != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("private_bars_recipient_identity_invalid")
    return {"ok": True, "schema": "mmibkr.private_broker_bars_preflight.v1",
            "symbols": len(names), "requests": sum(map(len, windows.values())),
            "security_types": sorted({str(hints[name]["secType"]).upper() for name in names}),
            "requires_encrypted_private_return": True, "broker_mutation_authority": False,
            "plaintext_artifact_allowed": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("symbols", "contracts-json", "bar-requests-json", "recipient-b64", "recipient-key-id", "profile"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    receipt = validate(symbols=args.symbols, contracts_json=args.contracts_json,
                       bar_requests_json=args.bar_requests_json,
                       recipient_b64=args.recipient_b64,
                       recipient_key_id=args.recipient_key_id, profile=args.profile)
    print("IBKR_PRIVATE_BARS_VALIDATED=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
