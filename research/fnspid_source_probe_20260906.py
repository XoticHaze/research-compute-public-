from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

import requests

URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/fcd1056328b3db04769d4530abe4158d086cffc1/Stock_news/nasdaq_exteral_data.csv"
EXPECTED_SHA256 = "1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da"
CHUNK = 2 * 1024 * 1024
OFFSET_RE = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")
TIME_RE = re.compile(r"[T ]\d{1,2}:\d{2}")


def timestamp_shape(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "empty"
    if len(value) == 10:
        try:
            datetime.fromisoformat(value)
            return "date_only"
        except ValueError:
            pass
    if TIME_RE.search(value):
        return "datetime_explicit_offset" if OFFSET_RE.search(value) else "datetime_no_offset"
    return "other"


def get_range(session: requests.Session, start: int, stop: int) -> tuple[requests.Response, bytes]:
    r = session.get(URL, headers={"Range": f"bytes={start}-{stop}", "User-Agent": "research-compute/1.0"}, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r, r.content


def complete_lines(blob: bytes, is_first: bool = False) -> list[str]:
    text = blob.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if not is_first and lines:
        lines = lines[1:]
    if lines and not text.endswith(("\n", "\r")):
        lines = lines[:-1]
    return lines


def main() -> None:
    s = requests.Session()
    head = s.head(URL, headers={"User-Agent": "research-compute/1.0"}, timeout=60, allow_redirects=True)
    head.raise_for_status()
    size = int(head.headers.get("content-length") or 23232979597)
    offsets = [0, size // 4, size // 2, (3 * size) // 4, max(0, size - CHUNK)]

    first_response, first_blob = get_range(s, 0, CHUNK - 1)
    first_lines = complete_lines(first_blob, is_first=True)
    if not first_lines:
        raise RuntimeError("first range produced no complete lines")
    header_line = first_lines[0]
    header = next(csv.reader([header_line]))
    lower = {name.lower(): name for name in header}
    symbol_field = next((lower[x] for x in ("stock", "ticker", "symbol") if x in lower), None)
    date_field = next((lower[x] for x in ("date", "datetime", "timestamp", "published_at", "published") if x in lower), None)

    chunks = []
    for i, offset in enumerate(offsets):
        response, blob = (first_response, first_blob) if offset == 0 else get_range(s, offset, min(size - 1, offset + CHUNK - 1))
        lines = complete_lines(blob, is_first=(offset == 0))
        data_lines = lines[1:] if offset == 0 else lines
        rows = []
        for line in data_lines[:1000]:
            try:
                values = next(csv.reader([line]))
            except Exception:
                continue
            if len(values) != len(header):
                continue
            row = dict(zip(header, values))
            rows.append(row)
            if len(rows) >= 5:
                break
        chunks.append({
            "offset": offset,
            "status": response.status_code,
            "content_range": response.headers.get("content-range"),
            "bytes_received": len(blob),
            "sample_symbols": [r.get(symbol_field) for r in rows] if symbol_field else [],
            "sample_dates": [r.get(date_field) for r in rows] if date_field else [],
            "timestamp_shapes": [timestamp_shape(r.get(date_field, "")) for r in rows] if date_field else [],
            "sample_rows": [{k: r.get(k) for k in header[: min(8, len(header))]} for r in rows[:2]],
        })

    payload = {
        "schema": "research.fnspid_source_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": URL,
        "source_commit": "fcd1056328b3db04769d4530abe4158d086cffc1",
        "expected_source_sha256": EXPECTED_SHA256,
        "head": {
            "status": head.status_code,
            "final_url": head.url,
            "content_length": size,
            "accept_ranges": head.headers.get("accept-ranges"),
            "etag": head.headers.get("etag"),
        },
        "header": header,
        "symbol_field": symbol_field,
        "date_field": date_field,
        "range_chunks": chunks,
        "research_only": True,
    }
    with open("fnspid-source-probe-20260906.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("FNSPID_SOURCE_PROBE=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
