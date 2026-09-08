from __future__ import annotations

import hashlib
import json

import opportunity_parallel_sec_fundamentals_20260907 as batch

# Fixed issuer identities for the frozen cohort. This removes only the blocked
# www.sec.gov ticker-discovery request. The research source remains the official
# SEC companyfacts API for each exact CIK below.
PINNED_CIKS = {
    "AMAT": 6951,
    "LRCX": 707549,
    "KLAC": 319201,
    "MU": 723125,
    "AMD": 2488,
    "QCOM": 804328,
    "DHI": 882184,
    "LEN": 920760,
    "PHM": 822416,
    "TOL": 794170,
    "NVR": 906163,
    "MHO": 799292,
}


def pinned_ticker_ciks() -> tuple[dict[str, int], str]:
    missing = sorted(set(batch.ALL_STOCKS) - set(PINNED_CIKS))
    if missing:
        raise RuntimeError(f"pinned CIK map missing frozen symbols: {missing}")
    canonical = json.dumps(PINNED_CIKS, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return dict(PINNED_CIKS), hashlib.sha256(canonical).hexdigest()


batch.ticker_ciks = pinned_ticker_ciks
batch.SEC_TICKERS_URL = "pinned-sec-issuer-cik-map:v1"

if __name__ == "__main__":
    batch.main()
