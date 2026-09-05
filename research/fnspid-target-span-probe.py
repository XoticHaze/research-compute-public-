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
    "path": "Stock_news/nasdaq_exteral_data.csv",
    "size_bytes": 23232979597,
    "lfs_sha256": "1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da",
}
PINNED = Path("research/fnspid-pilot-locator.json")
SPEC = Path("research/fnspid-targeted-slice.json")
CACHE = Path(".cache/fnspid-range")
CHUNK = 1024 * 1024
MAX_ITERS = 18
ROW_START = re.compile(rb"(?m)^(\d+),((?:19|20)\d{2}-\d{2}-\d{2} [^,\r\n]*),")
DATE_RE = re.compile(r"^(?:19|20)\d{2}-\d{2}-\d{2}")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


def url():
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
        req = urllib.request.Request(url(), headers={"User-Agent": "research-compute-public/1", "Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"})
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
        if len(row) != 12:
            continue
        date = row[1].strip()
        sym = row[3].strip().upper()
        if DATE_RE.match(date) and SYMBOL_RE.match(sym):
            out.append((sym, date[:10]))
    if out:
        return out
    # Fallback for arbitrary offsets inside quoted article bodies.
    lines = text.splitlines()[1:-1]
    try:
        for row in csv.reader(io.StringIO("\n".join(lines))):
            if len(row) != 12:
                continue
            date = row[1].strip()
            sym = row[3].strip().upper()
            if DATE_RE.match(date) and SYMBOL_RE.match(sym):
                out.append((sym, date[:10]))
    except csv.Error:
        pass
    return out


def sample(pos: int, target: str | None = None):
    cache_hits = network_reads = 0
    tried = []
    for shift in (0, -CHUNK // 2, CHUNK // 2, -CHUNK, CHUNK):
        at = max(0, min(pos + shift, SOURCE["size_bytes"] - CHUNK))
        data, hit = fetch_range(at)
        cache_hits += int(hit); network_reads += int(not hit)
        rows = valid_rows(data)
        if rows:
            syms = [x[0] for x in rows]
            tdates = [x[1] for x in rows if target and x[0] == target]
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
                "cache_hits": cache_hits,
                "network_reads": network_reads,
            }
        tried.append(at)
    raise RuntimeError(f"no structurally valid rows around {pos}; tried={tried}")


def symbol_boundary(target: str, upper: bool):
    lo, hi = 0, SOURCE["size_bytes"] - CHUNK
    trace = []
    hits = reads = 0
    for _ in range(MAX_ITERS):
        if hi - lo <= CHUNK:
            break
        mid = (lo + hi) // 2
        s = sample(mid, target)
        hits += s["cache_hits"]; reads += s["network_reads"]
        trace.append(s)
        med = s["median_symbol"]
        go_right = med <= target if upper else med < target
        if go_right:
            lo = mid + 1
        else:
            hi = mid
    return max(0, lo - 2 * CHUNK), min(SOURCE["size_bytes"], hi + 3 * CHUNK), trace, hits, reads


def target_date_sample(pos: int, target: str):
    # Search a bounded neighborhood because a 1MB sample may straddle a huge quoted row.
    for delta in (0, -CHUNK, CHUNK, -2*CHUNK, 2*CHUNK):
        s = sample(pos + delta, target)
        if s["target_rows"]:
            return s
    return None


def date_cutoff(target: str, block_lo: int, block_hi: int, start_date: str):
    points = []
    hits = reads = 0
    for frac in (0.05, 0.25, 0.5, 0.75, 0.95):
        pos = int(block_lo + (block_hi - block_lo) * frac)
        s = target_date_sample(pos, target)
        if s:
            hits += s["cache_hits"]; reads += s["network_reads"]
            points.append(s)
    dated = [x for x in points if x["target_median_date"]]
    dates = [x["target_median_date"] for x in dated]
    monotone_desc = len(dates) >= 3 and all(a >= b for a, b in zip(dates, dates[1:]))
    if not monotone_desc:
        return block_hi, points, False, hits, reads

    lo, hi = block_lo, block_hi
    trace = []
    for _ in range(MAX_ITERS):
        if hi - lo <= CHUNK:
            break
        mid = (lo + hi) // 2
        s = target_date_sample(mid, target)
        if not s or not s["target_median_date"]:
            # Remain conservative rather than skipping unknown source bytes.
            hi = min(block_hi, mid + 2 * CHUNK)
            continue
        hits += s["cache_hits"]; reads += s["network_reads"]
        trace.append(s)
        if s["target_median_date"] >= start_date:
            lo = mid + 1
        else:
            hi = mid
    return min(block_hi, hi + 4 * CHUNK), points + trace, True, hits, reads


def main():
    pinned = json.loads(PINNED.read_text())
    spec = json.loads(SPEC.read_text())
    if pinned["source"]["lfs_sha256"] != SOURCE["lfs_sha256"] or spec["source"]["lfs_sha256"] != SOURCE["lfs_sha256"]:
        raise SystemExit("source identity mismatch")
    results = []
    total_hits = total_reads = 0
    for target in spec["symbols"]:
        lower_lo, lower_hi, lower_trace, h1, n1 = symbol_boundary(target, upper=False)
        upper_lo, upper_hi, upper_trace, h2, n2 = symbol_boundary(target, upper=True)
        block_lo = lower_lo
        block_hi = upper_hi
        cutoff, date_trace, monotone, h3, n3 = date_cutoff(target, block_lo, block_hi, spec["start_date"])
        total_hits += h1+h2+h3; total_reads += n1+n2+n3
        results.append({
            "target": target,
            "symbol_block_start_approx": block_lo,
            "symbol_block_end_approx": block_hi,
            "symbol_block_bytes_approx": block_hi - block_lo,
            "materialize_start": block_lo,
            "materialize_end": cutoff,
            "materialize_bytes_approx": cutoff - block_lo,
            "date_order_monotone_desc": monotone,
            "symbol_lower_trace": lower_trace,
            "symbol_upper_trace": upper_trace,
            "date_trace": date_trace,
        })
    out = {
        "schema": "research_compute_public.fnspid_target_span_probe.v1",
        "source": SOURCE,
        "slice_spec_sha256": __import__("hashlib").sha256(SPEC.read_bytes()).hexdigest(),
        "start_date": spec["start_date"],
        "end_date": spec["end_date"],
        "results": results,
        "cache_hits": total_hits,
        "network_reads": total_reads,
        "research_only": True,
        "promotion_authority": False,
    }
    Path("fnspid-target-span-receipt.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("FNSPID_TARGET_SPAN=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
