from __future__ import annotations

import gzip
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

SYMBOL_CIK = {"NVDA": 1045810, "AMAT": 6951, "DHI": 882184, "PHM": 822416}
SYMBOLS = list(SYMBOL_CIK)
START_DATE = "2024-01-01"
USER_AGENT = "XoticHaze Research 152584286+XoticHaze@users.noreply.github.com"


def request_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", "Accept": "application/json,text/xml,application/xml,text/html;q=0.9,*/*;q=0.8"})
    with urlopen(req, timeout=30) as resp:
        data = resp.read()
        return gzip.decompress(data) if resp.headers.get("Content-Encoding") == "gzip" else data


def get_json(url: str) -> dict:
    return json.loads(request_bytes(url).decode("utf-8"))


def get_text(url: str) -> str:
    return request_bytes(url).decode("utf-8", errors="replace")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_form4(text: str) -> dict:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        m = re.search(r"(<ownershipDocument[\s\S]*?</ownershipDocument>)", text, flags=re.I)
        if not m:
            return {"xml_parse": False, "transaction_codes": [], "issuer_symbol": None, "owner_names": []}
        root = ET.fromstring(m.group(1))
    codes = []
    issuer_symbol = None
    owners = []
    for elem in root.iter():
        name = local(elem.tag)
        value = (elem.text or "").strip()
        if name == "issuerTradingSymbol" and value:
            issuer_symbol = value
        elif name == "rptOwnerName" and value:
            owners.append(value)
        elif name == "transactionCode" and value:
            codes.append(value)
    return {"xml_parse": True, "transaction_codes": codes, "purchase_count": sum(c == "P" for c in codes), "sale_count": sum(c == "S" for c in codes), "issuer_symbol": issuer_symbol, "owner_names": sorted(set(owners))}


def recent_rows(submissions: dict) -> list[dict]:
    recent = submissions["filings"]["recent"]
    keys = ["accessionNumber", "filingDate", "acceptanceDateTime", "form", "primaryDocument"]
    rows = []
    for i in range(len(recent["accessionNumber"])):
        row = {k: recent[k][i] if k in recent and i < len(recent[k]) else None for k in keys}
        if row["form"] in {"4", "4/A"} and row["filingDate"] and row["filingDate"] >= START_DATE:
            rows.append(row)
    return rows


def main() -> None:
    results = {}
    admitted = True
    for symbol in SYMBOLS:
        cik = SYMBOL_CIK[symbol]
        try:
            sub = get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        except Exception as exc:
            results[symbol] = {"cik": cik, "source_ok": False, "submissions_error": f"{type(exc).__name__}: {exc}"}
            admitted = False
            continue
        rows = recent_rows(sub)
        samples = []
        for row in rows[:3]:
            accession = row["accessionNumber"]
            primary = row["primaryDocument"]
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{primary}"
            try:
                parsed = parse_form4(get_text(url))
                parsed.update({"accessionNumber": accession, "filingDate": row["filingDate"], "acceptanceDateTime": row["acceptanceDateTime"], "primaryDocument": primary, "url": url})
            except Exception as exc:
                parsed = {"accessionNumber": accession, "filingDate": row["filingDate"], "acceptanceDateTime": row["acceptanceDateTime"], "primaryDocument": primary, "url": url, "xml_parse": False, "error": f"{type(exc).__name__}: {exc}"}
            samples.append(parsed)
            time.sleep(0.2)
        acceptance_present = bool(rows) and all(r.get("acceptanceDateTime") for r in rows[: min(10, len(rows))])
        parsed_samples = [s for s in samples if s.get("xml_parse")]
        symbol_ok = bool(rows) and acceptance_present and bool(parsed_samples) and all((s.get("issuer_symbol") or "").upper() == symbol for s in parsed_samples)
        admitted = admitted and symbol_ok
        results[symbol] = {"cik": cik, "form4_rows_since_start": len(rows), "acceptance_datetime_present": acceptance_present, "parsed_sample_count": len(parsed_samples), "sample_transaction_codes": sorted({c for s in parsed_samples for c in s.get("transaction_codes", [])}), "samples": samples, "source_ok": symbol_ok}
    out = {
        "schema": "research.p280_sec_form4_source_probe_r1",
        "parent": "P280",
        "claim": "SEC Form 4 ownership filings provide a public, authentication-free, causally timestamped directional-insider-event source suitable for a separate alpha discriminator if source-shape admission passes.",
        "contract": {"symbols": SYMBOLS, "symbol_cik": SYMBOL_CIK, "start_date": START_DATE, "source": "SEC EDGAR company submissions plus exact filing primary documents", "causality_policy": "Economic consumers must make an event available no earlier than the first trading day strictly after filingDate; acceptanceDateTime is retained as provenance but is not needed to trade intraday.", "directional_codes": {"P": "open-market/private purchase", "S": "sale"}, "no_price_or_alpha_inference_in_source_probe": True},
        "tests": results,
        "decision": "P280_SEC_FORM4_SOURCE_ADMITTED" if admitted else "P280_SEC_FORM4_SOURCE_NOT_ADMITTED",
        "next_if_admitted": "Run one fixed price-state versus insider-only versus price+insider versus permuted-insider walk-forward residual-selection test across Semiconductor and Homebuilder components, with matched industry controls and turnover costs.",
        "limitations": ["Source admission is not alpha evidence", "Only a bounded representative symbol set is probed here", "Use conservative next-trading-day availability in economic tests"],
        "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p280_sec_form4_source_probe_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
