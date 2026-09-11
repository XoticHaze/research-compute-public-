from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests

PAGE = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"
TARGETS = [
    PAGE,
    "https://www.sec.gov/files/data/fails-deliver-data/cnsfails202608a.zip",
    "https://www.sec.gov/files/data/fails-deliver-data/cnsfails201801a.zip",
]
UA = {
    "User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com",
    "Accept": "application/zip,application/octet-stream,text/html,*/*",
    "Accept-Encoding": "gzip, deflate",
    "Referer": PAGE,
}


def main() -> None:
    session = requests.Session()
    rows = []
    for url in TARGETS:
        item = {"url": url}
        try:
            r = session.get(url, headers=UA, timeout=(15, 60), allow_redirects=True)
            item.update(
                {
                    "status": r.status_code,
                    "final_url": r.url,
                    "content_type": r.headers.get("content-type"),
                    "content_length_header": r.headers.get("content-length"),
                    "retry_after": r.headers.get("retry-after"),
                    "server": r.headers.get("server"),
                    "bytes": len(r.content),
                    "sha256": hashlib.sha256(r.content).hexdigest(),
                    "body_prefix_hex": r.content[:16].hex(),
                    "body_prefix_text": r.text[:160] if "text" in (r.headers.get("content-type") or "").lower() else None,
                }
            )
        except Exception as exc:
            item["exception"] = repr(exc)
        rows.append(item)
    out = {
        "schema": "research.p553_sec_ftd_transport_probe_r2",
        "parent": "P553",
        "decision": "TRANSPORT_DIAGNOSTIC_ONLY",
        "requests": rows,
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
    Path("artifacts/p553_sec_ftd_transport_probe_r2.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
