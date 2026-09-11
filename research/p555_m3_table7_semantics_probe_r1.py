from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests

UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com"}
BASE = "https://www.census.gov/manufacturing/m3/historical_data/pressreleases/prel/{year}/{mon}{yy}prel.pdf"
SAMPLES = [(2012,"jan"),(2016,"jan"),(2020,"jan"),(2021,"dec"),(2024,"jul"),(2026,"jan")]


def extract(data: bytes) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext missing")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.pdf"
        p.write_bytes(data)
        cp = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True, text=True, timeout=90)
        if cp.returncode:
            raise RuntimeError(cp.stderr[-500:])
        return cp.stdout


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def find_release_date(text: str) -> str | None:
    first = text.split("\f")[0]
    patterns = [
        r"FOR RELEASE[^\n]*?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        r"(?:MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY),?\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
        r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, first, flags=re.I)
        if m:
            return m.group(1)
    return None


def inspect_table7(text: str) -> dict:
    pages = text.split("\f")
    candidates = []
    for idx, page in enumerate(pages, start=1):
        low = page.lower()
        if "table 7" in low and "unfilled orders" in low:
            lines = page.splitlines()
            inds = [i for i,l in enumerate(lines) if "industrial machinery" in l.lower()]
            candidates.append({
                "page": idx,
                "header_excerpt": [clean(x) for x in lines[:35] if clean(x)],
                "industrial_rows": [clean(" ".join(lines[max(0,i-1):min(len(lines),i+2)])) for i in inds],
            })
    return {"candidate_pages": candidates, "candidate_count": len(candidates)}


def main() -> None:
    rows = []
    for year, mon in SAMPLES:
        url = BASE.format(year=year, mon=mon, yy=str(year)[2:])
        item = {"year":year,"month":mon,"url":url}
        try:
            r = requests.get(url, headers=UA, timeout=(20,90))
            item.update({"status":r.status_code,"bytes":len(r.content),"sha256":hashlib.sha256(r.content).hexdigest()})
            r.raise_for_status()
            text = extract(r.content)
            item["release_date_text"] = find_release_date(text)
            item["table7"] = inspect_table7(text)
            item["usable"] = bool(item["table7"]["candidate_count"] == 1 and item["table7"]["candidate_pages"][0]["industrial_rows"])
        except Exception as exc:
            item["exception"] = repr(exc)
            item["usable"] = False
        rows.append(item)
    usable = sum(bool(r.get("usable")) for r in rows)
    out = {
        "schema":"research.p555_m3_table7_semantics_probe_r1",
        "parent":"P555",
        "decision":"TABLE7_SEMANTICS_STABLE" if usable == len(rows) else "TABLE7_SEMANTICS_NEEDS_REPAIR",
        "usable":usable,
        "sample_count":len(rows),
        "samples":rows,
        "boundaries":{"scientific_alpha_claim":False,"portfolio_ranking":False,"allocation_authority":False,"runtime":False,"broker":False,"live_trading":False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p555_m3_table7_semantics_probe_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))

if __name__ == "__main__":
    main()
