#!/usr/bin/env python3
"""Archive-index source binding for the already-frozen P20 discriminator.

Changes source mechanism only. Instead of data.sec.gov submissions JSON, enumerate
Form 4 filings from SEC quarterly master indexes, which carry causal filing dates
and accession-bound archive paths. Parse the complete submission text directly.
Scientific thresholds, universe, hold, costs, controls, and decision gates remain
owned by p20_sec_insider_purchase_alpha.py unchanged.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import urllib.parse

import p20_sec_insider_purchase_alpha as p20

FROZEN_SEC_CIK_BY_TICKER = {
    "NVDA": 1045810, "AMD": 2488, "AMAT": 6951, "AVGO": 1730168,
    "MU": 723125, "INTC": 50863, "QCOM": 804328, "TXN": 97476,
}


def _archive_master_rows():
    by_cik = {v: k for k, v in FROZEN_SEC_CIK_BY_TICKER.items()}
    start_year, end_year = p20.START_DATE.year, p20.END_DATE.year
    for year in range(start_year, end_year + 1):
        for qtr in range(1, 5):
            if year == end_year and qtr > ((p20.END_DATE.month - 1) // 3 + 1):
                continue
            url = f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{qtr}/master.gz"
            raw = p20.fetch_bytes(url, sec=True)
            text = gzip.decompress(raw).decode("latin-1", errors="replace")
            for line in text.splitlines():
                parts = line.split("|")
                if len(parts) != 5 or not parts[0].isdigit():
                    continue
                cik = int(parts[0])
                ticker = by_cik.get(cik)
                form = parts[2].strip()
                if ticker is None or form not in {"4", "4/A"}:
                    continue
                filed = dt.date.fromisoformat(parts[3].strip())
                if filed < p20.START_DATE or filed > p20.END_DATE:
                    continue
                filename = parts[4].strip()
                accession = filename.rsplit("/", 1)[-1].removesuffix(".txt")
                yield ticker, cik, accession, filed, filename


def collect_events_archive():
    events = []
    provenance = []
    seen = set()
    for ticker, cik, accession, filing_date, filename in _archive_master_rows():
        key = (cik, accession)
        if key in seen:
            continue
        seen.add(key)
        url = "https://www.sec.gov/Archives/" + urllib.parse.quote(filename, safe="/")
        try:
            doc = p20.fetch_bytes(url, sec=True)
        except Exception as exc:
            provenance.append({"ticker": ticker, "cik": cik, "accession": accession,
                               "filing_date": filing_date.isoformat(), "archive_path": filename,
                               "status": "fetch_failed", "error": str(exc)[:200]})
            continue
        sha = hashlib.sha256(doc).hexdigest()
        value, shares = p20.form4_purchase_totals(doc)
        provenance.append({"ticker": ticker, "cik": cik, "accession": accession,
                           "filing_date": filing_date.isoformat(), "archive_path": filename,
                           "document_sha256": sha, "purchase_value": value,
                           "purchase_shares": shares})
        if value >= p20.MIN_PURCHASE_USD:
            events.append(p20.FilingEvent(ticker, cik, accession, filing_date,
                                          filename, value, shares, sha))
    events.sort(key=lambda e: (e.filing_date, e.ticker, e.accession))
    return events, provenance


p20.collect_events = collect_events_archive

if __name__ == "__main__":
    raise SystemExit(p20.main())
