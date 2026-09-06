#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

SPEC_PATH = Path("research/fnspid-targeted-slice.json")
LOCATOR_PATH = Path("locator/fnspid-target-locator-receipt.json")
RANGE_CACHE = Path(".cache/fnspid-range")
SLICE_CACHE = Path(".cache/fnspid-slices")
CHUNK = 1024 * 1024
WINDOW = 4 * CHUNK
MAX_TARGET_BYTES = 384 * CHUNK
ROW_START = re.compile(rb"(?m)^(\d+),((?:19|20)\d{2}-\d{2}-\d{2} [^,\r\n]*),")
DATE_RE = re.compile(r"^(?:19|20)\d{2}-\d{2}-\d{2}")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


def load_inputs():
    spec = json.loads(SPEC_PATH.read_text())
    locator = json.loads(LOCATOR_PATH.read_text())
    source = spec["source"]
    if locator["source"]["lfs_sha256"] != source["lfs_sha256"]:
        raise SystemExit("locator/source LFS identity mismatch")
    if sorted(locator["targets"]) != sorted(spec["symbols"]):
        raise SystemExit("locator/spec target mismatch")
    if not locator.get("all_targets_found"):
        raise SystemExit("locator did not find every pilot target")
    return spec, locator


def source_url(source):
    return "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/" + source["path"]


