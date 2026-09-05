#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

BASE = Path(__file__).with_name("fnspid-all-external-nvda-span-probe.py")
spec = importlib.util.spec_from_file_location("fnspid_all_external_base", BASE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def bounded_sample(pos: int):
    hits = reads = 0
    tried = []
    # Always keep each network request at 1 MiB. Search farther only when a chunk
    # lands inside an unusually large multiline article record.
    shifts = [
        0,
        -mod.CHUNK // 2, mod.CHUNK // 2,
        -mod.CHUNK, mod.CHUNK,
        -2 * mod.CHUNK, 2 * mod.CHUNK,
        -4 * mod.CHUNK, 4 * mod.CHUNK,
        -8 * mod.CHUNK, 8 * mod.CHUNK,
        -16 * mod.CHUNK, 16 * mod.CHUNK,
    ]
    for shift in shifts:
        at = max(0, min(pos + shift, mod.SOURCE["size_bytes"] - mod.CHUNK))
        data, hit = mod.fetch_range(at)
        hits += int(hit)
        reads += int(not hit)
        rows = mod.valid_rows(data)
        if rows:
            syms = [x[0] for x in rows]
            tdates = [x[1] for x in rows if x[0] == mod.TARGET]
            return {
                "offset": at,
                "first_symbol": syms[0],
                "median_symbol": syms[len(syms) // 2],
                "last_symbol": syms[-1],
                "rows": len(rows),
                "target_rows": len(tdates),
                "target_min_date": min(tdates) if tdates else None,
                "target_median_date": sorted(tdates)[len(tdates) // 2] if tdates else None,
                "target_max_date": max(tdates) if tdates else None,
                "cache_hit": hit,
                "cache_hits": hits,
                "network_reads": reads,
                "boundary_search_radius_bytes": abs(shift),
            }
        tried.append(at)
    raise RuntimeError(f"no structurally valid rows in bounded ±16MiB search around {pos}; tried={tried}")


mod.sample = bounded_sample
mod.main()
