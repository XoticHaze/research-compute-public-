from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE = "https://www.tsa.gov/travel/passenger-volumes"
UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com"}
MAX_PAGES = 60


def parse_page(html: bytes) -> list[tuple[pd.Timestamp, int]]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.select("table tbody tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        dt = pd.to_datetime(cells[0], errors="coerce")
        n = pd.to_numeric(re.sub(r"[^0-9]", "", cells[1]), errors="coerce")
        if pd.notna(dt) and pd.notna(n):
            out.append((pd.Timestamp(dt).normalize(), int(n)))
    return out


def main() -> None:
    s = requests.Session()
    all_rows = []
    pages = []
    seen_dates = set()
    for p in range(MAX_PAGES):
        url = f"{BASE}?page={p}"
        r = s.get(url, headers=UA, timeout=(15, 60))
        item = {
            "page": p,
            "url": url,
            "status": r.status_code,
            "bytes": len(r.content),
            "content_type": r.headers.get("content-type"),
            "last_modified": r.headers.get("last-modified"),
            "sha256": hashlib.sha256(r.content).hexdigest(),
        }
        if r.status_code != 200:
            pages.append(item)
            break
        rows = parse_page(r.content)
        item["rows"] = len(rows)
        item["first_date"] = None if not rows else str(max(d for d, _ in rows).date())
        item["last_date"] = None if not rows else str(min(d for d, _ in rows).date())
        pages.append(item)
        if not rows:
            break
        new = 0
        for d, n in rows:
            key = d.date().isoformat()
            if key not in seen_dates:
                seen_dates.add(key)
                all_rows.append((d, n))
                new += 1
        if new == 0:
            break
    df = pd.DataFrame(all_rows, columns=["date", "passengers"]).sort_values("date") if all_rows else pd.DataFrame(columns=["date","passengers"])
    duplicates = 0 if df.empty else int(df.date.duplicated().sum())
    gaps = []
    if not df.empty:
        full = pd.date_range(df.date.min(), df.date.max(), freq="D")
        present = set(df.date)
        gaps = [str(d.date()) for d in full if d not in present]
    out = {
        "schema": "research.p569_tsa_air_travel_source_r0",
        "parent": "P07",
        "child": "P569",
        "decision": "SOURCE_SHAPE_ONLY",
        "publisher": "Transportation Security Administration",
        "source": BASE,
        "pages": pages,
        "observations": int(len(df)),
        "first_date": None if df.empty else str(df.date.min().date()),
        "last_date": None if df.empty else str(df.date.max().date()),
        "duplicates": duplicates,
        "calendar_gap_count": len(gaps),
        "calendar_gap_samples": gaps[:30],
        "recent_rows": [] if df.empty else [
            {"date": str(r.date.date()), "passengers": int(r.passengers)}
            for r in df.tail(14).itertuples(index=False)
        ],
        "boundary": {
            "availability_assumption_not_yet_admitted": True,
            "alpha_claim": False,
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p569_tsa_air_travel_source_r0.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
