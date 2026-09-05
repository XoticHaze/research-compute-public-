#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = {
    "dataset": "Zihan1004/FNSPID",
    "path": "Stock_news/All_external.csv",
    "size_bytes": 5731397037,
    "lfs_sha256": "5d4c018036bd82ca821da71b7a9c0c7db3289642e0fc6f897ea69f4a0c5135c3",
}
TARGET = "NVDA"
REQUEST_START = "2015-01-01"
REQUEST_END = "2021-08-16"
CACHE = Path(".cache/fnspid-range")
CHUNK = 1024 * 1024
MAX_ITERS = 16
# All_external has no leading Unnamed index. Each physical record begins with Date.
ROW_START = re.compile(rb'(?m)^"?((?:19|20)\d{2}-\d{2}-\d{2}[^,\r\n]*)"?,')
DATE_RE = re.compile(r"^(?:19|20)\d{2}-\d{2}-\d{2}")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


def url() -> str:
    return "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/" + SOURCE["path"]


def fetch_range(start: int):
    start = max(0, min(start, SOURCE["size_bytes"] - CHUNK))
    end = min(SOURCE["size_bytes"] - 1, start + CHUNK - 1)
    p = CACHE / SOURCE["lfs_sha256"] / f"{start}-{end}.bin"
    if p.exists():
        return p.read_bytes(), True
    p.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(5):
        req = urllib.request.Request(
            url(),
            headers={"User-Agent": "research-compute-public/1", "Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if getattr(r, "status", None) != 206 or not r.headers.get("Content-Range"):
                    raise RuntimeError(f"range not honored: status={getattr(r, 'status', None)} content-range={r.headers.get('Content-Range')}")
                data = r.read(CHUNK + 1)
            if len(data) > CHUNK:
                raise RuntimeError("bounded range exceeded")
            p.write_bytes(data)
            return data, False
        except (urllib.error.URLError, ConnectionResetError, TimeoutError, RuntimeError) as exc:
            last = exc
            time.sleep(min(8, 2 ** attempt))
    raise RuntimeError(f"range fetch failed after retries at {start}: {last}")


def valid_rows(data: bytes):
    text = data.decode("utf-8", errors="replace")
    out = []
    for m in ROW_START.finditer(data):
        pos = m.start()
        char_pos = len(data[:pos].decode("utf-8", errors="replace"))
        try:
            row = next(csv.reader(io.StringIO(text[char_pos:])))
        except (csv.Error, StopIteration):
            continue
        if len(row) != 11:
            continue
        date = row[0].strip()
        sym = row[2].strip().upper()
        if DATE_RE.match(date) and SYMBOL_RE.match(sym):
            out.append((sym, date[:10]))
    if out:
        return out
    # Fallback for arbitrary offsets inside multiline quoted articles.
    lines = text.splitlines()[1:-1]
    try:
        for row in csv.reader(io.StringIO("\n".join(lines))):
            if len(row) != 11:
                continue
            date = row[0].strip()
            sym = row[2].strip().upper()
            if DATE_RE.match(date) and SYMBOL_RE.match(sym):
                out.append((sym, date[:10]))
    except csv.Error:
        pass
    return out


def sample(pos: int):
    hits = reads = 0
    tried = []
    for shift in (0, -CHUNK // 2, CHUNK // 2, -CHUNK, CHUNK):
        at = max(0, min(pos + shift, SOURCE["size_bytes"] - CHUNK))
        data, hit = fetch_range(at)
        hits += int(hit); reads += int(not hit)
        rows = valid_rows(data)
        if rows:
            syms = [x[0] for x in rows]
            tdates = [x[1] for x in rows if x[0] == TARGET]
            return {
                "offset": at,
                "first_symbol": syms[0],
                "median_symbol": syms[len(syms)//2],
                "last_symbol": syms[-1],
                "rows": len(rows),
                "target_rows": len(tdates),
                "target_min_date": min(tdates) if tdates else None,
                "target_median_date": sorted(tdates)[len(tdates)//2] if tdates else None,
                "target_max_date": max(tdates) if tdates else None,
                "cache_hit": hit,
                "cache_hits": hits,
                "network_reads": reads,
            }
        tried.append(at)
    raise RuntimeError(f"no structurally valid rows around {pos}; tried={tried}")


def symbol_boundary(upper: bool):
    lo, hi = 0, SOURCE["size_bytes"] - CHUNK
    trace = []
    hits = reads = 0
    for _ in range(MAX_ITERS):
        if hi - lo <= CHUNK:
            break
        mid = (lo + hi) // 2
        s = sample(mid)
        hits += s["cache_hits"]; reads += s["network_reads"]
        trace.append(s)
        med = s["median_symbol"]
        go_right = med <= TARGET if upper else med < TARGET
        if go_right:
            lo = mid + 1
        else:
            hi = mid
    return max(0, lo - 2 * CHUNK), min(SOURCE["size_bytes"], hi + 3 * CHUNK), trace, hits, reads


def target_sample(pos: int):
    for delta in (0, -CHUNK, CHUNK, -2*CHUNK, 2*CHUNK):
        s = sample(pos + delta)
        if s["target_rows"]:
            return s
    return None


def date_window(block_lo: int, block_hi: int):
    hits = reads = 0
    probes = []
    for frac in (0.05, 0.25, 0.5, 0.75, 0.95):
        s = target_sample(int(block_lo + (block_hi - block_lo) * frac))
        if s:
            hits += s["cache_hits"]; reads += s["network_reads"]; probes.append(s)
    dates = [x["target_median_date"] for x in probes if x["target_median_date"]]
    descending = len(dates) >= 3 and all(a >= b for a, b in zip(dates, dates[1:]))
    if not descending:
        return block_lo, block_hi, probes, False, hits, reads

    def locate_cutoff(cutoff: str, newer_side: bool):
        nonlocal hits, reads
        lo, hi = block_lo, block_hi
        trace = []
        for _ in range(MAX_ITERS):
            if hi - lo <= CHUNK:
                break
            mid = (lo + hi) // 2
            s = target_sample(mid)
            if not s or not s["target_median_date"]:
                hi = min(block_hi, mid + 2 * CHUNK)
                continue
            hits += s["cache_hits"]; reads += s["network_reads"]; trace.append(s)
            d = s["target_median_date"]
            # Dates decrease as byte offset increases.
            if d > cutoff:
                lo = mid + 1
            else:
                hi = mid
        return max(block_lo, lo - 3*CHUNK), min(block_hi, hi + 3*CHUNK), trace

    # Start of requested missing window is the newer cutoff (2021-08-16), end is older 2015 cutoff.
    newer_lo, newer_hi, t1 = locate_cutoff(REQUEST_END, True)
    older_lo, older_hi, t2 = locate_cutoff(REQUEST_START, False)
    materialize_start = newer_lo
    materialize_end = older_hi
    return materialize_start, materialize_end, probes + t1 + t2, True, hits, reads


def main():
    lower_lo, _, lower_trace, h1, n1 = symbol_boundary(False)
    _, upper_hi, upper_trace, h2, n2 = symbol_boundary(True)
    mat_start, mat_end, date_trace, monotone, h3, n3 = date_window(lower_lo, upper_hi)
    observed_dates = [x["target_median_date"] for x in date_trace if x.get("target_median_date")]
    out = {
        "schema": "research_compute_public.fnspid_all_external_nvda_gap_probe.v1",
        "source": SOURCE,
        "target": TARGET,
        "requested_missing_window": {"start_date": REQUEST_START, "end_date": REQUEST_END},
        "symbol_block_start_approx": lower_lo,
        "symbol_block_end_approx": upper_hi,
        "symbol_block_bytes_approx": upper_hi - lower_lo,
        "date_order_monotone_desc": monotone,
        "materialize_start_approx": mat_start,
        "materialize_end_approx": mat_end,
        "materialize_bytes_approx": max(0, mat_end - mat_start),
        "observed_date_min": min(observed_dates) if observed_dates else None,
        "observed_date_max": max(observed_dates) if observed_dates else None,
        "covers_missing_window": bool(observed_dates and min(observed_dates) <= REQUEST_START and max(observed_dates) >= REQUEST_END),
        "cache_hits": h1+h2+h3,
        "network_reads": n1+n2+n3,
        "symbol_lower_trace": lower_trace,
        "symbol_upper_trace": upper_trace,
        "date_trace": date_trace,
        "research_only": true,
        "promotion_authority": false
    }
    Path("fnspid-all-external-nvda-span-receipt.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("FNSPID_ALL_EXTERNAL_NVDA_GAP=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
