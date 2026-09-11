from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import requests
from pypdf import PdfReader

UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com"}
BASE = "https://www.census.gov/manufacturing/m3/historical_data/pressreleases/prel/{year}/{mon}{yy}prel.pdf"
SAMPLES = [
    (2012, "jan"),
    (2016, "jan"),
    (2020, "jan"),
    (2024, "jul"),
    (2026, "jan"),
]


def compact(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    rows = []
    for year, mon in SAMPLES:
        url = BASE.format(year=year, mon=mon, yy=str(year)[2:])
        item = {"year": year, "month": mon, "url": url}
        try:
            r = requests.get(url, headers=UA, timeout=(20, 90))
            item["status"] = r.status_code
            item["bytes"] = len(r.content)
            item["content_type"] = r.headers.get("content-type")
            item["sha256"] = hashlib.sha256(r.content).hexdigest()
            r.raise_for_status()
            reader = PdfReader(io.BytesIO(r.content))
            texts = [(p.extract_text() or "") for p in reader.pages]
            joined = "\n".join(texts)
            lower = joined.lower()
            needle = "industrial machinery"
            positions = [m.start() for m in re.finditer(needle, lower)]
            item["pages"] = len(texts)
            item["industrial_machinery_hits"] = len(positions)
            item["table3_present"] = "table 3" in lower and "unfilled orders" in lower
            item["table7_present"] = "table 7" in lower
            item["contexts"] = [compact(joined[max(0, p - 500): p + 900]) for p in positions[:6]]
        except Exception as exc:
            item["exception"] = repr(exc)
        rows.append(item)

    viable = sum(bool(x.get("industrial_machinery_hits")) and x.get("table3_present") for x in rows)
    out = {
        "schema": "research.p555_m3_vintage_viability_r0",
        "parent": "P555",
        "decision": "VINTAGE_PATH_VIABLE" if viable >= 4 else "VINTAGE_PATH_NOT_YET_VIABLE",
        "required_sample_passes": 4,
        "sample_passes": viable,
        "samples": rows,
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
    Path("artifacts/p555_m3_vintage_viability_r0.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
