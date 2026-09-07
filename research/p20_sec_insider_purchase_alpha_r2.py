#!/usr/bin/env python3
"""Changed-mechanism launcher for the frozen P20 discriminator.

The first public execution was denied by SEC's company_tickers.json endpoint.
The scientific contract is unchanged. This launcher replaces only ticker->CIK
lookup with fixed SEC issuer identities for the already-frozen universe, then
executes the original P20 consumer unchanged.
"""
from __future__ import annotations

import sys

import p20_sec_insider_purchase_alpha as p20

FROZEN_SEC_CIK_BY_TICKER = {
    "NVDA": 1045810,
    "AMD": 2488,
    "AMAT": 6951,
    "AVGO": 1730168,
    "MU": 723125,
    "INTC": 50863,
    "QCOM": 804328,
    "TXN": 97476,
}


def _frozen_sec_ticker_map():
    if set(FROZEN_SEC_CIK_BY_TICKER) != set(p20.UNIVERSE):
        raise RuntimeError("frozen CIK map no longer matches frozen P20 universe")
    return dict(FROZEN_SEC_CIK_BY_TICKER)


p20.sec_ticker_map = _frozen_sec_ticker_map

if __name__ == "__main__":
    sys.exit(p20.main())
