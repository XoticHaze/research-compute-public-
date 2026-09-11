from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import requests

URL = "https://www.census.gov/econ_getzippedfile/?programCode=M3"
UA = {"User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com"}
TARGET_CATEGORY_CODES = {"33S", "33E", "34S", "35S", "36S"}
TARGET_DATA_CODES = {"VS", "NO", "UO", "US", "TI", "IS", "MPCNO", "MPCUO"}


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1", errors="replace")


def sectionize(lines: list[str]) -> dict[str, list[list[str]]]:
    sections: dict[str, list[list[str]]] = {}
    current = "PREAMBLE"
    sections[current] = []
    for raw in lines:
        stripped = raw.strip()
        # The M3 flat file uses uppercase, single-field section banners such as
        # CATEGORIES / DATA TYPES / TIME SERIES. Capture them without assuming
        # the exact list in advance.
        if stripped and "," not in stripped and stripped == stripped.upper() and len(stripped) < 80:
            current = stripped
            sections.setdefault(current, [])
            continue
        if not stripped:
            continue
        try:
            row = next(csv.reader([raw]))
        except Exception:
            row = [raw]
        sections.setdefault(current, []).append(row)
    return sections


def main() -> None:
    r = requests.get(URL, headers=UA, timeout=(20, 90), allow_redirects=True)
    r.raise_for_status()
    raw = r.content
    diag = {
        "schema": "research.p554_census_m3_industry_shape_r2",
        "parent": "P554",
        "decision": "SOURCE_SHAPE_ONLY",
        "source": URL,
        "final_url": r.url,
        "http_status": r.status_code,
        "content_type": r.headers.get("content-type"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "members": [],
        "section_names": [],
        "section_samples": {},
        "target_category_rows": [],
        "target_data_type_rows": [],
        "target_time_series_rows": [],
        "time_series_row_lengths": {},
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
        text = decode_bytes(z.read("M3-mf.csv"))
        sections = sectionize(text.splitlines())
        diag["section_names"] = list(sections)
        for name, rows in sections.items():
            diag["section_samples"][name] = rows[:5]

        for name, rows in sections.items():
            upper_name = name.upper()
            for row in rows:
                vals = {str(v).strip() for v in row}
                if vals & TARGET_CATEGORY_CODES:
                    diag["target_category_rows"].append({"section": name, "row": row})
                if vals & TARGET_DATA_CODES:
                    diag["target_data_type_rows"].append({"section": name, "row": row})
                if (vals & TARGET_CATEGORY_CODES) and (vals & TARGET_DATA_CODES):
                    diag["target_time_series_rows"].append({"section": name, "row": row[:40]})
                if "TIME" in upper_name or "SERIES" in upper_name or "DATA" in upper_name:
                    key = f"{name}:{len(row)}"
                    diag["time_series_row_lengths"][key] = diag["time_series_row_lengths"].get(key, 0) + 1

        # Also capture any raw rows where target category and measure codes occur
        # together, irrespective of the banner parser. This makes the probe
        # robust to format changes without inspecting investment performance.
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            try:
                row = next(csv.reader([raw_line]))
            except Exception:
                continue
            vals = {str(v).strip() for v in row}
            if (vals & TARGET_CATEGORY_CODES) and (vals & TARGET_DATA_CODES):
                diag["target_time_series_rows"].append({"line": line_no, "row": row[:40]})

    # De-duplicate diagnostic rows while preserving order.
    seen = set()
    deduped = []
    for item in diag["target_time_series_rows"]:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    diag["target_time_series_rows"] = deduped[:100]

    Path("artifacts").mkdir(exist_ok=True)
    out = Path("artifacts/p554_census_m3_industry_shape_r1.json")
    out.write_text(json.dumps(diag, indent=2, sort_keys=True))
    print(json.dumps(diag, sort_keys=True))


if __name__ == "__main__":
    main()
