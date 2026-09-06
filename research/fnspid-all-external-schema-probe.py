#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
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
CHUNK = 1024 * 1024
HEAD_CHUNKS = 8
CACHE = Path('.cache/fnspid-range')
OUT = Path('fnspid-all-external-schema-receipt.json')


def url() -> str:
    return 'https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/' + SOURCE['path']


def fetch(start: int):
    end = min(SOURCE['size_bytes'] - 1, start + CHUNK - 1)
    p = CACHE / SOURCE['lfs_sha256'] / f'{start}-{end}.bin'
    if p.exists():
        return p.read_bytes(), True
    p.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(5):
        req = urllib.request.Request(url(), headers={
            'User-Agent': 'research-compute-public/1',
            'Range': f'bytes={start}-{end}',
            'Accept-Encoding': 'identity',
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if getattr(r, 'status', None) != 206 or not r.headers.get('Content-Range'):
                    raise RuntimeError(f'range not honored status={getattr(r, "status", None)}')
                data = r.read(CHUNK + 1)
            if len(data) > CHUNK:
                raise RuntimeError('bounded range exceeded')
            p.write_bytes(data)
            return data, False
        except (urllib.error.URLError, ConnectionResetError, TimeoutError, RuntimeError) as exc:
            last = exc
            time.sleep(min(8, 2 ** attempt))
    raise RuntimeError(f'head range fetch failed start={start}: {last}')


def main():
    parts=[]; hits=0; reads=0
    for i in range(HEAD_CHUNKS):
        data, hit = fetch(i * CHUNK)
        parts.append(data); hits += int(hit); reads += int(not hit)
    blob=b''.join(parts)
    text=blob.decode('utf-8', errors='replace')
    reader=csv.reader(io.StringIO(text))
    rows=[]
    parse_error=None
    try:
        for i,row in enumerate(reader):
            rows.append(row)
            if i >= 5000:
                break
    except csv.Error as exc:
        parse_error=str(exc)

    header=rows[0] if rows else []
    body=rows[1:] if len(rows)>1 else []
    lengths={}
    for row in body:
        lengths[str(len(row))]=lengths.get(str(len(row)),0)+1
    canonical=[r for r in body if len(r)==len(header)] if header else []

    lower=[str(x).strip().lower() for x in header]
    symbol_idx=next((i for i,x in enumerate(lower) if x in {'stock_symbol','stock symbol','symbol','ticker','stock'}),None)
    date_idx=next((i for i,x in enumerate(lower) if x in {'date','datetime','timestamp','time'}),None)
    examples=[]
    for r in canonical[:10]:
        examples.append({
            'date': r[date_idx] if date_idx is not None and date_idx < len(r) else None,
            'symbol': r[symbol_idx] if symbol_idx is not None and symbol_idx < len(r) else None,
            'field_count': len(r),
        })
    symbols=[r[symbol_idx].strip() for r in canonical[:2000] if symbol_idx is not None and symbol_idx < len(r)]
    dates=[r[date_idx].strip() for r in canonical[:2000] if date_idx is not None and date_idx < len(r)]
    out={
        'schema':'research_compute_public.fnspid_all_external_schema_probe.v1',
        'source':SOURCE,
        'bytes_read':len(blob),
        'cache_hits':hits,
        'network_reads':reads,
        'header':header,
        'header_field_count':len(header),
        'body_rows_parsed':len(body),
        'row_length_counts':lengths,
        'canonical_rows_in_head':len(canonical),
        'symbol_column_index':symbol_idx,
        'date_column_index':date_idx,
        'first_examples':examples,
        'first_2000_unique_symbols':len(set(symbols)),
        'first_2000_symbols_non_decreasing':all(a <= b for a,b in zip(symbols,symbols[1:])),
        'first_2000_dates_non_increasing':all(a >= b for a,b in zip(dates,dates[1:])),
        'csv_parse_error_after_bounded_head':parse_error,
        'research_only':True,
        'promotion_authority':False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True)+'\n')
    print('FNSPID_ALL_EXTERNAL_SCHEMA='+json.dumps(out, sort_keys=True))


if __name__=='__main__':
    main()
