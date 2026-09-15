from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from pypdf import PdfReader

INDEX_URL = "https://www.census.gov/manufacturing/m3/historical_data/index.html"
UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com", "Accept": "text/html,application/pdf,*/*"}
START_YEAR = 2014
END_YEAR = 2025

MONTHS = {m.lower(): i for i, m in enumerate(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}
CATEGORIES = {
    "Machinery": ["Machinery"],
    "Computer and Electronic Products": ["Computers and electronic products", "Computer and electronic products"],
    "Transportation Equipment": ["Transportation equipment"],
    "Electrical Equipment, Appliances, and Components": ["Electrical equipment, appliances, and components"],
}
MEASURES = {
    "Shipments": (1, ["Value of Manufacturers' Shipments", "Manufacturers' Shipments"]),
    "New Orders": (2, ["New Orders"]),
    "Unfilled Orders": (3, ["Unfilled Orders"]),
    "Inventories": (4, ["Inventories"]),
}


def norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", s).strip()


def release_date(text: str) -> str | None:
    m = re.search(
        r"FOR RELEASE AT\s+\d{1,2}:\d{2}\s+[AP]M\s+[A-Z]{2,5},\s+[A-Z]+,\s+([A-Z]+\s+\d{1,2},\s+\d{4})",
        text,
        flags=re.I,
    )
    if not m:
        m = re.search(
            r"FOR RELEASE AT[^\n]{0,140}?([A-Z]+\s+\d{1,2},\s+\d{4})",
            text,
            flags=re.I,
        )
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).title(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def observation_month(url: str) -> str | None:
    name = url.rsplit("/", 1)[-1].lower()
    m = re.match(r"([a-z]{3})(\d{2})prel\.pdf$", name)
    if not m or m.group(1) not in MONTHS:
        return None
    yy = int(m.group(2))
    year = 2000 + yy if yy < 80 else 1900 + yy
    return f"{year:04d}-{MONTHS[m.group(1)]:02d}"


def extract_links(html: str) -> list[str]:
    hrefs = re.findall(r'href=["\']([^"\']+prel\.pdf)["\']', html, flags=re.I)
    urls = []
    for href in hrefs:
        url = urljoin(INDEX_URL, href)
        om = observation_month(url)
        if not om:
            continue
        year = int(om[:4])
        if START_YEAR <= year <= END_YEAR:
            urls.append(url)
    return sorted(set(urls), key=lambda u: observation_month(u) or "")


def find_table_page(pages: list[str], table_no: int, headings: list[str]) -> int | None:
    # Prefer exact table-number evidence so narrative references to a measure cannot be mistaken for a table.
    candidates = []
    for i, text in enumerate(pages):
        low = text.lower()
        has_no = bool(re.search(rf"table\s*{table_no}\b", low))
        has_heading = any(h.lower() in low for h in headings)
        if has_no and has_heading:
            candidates.append(i)
    if len(candidates) == 1:
        return candidates[0]
    # Known full-report layout keeps Tables 1-4 consecutive; permit one unique heading page only when unambiguous.
    if not candidates:
        heading_pages = [i for i, text in enumerate(pages) if any(h.lower() in text.lower() for h in headings)]
        if len(heading_pages) == 1:
            return heading_pages[0]
    return None


def first_published_value(page_text: str, aliases: list[str]) -> float | None:
    text = norm(page_text)
    for alias in sorted(aliases, key=len, reverse=True):
        # Footnote numerals may immediately follow the category label. The first number after leader punctuation is current estimate.
        pat = re.compile(
            re.escape(alias) + r"(?:\d+)?[^0-9\-]{0,100}([0-9][0-9,]*(?:\.[0-9]+)?)",
            flags=re.I,
        )
        m = pat.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def fetch_pdf(session: requests.Session, url: str) -> bytes:
    r = session.get(url, headers=UA, timeout=(20, 90))
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise RuntimeError(f"not_pdf:{r.status_code}:{r.headers.get('content-type')}")
    return r.content


def main() -> None:
    outdir = Path("artifacts")
    outdir.mkdir(exist_ok=True)
    session = requests.Session()
    idx = session.get(INDEX_URL, headers=UA, timeout=(20, 60))
    idx.raise_for_status()
    links = extract_links(idx.text)
    rows: list[dict] = []
    releases: list[dict] = []

    for n, url in enumerate(links, 1):
        om = observation_month(url)
        rec = {"observation_month": om, "source_url": url, "status": None, "errors": []}
        try:
            raw = fetch_pdf(session, url)
            rec["source_sha256"] = hashlib.sha256(raw).hexdigest()
            rec["source_bytes"] = len(raw)
            reader = PdfReader(io.BytesIO(raw))
            pages = [norm(p.extract_text() or "") for p in reader.pages]
            text = "\n".join(pages)
            rd = release_date(text)
            rec["release_date"] = rd
            rec["page_count"] = len(pages)
            if not rd:
                rec["errors"].append("release_date_not_proven")

            table_pages = {}
            for measure, (table_no, headings) in MEASURES.items():
                pi = find_table_page(pages, table_no, headings)
                table_pages[measure] = pi
                if pi is None:
                    rec["errors"].append(f"table_page_not_proven:{measure}")
                    continue
                for category, aliases in CATEGORIES.items():
                    value = first_published_value(pages[pi], aliases)
                    if value is None:
                        rec["errors"].append(f"value_not_proven:{measure}:{category}")
                        continue
                    rows.append({
                        "release_date": rd,
                        "observation_month": om,
                        "category": category,
                        "measure": measure,
                        "published_value": value,
                        "source_identity": rec["source_sha256"],
                        "source_url": url,
                        "table_number": table_no,
                        "pdf_page": pi + 1,
                    })
            rec["table_pages"] = {k: (v + 1 if v is not None else None) for k, v in table_pages.items()}
            expected = len(CATEGORIES) * len(MEASURES)
            release_rows = [x for x in rows if x["source_url"] == url]
            if not rec["errors"] and len(release_rows) == expected:
                rec["status"] = "COMPLETE_16_OF_16"
            else:
                rec["status"] = f"INCOMPLETE_{len(release_rows)}_OF_{expected}"
        except Exception as exc:
            rec["status"] = "FETCH_OR_PARSE_FAILED"
            rec["errors"].append(repr(exc))
        releases.append(rec)
        print(json.dumps({"progress": n, "total": len(links), "observation_month": om, "status": rec["status"]}, sort_keys=True))
        time.sleep(0.08)

    # Fail-closed: only fully proven releases enter the scientific manifest.
    complete_urls = {r["source_url"] for r in releases if r["status"] == "COMPLETE_16_OF_16"}
    admitted = [r for r in rows if r["source_url"] in complete_urls and r["release_date"]]
    admitted.sort(key=lambda x: (x["observation_month"], x["measure"], x["category"]))

    csv_path = outdir / "p554_census_m3_vintage_manifest_r1.csv"
    fields = ["release_date", "observation_month", "category", "measure", "published_value", "source_identity", "source_url", "table_number", "pdf_page"]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(admitted)

    complete = sum(r["status"] == "COMPLETE_16_OF_16" for r in releases)
    summary = {
        "schema": "research.p554_census_m3_vintage_manifest_summary.r1",
        "parent": "P554",
        "index_url": INDEX_URL,
        "horizon": {"start_year": START_YEAR, "end_year": END_YEAR},
        "release_links_discovered": len(links),
        "complete_releases": complete,
        "incomplete_or_failed_releases": len(releases) - complete,
        "admitted_rows": len(admitted),
        "required_rows_per_release": 16,
        "coverage_ratio": complete / len(releases) if releases else 0.0,
        "first_observation_month": min((r["observation_month"] for r in releases if r["status"] == "COMPLETE_16_OF_16"), default=None),
        "last_observation_month": max((r["observation_month"] for r in releases if r["status"] == "COMPLETE_16_OF_16"), default=None),
        "manifest_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "decision": "P554_VINTAGE_MANIFEST_READY" if complete >= 96 else "P554_VINTAGE_MANIFEST_COVERAGE_NOT_READY",
        "release_diagnostics": releases,
        "scientific_alpha_claim": False,
        "promotion_claim": False,
        "live_trading_change": False,
    }
    (outdir / "p554_census_m3_vintage_manifest_r1_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in summary.items() if k != "release_diagnostics"}, sort_keys=True))
    if summary["decision"] != "P554_VINTAGE_MANIFEST_READY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
