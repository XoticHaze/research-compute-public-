from __future__ import annotations

"""Collision-safe transport probe for SEC's official bulk XBRL archive.

This does not download the bulk archive, compute targets, or run a model. It reads at
most 4096 response bytes from each official SEC route to distinguish hosted-runner
transport policy from the already-blocked data.sec.gov Company Facts API route.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("sec_bulk_xbrl_transport_probe_20260906.json")
UA = "research-compute-public/1.0 (+https://github.com/XoticHaze/research-compute-public-)"
ROUTES = {
    "official_companyfacts_bulk": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip",
    "official_xbrl_archive_index": "https://www.sec.gov/Archives/edgar/daily-index/xbrl/",
}


def probe(name: str, url: str) -> dict:
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Range": "bytes=0-4095",
        },
    )
    try:
        with urlopen(req, timeout=45) as response:
            prefix = response.read(4096)
            headers = response.headers
            return {
                "name": name,
                "url": url,
                "ok": True,
                "status": int(response.status),
                "final_url": response.geturl(),
                "content_type": headers.get("Content-Type"),
                "content_length": headers.get("Content-Length"),
                "content_range": headers.get("Content-Range"),
                "accept_ranges": headers.get("Accept-Ranges"),
                "bytes_read": len(prefix),
                "prefix_hex": prefix[:16].hex(),
                "zip_magic": prefix.startswith(b"PK"),
            }
    except Exception as exc:
        code = getattr(exc, "code", None)
        body = b""
        try:
            body = exc.read(512)
        except Exception:
            pass
        return {
            "name": name,
            "url": url,
            "ok": False,
            "status": code,
            "error": repr(exc),
            "error_body_prefix": body.decode("utf-8", errors="replace"),
        }


def main() -> None:
    routes = {name: probe(name, url) for name, url in ROUTES.items()}
    bulk = routes["official_companyfacts_bulk"]
    status = "PASS" if bulk.get("ok") and bulk.get("zip_magic") else "BLOCKED_OR_INVALID"
    receipt = {
        "schema": "public_compute.sec_bulk_xbrl_transport_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "test official www.sec.gov bulk-XBRL transport independently of data.sec.gov",
        "routes": routes,
        "status": status,
        "bulk_download_performed": False,
        "max_response_bytes_read_per_route": 4096,
        "targets_computed": False,
        "model_executed": False,
        "external_holdout_loaded": False,
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
        "next_boundary": (
            "PASS authorizes a targeted extraction design from the official SEC companyfacts bulk ZIP; "
            "BLOCKED_OR_INVALID rejects this hosted-runner transport route without retry churn"
        ),
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SEC_BULK_XBRL_TRANSPORT_PROBE=" + json.dumps(receipt, sort_keys=True))
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
