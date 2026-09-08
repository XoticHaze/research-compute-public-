from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

import requests

URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/fcd1056328b3db04769d4530abe4158d086cffc1/Stock_news/nasdaq_exteral_data.csv"
EXPECTED_SHA256 = "1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da"
CHUNK = 4 * 1024 * 1024
OFFSET_RE = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")
TIME_RE = re.compile(r"[T ]\d{1,2}:\d{2}")
# True record starts are numeric source index followed by an ISO-like date. This
# lets an arbitrary byte range skip embedded Article newlines without pretending
# every physical line is a CSV record.
RECORD_START_RE = re.compile(rb"(?:^|\n)(?P<start>\d+),(?P<date>\d{4}-\d{2}-\d{2}[^,]*),")


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
    r = session.get(
        URL,
        headers={"Range": f"bytes={start}-{stop}", "User-Agent": "research-compute/1.0"},
        timeout=60,
        allow_redirects=True,
    )
    r.raise_for_status()
    return r, r.content


def parse_prefix(blob: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = blob.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    header = list(reader.fieldnames or [])
    rows: list[dict[str, str]] = []
    try:
        for row in reader:
            if None in row:
                continue
            rows.append(row)
            if len(rows) >= 5:
                break
    except csv.Error:
        pass
    return header, rows


def parse_arbitrary_range(blob: bytes, header: list[str]) -> tuple[int | None, list[dict[str, str]]]:
    matches = list(RECORD_START_RE.finditer(blob))
    if not matches:
        return None, []
    # Start at the first complete record boundary visible inside the byte range.
    start = matches[0].start("start")
    text = blob[start:].decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(",".join(header) + "\n" + text))
    rows: list[dict[str, str]] = []
    try:
        for row in reader:
            if None in row:
                continue
            rows.append(row)
            if len(rows) >= 5:
                break
    except csv.Error:
        pass
    return start, rows


def main() -> None:
    s = requests.Session()
    head = s.head(URL, headers={"User-Agent": "research-compute/1.0"}, timeout=60, allow_redirects=True)
    head.raise_for_status()
    size = int(head.headers.get("content-length") or 23232979597)
    offsets = [0, size // 4, size // 2, (3 * size) // 4, max(0, size - CHUNK)]

    first_response, first_blob = get_range(s, 0, CHUNK - 1)
    header, first_rows = parse_prefix(first_blob)
    if not header:
        raise RuntimeError("first range produced no CSV header")
    lower = {name.lower(): name for name in header}
    symbol_field = next((lower[x] for x in ("stock", "stock_symbol", "ticker", "symbol") if x in lower), None)
    date_field = next((lower[x] for x in ("date", "datetime", "timestamp", "published_at", "published") if x in lower), None)
    if not symbol_field or not date_field:
        raise RuntimeError(f"required symbol/date fields absent: header={header}")

    chunks = []
    for offset in offsets:
        response, blob = (first_response, first_blob) if offset == 0 else get_range(
            s, offset, min(size - 1, offset + CHUNK - 1)
        )
        if offset == 0:
            boundary = 0
            rows = first_rows
        else:
            boundary, rows = parse_arbitrary_range(blob, header)
        chunks.append({
            "offset": offset,
            "status": response.status_code,
            "content_range": response.headers.get("content-range"),
            "bytes_received": len(blob),
            "first_record_boundary_in_chunk": boundary,
            "sample_symbols": [r.get(symbol_field) for r in rows],
            "sample_dates": [r.get(date_field) for r in rows],
            "timestamp_shapes": [timestamp_shape(r.get(date_field, "")) for r in rows],
            "sample_rows": [
                {k: r.get(k) for k in [date_field, symbol_field, "Article_title", "Url", "Publisher"] if k in r}
                for r in rows[:2]
            ],
        })

    all_sample_symbols = [s for chunk in chunks for s in chunk["sample_symbols"] if s]
    payload = {
        "schema": "research.fnspid_source_probe.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": URL,
        "source_commit": "fcd1056328b3db04769d4530abe4158d086cffc1",
        "expected_source_sha256": EXPECTED_SHA256,
        "source_sha_status": "PINNED_FROM_UPSTREAM_METADATA_NOT_REHASHED_BY_PARTIAL_PROBE",
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
        "sample_symbol_order": all_sample_symbols,
        "range_access_usable": all(chunk["status"] == 206 for chunk in chunks),
        "research_only": True,
    }
    with open("fnspid-source-probe-20260906.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("FNSPID_SOURCE_PROBE=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
