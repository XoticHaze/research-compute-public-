from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import requests

URL = "https://www.census.gov/econ_getzippedfile/?programCode=M3"
UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com"}
TERMS = [
    "machinery",
    "computer",
    "electronic",
    "transportation",
    "electrical",
    "new orders",
    "unfilled orders",
    "shipments",
    "inventor",
]


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", errors="replace")


def main() -> None:
    r = requests.get(URL, headers=UA, timeout=(20, 90), allow_redirects=True)
    r.raise_for_status()
    raw = r.content
    diag = {
        "schema": "research.p554_census_m3_industry_shape_r1",
        "parent": "P554",
        "decision": "SOURCE_SHAPE_ONLY",
        "source": URL,
        "final_url": r.url,
        "http_status": r.status_code,
        "content_type": r.headers.get("content-type"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "members": [],
        "term_hits": {},
        "sample_lines": {},
        "boundaries": {
            "scientific_alpha_claim": False,
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        diag["members"] = z.namelist()
        for name in z.namelist():
            if name.endswith("/"):
                continue
            data = z.read(name)
            text = decode_bytes(data)
            lines = text.splitlines()
            if lines:
                diag["sample_lines"][name] = lines[:5]
            lower = text.lower()
            hits = {}
            for term in TERMS:
                if term in lower:
                    matching = [line[:500] for line in lines if term in line.lower()][:8]
                    hits[term] = matching
            if hits:
                diag["term_hits"][name] = hits
    Path("artifacts").mkdir(exist_ok=True)
    out = Path("artifacts/p554_census_m3_industry_shape_r1.json")
    out.write_text(json.dumps(diag, indent=2, sort_keys=True))
    print(json.dumps(diag, sort_keys=True))


if __name__ == "__main__":
    main()
