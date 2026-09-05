#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

SOURCES = [
    {
        "path": "Stock_news/All_external.csv",
        "size": 5731397037,
        "lfs_sha256": "5d4c018036bd82ca821da71b7a9c0c7db3289642e0fc6f897ea69f4a0c5135c3",
    },
    {
        "path": "Stock_news/nasdaq_exteral_data.csv",
        "size": 23232979597,
        "lfs_sha256": "1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da",
    },
]
TARGETS = {"NVDA","AMD","AMAT","AVGO","MU","DHI","LEN","PHM","TOL","NVR"}
CHUNK = 512 * 1024
CACHE = Path(".cache/fnspid-range")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def resolve_url(path: str) -> str:
    return "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/" + path


def fetch_range(source: dict, start: int, length: int) -> tuple[bytes, bool, str | None]:
    end = min(source["size"] - 1, start + length - 1)
    cache_file = CACHE / source["lfs_sha256"] / f"{start}-{end}.bin"
    if cache_file.exists():
        return cache_file.read_bytes(), True, None
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        resolve_url(source["path"]),
        headers={
            "User-Agent": "research-compute-public/1",
            "Range": f"bytes={start}-{end}",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        status = getattr(r, "status", None)
        content_range = r.headers.get("Content-Range")
        if status != 206 or not content_range:
            raise RuntimeError(f"range request not honored for {source['path']}: status={status} content-range={content_range}")
        data = r.read(length + 1)
    if len(data) > length:
        raise RuntimeError("range response exceeded requested bounded length")
    cache_file.write_bytes(data)
    return data, False, content_range


def header_and_indices(data: bytes):
    text = data.decode("utf-8", errors="replace")
    first = text.splitlines()[0]
    header = next(csv.reader([first]))
    lower = {x.strip().lower(): i for i, x in enumerate(header)}
    sym_i = next((lower[k] for k in ("stock", "ticker", "symbol") if k in lower), None)
    date_i = next((lower[k] for k in ("date", "datetime", "timestamp", "published_at", "published") if k in lower), None)
    return header, sym_i, date_i


def inspect_chunk(data: bytes, header_len: int | None, sym_i: int | None, date_i: int | None, is_start: bool):
    text = data.decode("utf-8", errors="replace")
    # Keep only complete physical lines; validate logical rows by exact field count.
    lines = text.splitlines()
    if not is_start and lines:
        lines = lines[1:]
    if lines:
        lines = lines[:-1]
    if is_start and lines:
        lines = lines[1:]
    valid = []
    field_counts = Counter()
    for row in csv.reader(io.StringIO("\n".join(lines))):
        field_counts[len(row)] += 1
        if header_len is not None and len(row) == header_len:
            valid.append(row)
    pairs = []
    if sym_i is not None and date_i is not None:
        for row in valid:
            sym = row[sym_i].strip().upper() if sym_i < len(row) else ""
            dt = row[date_i].strip() if date_i < len(row) else ""
            if sym and dt:
                pairs.append((sym, dt[:32]))
    target_counts = Counter(sym for sym, _ in pairs if sym in TARGETS)
    years = Counter()
    for _, dt in pairs:
        m = YEAR_RE.search(dt)
        if m:
            years[m.group(0)] += 1
    sample_pairs = pairs[:3] + (pairs[-3:] if len(pairs) > 3 else [])
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "newline_count": data.count(b"\n"),
        "field_count_histogram": dict(field_counts.most_common(8)),
        "validated_rows": len(valid),
        "symbol_date_samples": sample_pairs,
        "target_symbol_counts": dict(sorted(target_counts.items())),
        "year_counts": dict(sorted(years.items())),
    }


def main():
    receipt = {
        "schema": "research_compute_public.fnspid_range_layout_probe.v1",
        "dataset": "Zihan1004/FNSPID",
        "range_chunk_bytes": CHUNK,
        "cache_root": str(CACHE),
        "cache_identity": "source_lfs_sha256+byte_range",
        "sources": [],
        "research_only": True,
        "promotion_authority": False,
    }
    for source in SOURCES:
        positions = sorted(set([0, source["size"] // 4, source["size"] // 2, (3 * source["size"]) // 4, max(0, source["size"] - CHUNK)]))
        chunks = []
        header = None
        sym_i = date_i = None
        for pos in positions:
            data, hit, content_range = fetch_range(source, pos, CHUNK)
            if pos == 0:
                header, sym_i, date_i = header_and_indices(data)
            summary = inspect_chunk(data, len(header) if header else None, sym_i, date_i, pos == 0)
            summary.update({"start": pos, "cache_hit": hit, "content_range": content_range})
            chunks.append(summary)
        receipt["sources"].append({
            **source,
            "header": header,
            "symbol_column_index": sym_i,
            "date_column_index": date_i,
            "chunks": chunks,
        })
    Path("fnspid-range-layout-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("FNSPID_RANGE_LAYOUT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
