#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = {
    "path": "Stock_news/nasdaq_exteral_data.csv",
    "size": 23232979597,
    "lfs_sha256": "1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da",
}
DEFAULT_TARGETS = ["AMAT", "AMD", "AVGO", "DHI", "LEN", "MU", "NVR", "NVDA", "PHM", "TOL"]
CACHE = Path(".cache/fnspid-range")
CHUNK = 1024 * 1024
MAX_ITERS = 18
ROW_START = re.compile(rb"(?m)^(\d+),((?:19|20)\d{2}-\d{2}-\d{2} [^,\r\n]*),")
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")
DATE_RE = re.compile(r"^(?:19|20)\d{2}-\d{2}-\d{2}")


def configured_targets():
    raw = os.environ.get("FNSPID_TARGETS", "").strip()
    return [x.strip().upper() for x in raw.split(",") if x.strip()] if raw else DEFAULT_TARGETS


def url() -> str:
    return "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/" + SOURCE["path"]


def fetch_range(start: int, length: int = CHUNK):
    start = max(0, min(start, SOURCE["size"] - 1))
    end = min(SOURCE["size"] - 1, start + length - 1)
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
                data = r.read(length + 1)
            if len(data) > length:
                raise RuntimeError("bounded range exceeded")
            p.write_bytes(data)
            return data, False
        except (urllib.error.URLError, ConnectionResetError, TimeoutError, RuntimeError) as exc:
            last = exc
            time.sleep(min(8, 2 ** attempt))
    raise RuntimeError(f"range fetch failed after retries start={start} end={end}: {last}")


def fetch_window(start: int, length: int):
    parts = []
    hits = 0
    reads = 0
    offset = start
    remaining = length
    while remaining > 0:
        n = min(CHUNK, remaining)
        data, hit = fetch_range(offset, n)
        parts.append(data)
        hits += int(hit)
        reads += int(not hit)
        if not data:
            break
        offset += len(data)
        remaining -= len(data)
        if len(data) < n:
            break
    return b"".join(parts), hits, reads


def _valid(row):
    if len(row) != 12:
        return None
    date = row[1].strip()
    sym = row[3].strip().upper()
    if not DATE_RE.match(date) or not SYMBOL_RE.match(sym):
        return None
    return sym, date


def valid_pairs(data: bytes):
    text = data.decode("utf-8", errors="replace")
    out = []
    for m in ROW_START.finditer(data):
        pos = m.start()
        char_pos = len(data[:pos].decode("utf-8", errors="replace"))
        try:
            row = next(csv.reader(io.StringIO(text[char_pos:])))
        except (csv.Error, StopIteration):
            continue
        v = _valid(row)
        if v:
            out.append((pos, v[0], v[1]))
    if out:
        return out
    lines = text.splitlines()
    if lines:
        lines = lines[1:-1]
    try:
        rows = csv.reader(io.StringIO("\n".join(lines)))
        logical_offset = 0
        for row in rows:
            v = _valid(row)
            if v:
                out.append((logical_offset, v[0], v[1]))
            logical_offset += 1
    except csv.Error:
        pass
    return out


def sample(start: int):
    data, hit = fetch_range(start)
    pairs = valid_pairs(data)
    return {"start": start, "cache_hit": hit, "sha256": hashlib.sha256(data).hexdigest(), "pairs": pairs}


def locate(target: str):
    lo, hi = 0, max(0, SOURCE["size"] - CHUNK)
    trace = []
    network_reads = 0
    cache_reads = 0
    best = None
    for _ in range(MAX_ITERS):
        if hi <= lo or hi - lo <= CHUNK:
            break
        mid = (lo + hi) // 2
        s = sample(mid)
        cache_reads += int(s["cache_hit"])
        network_reads += int(not s["cache_hit"])
        pairs = s["pairs"]
        if not pairs:
            for shift in (-CHUNK // 2, CHUNK // 2, -CHUNK, CHUNK):
                s = sample(max(0, min(mid + shift, SOURCE["size"] - CHUNK)))
                cache_reads += int(s["cache_hit"])
                network_reads += int(not s["cache_hit"])
                pairs = s["pairs"]
                if pairs:
                    break
        if not pairs:
            return {"target": target, "found": False, "failure": f"no_structurally_valid_rows_near_{mid}", "trace": trace, "network_reads": network_reads, "cache_reads": cache_reads}
        syms = [p[1] for p in pairs]
        med = syms[len(syms)//2]
        trace.append({"offset": s["start"], "first": syms[0], "median": med, "last": syms[-1], "rows": len(syms), "cache_hit": s["cache_hit"]})
        exact = [p for p in pairs if p[1] == target]
        if exact:
            best = s["start"] + exact[len(exact)//2][0]
            break
        if med < target:
            lo = mid + 1
        else:
            hi = max(0, mid - 1)
    center = best if best is not None else (lo + hi) // 2
    window_start = max(0, center - 2 * CHUNK)
    data, window_hits, window_reads = fetch_window(window_start, 4 * CHUNK)
    cache_reads += window_hits
    network_reads += window_reads
    pairs = valid_pairs(data)
    exact = [(window_start + p, s, d) for p, s, d in pairs if s == target]
    neighbors = [(s, d) for _, s, d in pairs]
    return {
        "target": target,
        "found": bool(exact),
        "approx_center": center,
        "window_start": window_start,
        "window_bytes": len(data),
        "exact_rows_observed": len(exact),
        "first_exact_byte": exact[0][0] if exact else None,
        "last_exact_byte": exact[-1][0] if exact else None,
        "first_neighbor": neighbors[0] if neighbors else None,
        "last_neighbor": neighbors[-1] if neighbors else None,
        "trace": trace,
        "network_reads": network_reads,
        "cache_reads": cache_reads,
    }


def main():
    targets = configured_targets()
    results = []
    for target in targets:
        try:
            results.append(locate(target))
        except Exception as exc:
            results.append({"target": target, "found": False, "failure": f"{type(exc).__name__}:{exc}", "trace": [], "network_reads": 0, "cache_reads": 0})
    out = {
        "schema": "research_compute_public.fnspid_target_locator.v1",
        "dataset": "Zihan1004/FNSPID",
        "source": SOURCE,
        "targets": targets,
        "results": results,
        "all_targets_found": all(x.get("found") for x in results),
        "found_count": sum(bool(x.get("found")) for x in results),
        "network_reads": sum(x.get("network_reads", 0) for x in results),
        "cache_reads": sum(x.get("cache_reads", 0) for x in results),
        "cache_identity": "source_lfs_sha256+byte_range",
        "research_only": True,
        "promotion_authority": False,
    }
    Path("fnspid-target-locator-receipt.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("FNSPID_TARGET_LOCATOR=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
