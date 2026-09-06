from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import requests

URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/fcd1056328b3db04769d4530abe4158d086cffc1/Stock_news/nasdaq_exteral_data.csv"
SIZE = 23232979597
CHUNK = 64 * 1024 * 1024
OFFSETS = [128, 256, 384, 512, 768, 1024, 1280, 1536, 1792, 2048]
RECORD_START = re.compile(rb"(?:^|\n)(?P<idx>\d+),(?P<date>\d{4}-\d{2}-\d{2}[^,]*),")
SYMBOL_RE = re.compile(r"^[A-Z0-9.^=_-]{1,16}$")


def prefix_fields(blob: bytes, start: int, want: int = 4) -> list[str] | None:
    # Parse only the first fields of one CSV record. This honors quoted commas
    # and doubled quotes, but intentionally stops before the giant Article body.
    out: list[str] = []
    field = bytearray()
    quoted = False
    i = start
    limit = min(len(blob), start + 2 * 1024 * 1024)
    while i < limit:
        b = blob[i]
        if b == 34:  # quote
            if quoted and i + 1 < limit and blob[i + 1] == 34:
                field.append(34); i += 2; continue
            quoted = not quoted; i += 1; continue
        if b == 44 and not quoted:  # comma
            out.append(field.decode("utf-8", errors="replace"))
            field.clear(); i += 1
            if len(out) >= want:
                return out
            continue
        if b in (10, 13) and not quoted:
            return None
        field.append(b); i += 1
    return None


def sample(offset: int) -> dict:
    start = offset * 1024 * 1024
    stop = min(SIZE - 1, start + CHUNK - 1)
    r = requests.get(URL, headers={"Range": f"bytes={start}-{stop}", "User-Agent": "research-compute/1.0"}, timeout=120)
    r.raise_for_status()
    blob = r.content
    rows = []
    for m in RECORD_START.finditer(blob):
        p = m.start("idx")
        fields = prefix_fields(blob, p)
        if not fields or len(fields) < 4:
            continue
        idx, date, title, symbol = fields[:4]
        symbol = symbol.strip().upper()
        if idx != m.group("idx").decode() or not SYMBOL_RE.match(symbol):
            continue
        rows.append({"absolute_byte": start + p, "source_index": int(idx), "date": date, "symbol": symbol})
        if len(rows) >= 12:
            break
    return {
        "offset_mib": offset,
        "status": r.status_code,
        "content_range": r.headers.get("content-range"),
        "valid_record_starts": len(rows),
        "samples": rows,
    }


def main() -> None:
    chunks = [sample(x) for x in OFFSETS]
    all_rows = [r for c in chunks for r in c["samples"]]
    payload = {
        "schema": "research.fnspid_ticker_locator.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": "fcd1056328b3db04769d4530abe4158d086cffc1",
        "chunk_bytes": CHUNK,
        "chunks": chunks,
        "valid_samples": len(all_rows),
        "sample_symbols": [r["symbol"] for r in all_rows],
        "research_only": True,
    }
    with open("fnspid-ticker-locator-20260906.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True); fh.write("\n")
    print("FNSPID_TICKER_LOCATOR=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
