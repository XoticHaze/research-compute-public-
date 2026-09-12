from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import requests
from pypdf import PdfReader

PDF_URL = "https://www.census.gov/manufacturing/m3/historical_data/pressreleases/prel/2024/jan24prel.pdf"
UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com"}
TARGETS = [
    "Machinery",
    "Computers and electronic products",
    "Electrical equipment, appliances",
    "Transportation equipment",
]
MEASURE_HEADINGS = [
    "Value of Manufacturers' Shipments",
    "New Orders",
    "Unfilled Orders",
    "Inventories",
]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("’", "'")).strip()


def main() -> None:
    r = requests.get(PDF_URL, headers=UA, timeout=(20, 90))
    r.raise_for_status()
    raw = r.content
    reader = PdfReader(io.BytesIO(raw))
    pages = [norm(p.extract_text() or "") for p in reader.pages]
    all_text = "\n".join(pages)

    release_match = re.search(
        r"FOR RELEASE AT\s+([0-9: ]+[AP]M\s+[A-Z]{2,4},\s+[A-Z]+,\s+[A-Z]+\s+\d{1,2},\s+\d{4})",
        all_text,
        flags=re.I,
    )
    if not release_match:
        # Alternate text extraction often drops comma punctuation but preserves the date.
        release_match = re.search(r"FOR RELEASE AT[^\n]{0,100}?(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{1,2},\s+\d{4}", all_text, flags=re.I)

    target_hits = {}
    for target in TARGETS:
        hits = []
        t = target.lower()
        for i, text in enumerate(pages):
            if t in text.lower():
                # Keep small exact snippets around every occurrence for parser design.
                low = text.lower()
                start = 0
                while True:
                    j = low.find(t, start)
                    if j < 0:
                        break
                    hits.append({"page": i + 1, "snippet": text[max(0, j - 120): j + 500]})
                    start = j + len(t)
        target_hits[target] = hits[:20]

    heading_hits = {}
    for heading in MEASURE_HEADINGS:
        heading_hits[heading] = [i + 1 for i, text in enumerate(pages) if heading.lower() in text.lower()]

    decision = "P554_VINTAGE_REPRESENTATION_PROVEN"
    missing_targets = [k for k, v in target_hits.items() if not v]
    missing_headings = [k for k, v in heading_hits.items() if not v]
    if missing_targets or missing_headings or not release_match:
        decision = "P554_VINTAGE_REPRESENTATION_INCOMPLETE"

    out = {
        "schema": "research.p554_census_m3_vintage_representation_probe.r1",
        "parent": "P554",
        "decision": decision,
        "source_url": PDF_URL,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "page_count": len(pages),
        "release_evidence": release_match.group(0) if release_match else None,
        "target_hits": target_hits,
        "measure_heading_pages": heading_hits,
        "missing_targets": missing_targets,
        "missing_headings": missing_headings,
        "scientific_alpha_claim": False,
        "promotion_claim": False,
        "live_trading_change": False,
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p554_census_m3_vintage_representation_probe_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))
    if decision != "P554_VINTAGE_REPRESENTATION_PROVEN":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
