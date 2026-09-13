from __future__ import annotations

import json
from pathlib import Path

import requests

CASES = [
    ("202608a", "https://www.sec.gov/files/data/fails-deliver-data/cnsfails202608a.zip"),
    ("202608a_old_prefix", "https://www.sec.gov/files/data/other/fails-deliver-data/cnsfails202608a.zip"),
    ("202605b", "https://www.sec.gov/files/data/fails-deliver-data/cnsfails202605b.zip"),
    ("202605b_old_prefix", "https://www.sec.gov/files/data/other/fails-deliver-data/cnsfails202605b.zip"),
    ("202001a", "https://www.sec.gov/files/data/fails-deliver-data/cnsfails202001a.zip"),
    ("202001a_old_prefix", "https://www.sec.gov/files/data/other/fails-deliver-data/cnsfails202001a.zip"),
]

HEADERS = {
    "User-Agent": "XoticHazeResearch/1.0 152584286+XoticHaze@users.noreply.github.com",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Accept-Encoding": "gzip, deflate",
    "Range": "bytes=0-1023",
}


def probe(label: str, url: str) -> dict:
    try:
        with requests.get(url, headers=HEADERS, timeout=(10, 30), stream=True, allow_redirects=True) as r:
            first = b""
            try:
                first = next(r.iter_content(chunk_size=1024), b"")
            except Exception:
                pass
            return {
                "label": label,
                "url": url,
                "status": r.status_code,
                "content_type": r.headers.get("content-type"),
                "content_length": r.headers.get("content-length"),
                "content_range": r.headers.get("content-range"),
                "final_url": r.url,
                "first_bytes_hex": first[:16].hex(),
                "looks_like_zip": first.startswith(b"PK"),
            }
    except Exception as exc:
        return {
            "label": label,
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> None:
    rows = [probe(label, url) for label, url in CASES]
    out = {
        "schema": "research.sec_ftd_source_route_probe_r1",
        "purpose": "Resolve official SEC FTD archive reachability/path binding without changing any scientific hypothesis.",
        "rows": rows,
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/sec_ftd_source_route_probe_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
