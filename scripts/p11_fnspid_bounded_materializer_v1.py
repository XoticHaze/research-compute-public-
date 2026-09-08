#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DEFAULT_SYMBOLS=("NVDA","AMD","AMAT","AVGO","MU","DHI","LEN","PHM","TOL","NVR")
DATE_FIELDS=("date","datetime","timestamp","published_at","published","Date")
SYMBOL_FIELDS=("stock","ticker","symbol","Stock_symbol")
URL_FIELDS=("url","URL","Url")
OFFSET_RE=re.compile(r"(?:Z|UTC|[+-]\d{2}:?\d{2})$")
TIME_RE=re.compile(r"[T ]\d{1,2}:\d{2}")

# FNSPID carries full article bodies. The stdlib CSV default (128 KiB) is too low
# for valid rows, so raise only the parser field ceiling; the workload still streams
# one row at a time and never materializes the full 23.2 GB source in memory.
csv.field_size_limit(sys.maxsize)


def _open(source: str):
    req=urllib.request.Request(source, headers={"User-Agent":"research-compute-p11/1"})
    raw=urllib.request.urlopen(req, timeout=120)
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")


def _field(fields, choices):
    lower={x.lower():x for x in fields or []}
    for c in choices:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _date_prefix(value: str):
    value=(value or "").strip()
    if len(value)>=10:
        try:
            return datetime.fromisoformat(value[:10]).date().isoformat()
        except ValueError:
            return None
    return None


def _timestamp_shape(value: str)->str:
    value=(value or "").strip()
    if not value:
        return "empty"
    if len(value)==10 and _date_prefix(value):
        return "date_only"
    if TIME_RE.search(value):
        return "datetime_explicit_offset" if OFFSET_RE.search(value) else "datetime_no_offset"
    return "other"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2023-12-31")
    ap.add_argument("--source-sha256", required=True)
    ap.add_argument("--source-revision", required=True)
    args=ap.parse_args()
    symbols={x.strip().upper() for x in args.symbols.split(",") if x.strip()}
    counts=Counter(); years=defaultdict(Counter); min_ts={}; max_ts={}; seen_urls=set(); dup_urls=0
    shapes=Counter(); examples=defaultdict(list); selected_hash=hashlib.sha256()
    with _open(args.source) as fh:
        # Exact source identity is independently pinned by immutable HF revision +
        # published LFS SHA. Do not relabel a decoded-text digest as the source hash.
        reader=csv.DictReader(fh)
        if not reader.fieldnames:
            raise SystemExit("FNSPID input has no CSV header")
        sf=_field(reader.fieldnames,SYMBOL_FIELDS); df=_field(reader.fieldnames,DATE_FIELDS); uf=_field(reader.fieldnames,URL_FIELDS)
        if not sf or not df:
            raise SystemExit(f"required symbol/date fields absent: {reader.fieldnames}")
        for row in reader:
            sym=(row.get(sf) or "").strip().upper(); raw_ts=(row.get(df) or "").strip(); day=_date_prefix(raw_ts)
            if sym not in symbols or day is None or not(args.start<=day<=args.end):
                continue
            encoded=json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode("utf-8")
            selected_hash.update(encoded+b"\n")
            counts[sym]+=1; years[sym][day[:4]]+=1
            min_ts[sym]=min(min_ts.get(sym,raw_ts),raw_ts); max_ts[sym]=max(max_ts.get(sym,raw_ts),raw_ts)
            shape=_timestamp_shape(raw_ts); shapes[shape]+=1
            if len(examples[shape])<5 and raw_ts not in examples[shape]: examples[shape].append(raw_ts)
            if uf and row.get(uf):
                u=row[uf].strip()
                if u in seen_urls: dup_urls+=1
                seen_urls.add(u)
    total=sum(counts.values()); explicit=shapes["datetime_explicit_offset"]
    report={
      "schema":"p11.fnspid_bounded_source_receipt.v1",
      "authority":"research_only",
      "source_repo":"Zihan1004/FNSPID",
      "source_revision":args.source_revision,
      "source_path":"Stock_news/nasdaq_exteral_data.csv",
      "source_sha256_expected":args.source_sha256,
      "source_identity_verification":"IMMUTABLE_REVISION_PLUS_UPSTREAM_LFS_SHA_PIN",
      "requested_symbols":sorted(symbols),
      "requested_date_range":{"start":args.start,"end":args.end},
      "rows":total,
      "coverage":{s:{"rows":counts[s],"min_raw_publication":min_ts.get(s),"max_raw_publication":max_ts.get(s),"years":dict(sorted(years[s].items()))} for s in sorted(symbols)},
      "duplicate_url_rows":dup_urls,"unique_urls":len(seen_urls),
      "selected_row_content_sha256":selected_hash.hexdigest(),
      "publication_time_policy":"RAW_ONLY_NO_TIMEZONE_IMPUTATION",
      "timestamp_shape_counts":dict(sorted(shapes.items())),
      "timestamp_shape_examples":dict(sorted(examples.items())),
      "explicit_offset_row_fraction":(explicit/total if total else None),
      "timezone_verified":False,
      "causal_intraday_admission":"REQUIRES_SEPARATE_SOURCE_SEMANTICS_VERIFICATION",
      "next_gate":"DAILY_CAUSAL_ABLATION_ONLY_IF_PUBLICATION_SEMANTICS_SUPPORT_CAUSAL_DAILY_JOIN",
      "strategy_spec_write":False,"runtime_activation":False,"broker_submit":False,"promotion_authority":False,"live_trading_change":False
    }
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("P11_FNSPID_RECEIPT="+json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
