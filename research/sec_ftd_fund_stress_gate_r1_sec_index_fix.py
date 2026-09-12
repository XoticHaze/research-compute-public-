from __future__ import annotations

import re
import time
from datetime import date, timedelta
from urllib.parse import urljoin

import requests

import sec_ftd_fund_stress_gate_r1 as base

INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 XoticHazeResearch/1.0 contact 152584286+XoticHaze@users.noreply.github.com",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/zip,application/octet-stream;q=0.9,*/*;q=0.8",
}


def discover_archives(session: requests.Session) -> list[tuple[str, date]]:
    r = session.get(INDEX_URL, timeout=(10, 45))
    r.raise_for_status()
    hrefs = re.findall(r'href=["\']([^"\']+cnsfails(\d{6})([ab])\.zip)["\']', r.text, flags=re.I)
    out = []
    seen = set()
    for href, yyyymm, half in hrefs:
        year = int(yyyymm[:4])
        month = int(yyyymm[4:])
        if year < base.START_YEAR or year > base.END_YEAR:
            continue
        if half.lower() == "a":
            period_end = date(year, month, 15)
        elif month == 12:
            period_end = date(year, 12, 31)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)
        if period_end + timedelta(days=base.DISCLOSURE_LAG_DAYS) > date.today():
            continue
        url = urljoin(INDEX_URL, href)
        if url not in seen:
            out.append((url, period_end))
            seen.add(url)
    return sorted(out, key=lambda x: x[1])


def fetch_ftd_dynamic() -> tuple[list[dict], dict]:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    archives = discover_archives(session)
    periods = []
    errors = []
    for url, period_end in archives:
        try:
            r = session.get(url, timeout=(10, 60))
            r.raise_for_status()
            totals = base.parse_ftd_zip(r.content)
            periods.append({
                "period_end": period_end.isoformat(),
                "available_date": (period_end + timedelta(days=base.DISCLOSURE_LAG_DAYS)).isoformat(),
                "url": url,
                "ftd_dollar": totals,
            })
            time.sleep(0.10)
        except Exception as exc:
            errors.append({"url": url, "error": f"{type(exc).__name__}: {str(exc)[:180]}"})
    return periods, {
        "index_url": INDEX_URL,
        "discovered": len(archives),
        "loaded": len(periods),
        "errors": errors,
        "fetch_repair": "canonical SEC index link discovery; scientific spec unchanged",
    }


if __name__ == "__main__":
    base.fetch_ftd = fetch_ftd_dynamic
    base.main()
