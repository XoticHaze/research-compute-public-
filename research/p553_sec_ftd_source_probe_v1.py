from __future__ import annotations

import json
from pathlib import Path

import requests

INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"
ARCHIVE_URL = "https://www.sec.gov/files/data/fails-deliver-data/cnsfails202608a.zip"

PROFILES = {
    "current_workload": {
        "User-Agent": "XoticHaze market research contact XoticHaze@users.noreply.github.com",
    },
    "sec_declared_client": {
        "User-Agent": "XoticHaze/1.0 research contact 152584286+XoticHaze@users.noreply.github.com",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "*/*",
    },
    "browser_compatible": {
        "User-Agent": "Mozilla/5.0 XoticHazeResearch/1.0 contact 152584286+XoticHaze@users.noreply.github.com",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/zip,application/octet-stream;q=0.9,*/*;q=0.8",
    },
}


def probe(url: str, headers: dict[str, str]) -> dict[str, object]:
    try:
        r = requests.get(url, headers=headers, timeout=(10, 30), allow_redirects=True)
        return {
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("content-type"),
            "content_length_header": r.headers.get("content-length"),
            "body_bytes": len(r.content),
            "server": r.headers.get("server"),
            "retry_after": r.headers.get("retry-after"),
            "first_80_hex": r.content[:80].hex(),
        }
    except Exception as exc:
        return {"exception_type": type(exc).__name__, "exception": str(exc)[:500]}


def main() -> None:
    out = {
        "schema": "research.p553_sec_ftd_source_probe.v1",
        "purpose": "route-only diagnostic; no scientific evaluation",
        "targets": {"index": INDEX_URL, "archive": ARCHIVE_URL},
        "profiles": {},
    }
    for name, headers in PROFILES.items():
        out["profiles"][name] = {
            "index": probe(INDEX_URL, headers),
            "archive": probe(ARCHIVE_URL, headers),
        }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p553_sec_ftd_source_probe_v1.json").write_text(
        json.dumps(out, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
