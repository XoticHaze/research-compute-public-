from __future__ import annotations
import hashlib, json, urllib.request
from pathlib import Path

SOURCES = {
    "SPY": "https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-spy.xlsx",
    "TLT": "https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appSubType=ISHARES&appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&portfolioId=239454&targetSite=us-ishares&userType=individual",
    "GLD": "https://api.spdrgoldshares.com/api/v1/historical-archive?exchange=NYSE&lang=en&product=gld",
}

def fetch(url: str):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 CC-Market-Research/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        b = r.read()
        return {
            "status": r.status,
            "content_type": r.headers.get("Content-Type"),
            "content_length": len(b),
            "sha256": hashlib.sha256(b).hexdigest(),
            "final_url": r.geturl(),
            "magic_hex": b[:16].hex(),
        }

def main():
    out = {"schema":"research.p46_authoritative_source_probe_r1","parent":"P46","purpose":"materialize and fingerprint authoritative issuer history endpoints without changing P46 model logic","sources":{},"unresolved":["QQQ","DBC"]}
    failures = []
    for ticker,url in SOURCES.items():
        try:
            out["sources"][ticker] = {"url":url, **fetch(url)}
        except Exception as e:
            out["sources"][ticker] = {"url":url,"error":repr(e)}
            failures.append(ticker)
    out["decision"] = "AUTHORITATIVE_SOURCE_PROBE_PASS" if not failures else "AUTHORITATIVE_SOURCE_PROBE_PARTIAL"
    out["failed"] = failures
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p46_authoritative_source_probe_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))
    if failures:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
