from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

import requests

UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com"}
BASE = "https://www.census.gov/manufacturing/m3/historical_data/pressreleases/prel/{year}/{mon}{yy}prel.pdf"
MONTHS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
START_YEAR = 2012
END_YEAR = 2026
END_MONTH_INDEX = 7  # through July 2026 report month; Aug 2026 not yet safely complete at firing date
REQUEST_DELAY_SECONDS = 0.12
MIN_COVERAGE = 0.90


def extract_text(data: bytes) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext missing")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "release.pdf"
        p.write_bytes(data)
        cp = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True, text=True, timeout=90)
        if cp.returncode:
            raise RuntimeError(f"pdftotext rc={cp.returncode}: {cp.stderr[-600:]}")
        return cp.stdout


def parse_release_date(text: str) -> str | None:
    first = text.split("\f")[0]
    pats = [
        r"FOR RELEASE[^\n]*?([A-Z][A-Z]+\s+\d{1,2},\s+\d{4})",
        r"FOR RELEASE[^\n]*?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        r"([A-Z][A-Z]+\s+\d{1,2},\s+\d{4})",
        r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
    ]
    for pat in pats:
        m = re.search(pat, first)
        if not m:
            continue
        raw = m.group(1).strip().title()
        try:
            return datetime.strptime(raw, "%B %d, %Y").date().isoformat()
        except ValueError:
            continue
    return None


def normalize_minus(s: str) -> str:
    return s.replace("−", "-").replace("–", "-").replace("—", "-").replace("‐", "-")


def find_table_page(text: str, table_no: int, phrase: str) -> str:
    matches = []
    for page in text.split("\f"):
        low = page.lower()
        if f"table {table_no}" in low and phrase in low and "industrial machinery" in low:
            matches.append(page)
    if len(matches) != 1:
        raise RuntimeError(f"table {table_no} candidate_count={len(matches)}")
    return matches[0]


def industrial_line(page: str) -> str:
    lines = page.splitlines()
    hits = [line for line in lines if "industrial machinery" in line.lower()]
    if len(hits) != 1:
        raise RuntimeError(f"industrial machinery row count={len(hits)}")
    return re.sub(r"\s+", " ", hits[0]).strip()


def first_numeric_after_label(line: str) -> float:
    low = line.lower()
    p = low.find("industrial machinery")
    if p < 0:
        raise RuntimeError("industrial machinery label absent")
    tail = normalize_minus(line[p + len("industrial machinery"):])
    nums = re.findall(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?", tail)
    if not nums:
        raise RuntimeError(f"no numeric tokens after label: {line}")
    return float(nums[0].replace(",", ""))


def expected_report_months() -> list[tuple[int, int, str]]:
    out = []
    for year in range(START_YEAR, END_YEAR + 1):
        last = 12 if year < END_YEAR else END_MONTH_INDEX
        for mi in range(1, last + 1):
            out.append((year, mi, MONTHS[mi - 1]))
    return out


def main() -> None:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext missing")

    session = requests.Session()
    records = []
    failures = []
    expected = expected_report_months()

    for year, month_num, mon in expected:
        url = BASE.format(year=year, mon=mon, yy=str(year)[2:])
        report_month = f"{year:04d}-{month_num:02d}"
        try:
            r = session.get(url, headers=UA, timeout=(20, 90))
            if r.status_code != 200:
                failures.append({"report_month": report_month, "url": url, "status": r.status_code})
                time.sleep(REQUEST_DELAY_SECONDS)
                continue
            sha = hashlib.sha256(r.content).hexdigest()
            text = extract_text(r.content)
            release_date = parse_release_date(text)
            t1 = find_table_page(text, 1, "shipments")
            t3 = find_table_page(text, 3, "unfilled orders")
            row1 = industrial_line(t1)
            row3 = industrial_line(t3)
            shipments = first_numeric_after_label(row1)
            unfilled = first_numeric_after_label(row3)
            if shipments <= 0 or unfilled < 0:
                raise RuntimeError(f"invalid values shipments={shipments} unfilled={unfilled}")
            ratio = unfilled / shipments
            if not (0.1 <= ratio <= 20.0):
                raise RuntimeError(f"implausible backlog ratio={ratio}")
            if release_date is None:
                raise RuntimeError("release date not parsed")
            records.append({
                "report_month": report_month,
                "release_date": release_date,
                "shipments_sa_preliminary_musd": shipments,
                "unfilled_orders_sa_preliminary_musd": unfilled,
                "backlog_ratio": ratio,
                "source_url": url,
                "pdf_sha256": sha,
                "pdf_bytes": len(r.content),
                "table1_row": row1,
                "table3_row": row3,
            })
        except Exception as exc:
            failures.append({"report_month": report_month, "url": url, "exception": repr(exc)})
        time.sleep(REQUEST_DELAY_SECONDS)

    records.sort(key=lambda x: x["report_month"])
    coverage = len(records) / len(expected) if expected else 0.0
    duplicate_months = len(records) - len({r["report_month"] for r in records})
    release_before_report_end = []
    for rec in records:
        y, m = map(int, rec["report_month"].split("-"))
        rel = datetime.fromisoformat(rec["release_date"]).date()
        # Release must occur after its own report month. Comparing YYYY-MM is sufficient here.
        if (rel.year, rel.month) <= (y, m):
            release_before_report_end.append({"report_month": rec["report_month"], "release_date": rec["release_date"]})

    decision = "VINTAGE_MATERIALIZATION_READY" if coverage >= MIN_COVERAGE and duplicate_months == 0 and not release_before_report_end else "VINTAGE_MATERIALIZATION_NEEDS_REPAIR"
    out = {
        "schema": "research.p555_m3_vintage_materialize_r1",
        "parent": "P555",
        "decision": decision,
        "contract": {
            "industry": "Industrial machinery",
            "source": "original monthly Census M3 full-report PDFs",
            "shipments": "Table 1 first numeric field on Industrial machinery row = current report month SA preliminary value",
            "unfilled_orders": "Table 3 first numeric field on Industrial machinery row = current report month SA preliminary value",
            "backlog_ratio": "unfilled_orders_sa_preliminary / shipments_sa_preliminary",
            "no_revised_current_archive_values": True,
            "min_coverage": MIN_COVERAGE,
        },
        "expected_months": len(expected),
        "materialized_months": len(records),
        "coverage": coverage,
        "first_report_month": records[0]["report_month"] if records else None,
        "last_report_month": records[-1]["report_month"] if records else None,
        "duplicate_months": duplicate_months,
        "release_date_violations": release_before_report_end,
        "failures": failures,
        "records": records,
        "boundaries": {
            "scientific_alpha_claim": False,
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p555_m3_vintage_materialize_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in out.items() if k != "records"}, sort_keys=True))


if __name__ == "__main__":
    main()