def fetch_range(source, start: int, length: int = CHUNK):
    start = max(0, min(start, source["size_bytes"] - 1))
    end = min(source["size_bytes"] - 1, start + length - 1)
    p = RANGE_CACHE / source["lfs_sha256"] / f"{start}-{end}.bin"
    if p.exists():
        return p.read_bytes(), True
    p.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(5):
        req = urllib.request.Request(
            source_url(source),
            headers={"User-Agent": "research-compute-public/1", "Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if getattr(r, "status", None) != 206 or not r.headers.get("Content-Range"):
                    raise RuntimeError(f"range not honored: status={getattr(r, 'status', None)} content-range={r.headers.get('Content-Range')}")
                data = r.read(length + 1)
            if len(data) > length:
                raise RuntimeError("bounded range exceeded")
            p.write_bytes(data)
            return data, False
        except (urllib.error.URLError, ConnectionResetError, TimeoutError, RuntimeError) as exc:
            last = exc
            time.sleep(min(8, 2 ** attempt))
    raise RuntimeError(f"range fetch failed after retries start={start} end={end}: {last}")


def fetch_window(source, start: int, length: int):
    parts = []
    hits = reads = 0
    pos = start
    remain = length
    while remain > 0 and pos < source["size_bytes"]:
        n = min(CHUNK, remain)
        data, hit = fetch_range(source, pos, n)
        parts.append(data)
        hits += int(hit)
        reads += int(not hit)
        pos += len(data)
        remain -= len(data)
        if len(data) < n:
            break
    return b"".join(parts), hits, reads


def valid_row(row):
    if len(row) != 12:
        return None
    date = row[1].strip()
    sym = row[3].strip().upper()
    if not DATE_RE.match(date) or not SYMBOL_RE.match(sym):
        return None
    return sym, date


def parse_rows(data: bytes):
    text = data.decode("utf-8", errors="replace")
    out = []
    seen_starts = set()
    for m in ROW_START.finditer(data):
        pos = m.start()
        if pos in seen_starts:
            continue
        seen_starts.add(pos)
        char_pos = len(data[:pos].decode("utf-8", errors="replace"))
        try:
            row = next(csv.reader(io.StringIO(text[char_pos:])))
        except (csv.Error, StopIteration):
            continue
        v = valid_row(row)
        if v:
            out.append((pos, v[0], v[1], row))
    return out


def summarize_window(rows, target):
    syms = [x[1] for x in rows]
    target_rows = [x for x in rows if x[1] == target]
    dates = [x[2][:10] for x in target_rows]
    return {
        "rows": len(rows),
        "first_symbol": syms[0] if syms else None,
        "last_symbol": syms[-1] if syms else None,
        "target_rows": len(target_rows),
        "target_min_date": min(dates) if dates else None,
        "target_max_date": max(dates) if dates else None,
    }


def discover_span(source, locator_result, target, start_date):
    anchor = int(locator_result["window_start"])
    anchor -= anchor % WINDOW
    cache_hits = network_reads = 0
    trace = []

    # Walk left until the prior symbol block is observed.
    left = anchor
    cursor = anchor
    scanned = 0
    while cursor >= 0 and scanned <= MAX_TARGET_BYTES:
        data, h, n = fetch_window(source, cursor, WINDOW)
        cache_hits += h; network_reads += n
        rows = parse_rows(data)
        s = summarize_window(rows, target)
        trace.append({"direction": "left", "start": cursor, **s})
        if s["target_rows"] == 0 and rows and max(x[1] for x in rows) < target:
            left = cursor + WINDOW
            break
        if s["target_rows"]:
            left = cursor
        if cursor == 0:
            break
        cursor = max(0, cursor - WINDOW)
        scanned += WINDOW
    else:
        raise RuntimeError(f"left boundary exceeded cap for {target}")

    # Walk right until target history is older than requested start or next symbol appears.
    right = anchor + WINDOW
    cursor = anchor + WINDOW
    scanned = 0
    while cursor < source["size_bytes"] and scanned <= MAX_TARGET_BYTES:
        data, h, n = fetch_window(source, cursor, WINDOW)
        cache_hits += h; network_reads += n
        rows = parse_rows(data)
        s = summarize_window(rows, target)
        trace.append({"direction": "right", "start": cursor, **s})
        if s["target_rows"]:
            right = cursor + len(data)
            if s["target_max_date"] and s["target_max_date"] < start_date:
                break
        elif rows and min(x[1] for x in rows) > target:
            break
        cursor += WINDOW
        scanned += WINDOW
    else:
        raise RuntimeError(f"right boundary exceeded cap for {target}")

    return left, min(right, source["size_bytes"]), trace, cache_hits, network_reads


def materialize_target(source, target, left, right, start_date, end_date):
    total = right - left
    if total <= 0 or total > MAX_TARGET_BYTES:
        raise RuntimeError(f"invalid target span {target}: {total} bytes")
    data, hits, reads = fetch_window(source, left, total)
    rows = parse_rows(data)
    selected = []
    for _, sym, date, row in rows:
        day = date[:10]
        if sym == target and start_date <= day <= end_date:
            selected.append(row[1:])  # drop upstream Unnamed: 0 only
    return selected, hits, reads, hashlib.sha256(data).hexdigest(), total


def main():
    spec, locator = load_inputs()
    source = spec["source"]
    spec_sha = hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest()
    out_dir = SLICE_CACHE / source["lfs_sha256"] / spec_sha
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "fnspid-pilot-slice.csv"
    receipt_path = out_dir / "fnspid-pilot-slice-receipt.json"

    all_rows = []
    target_receipts = []
    total_hits = total_reads = 0
    locator_by_target = {x["target"]: x for x in locator["results"]}
    for target in spec["symbols"]:
        lr = locator_by_target[target]
        left, right, trace, hits, reads = discover_span(source, lr, target, spec["start_date"])
        rows, h2, n2, span_sha, span_bytes = materialize_target(source, target, left, right, spec["start_date"], spec["end_date"])
        total_hits += hits + h2
        total_reads += reads + n2
        all_rows.extend(rows)
        dates = [r[0][:10] for r in rows]
        target_receipts.append({
            "symbol": target,
            "rows": len(rows),
            "min_date": min(dates) if dates else None,
            "max_date": max(dates) if dates else None,
            "span_start": left,
            "span_end": right,
            "span_bytes": span_bytes,
            "span_sha256": span_sha,
            "discovery_trace": trace,
        })

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(spec["columns"])
        w.writerows(all_rows)

    symbol_counts = Counter(r[2].strip().upper() for r in all_rows)
    receipt = {
        "schema": "research_compute_public.fnspid_targeted_slice_receipt.v1",
        "source": source,
        "slice_spec_sha256": spec_sha,
        "symbols": spec["symbols"],
        "start_date": spec["start_date"],
        "end_date": spec["end_date"],
        "rows": len(all_rows),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "targets": target_receipts,
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "csv_bytes": csv_path.stat().st_size,
        "range_cache_hits": total_hits,
        "range_network_reads": total_reads,
        "raw_publication_timestamp_preserved": True,
        "timezone_imputation": False,
        "research_only": True,
        "promotion_authority": False,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("FNSPID_TARGETED_SLICE=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
