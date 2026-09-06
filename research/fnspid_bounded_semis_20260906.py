from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

import requests

URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/fcd1056328b3db04769d4530abe4158d086cffc1/Stock_news/nasdaq_exteral_data.csv"
EXPECTED_SHA256 = "1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da"
SOURCE_COMMIT = "fcd1056328b3db04769d4530abe4158d086cffc1"
UPSTREAM_PROCESSOR_COMMIT = "4054842ec476953b30ee874d4b7e8eea786a21fa"
TARGETS = ("AMAT", "AMD", "AVGO")
START = "2015-01-01"
END = "2023-12-31"
MAX_RANGE_BYTES = 2 * 1024 * 1024 * 1024
UTC_LITERAL_RE = re.compile(r"\sUTC$")
NUMERIC_OFFSET_RE = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")
TIME_RE = re.compile(r"[T ]\d{1,2}:\d{2}")


def shape(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "empty"
    if UTC_LITERAL_RE.search(value):
        return "datetime_utc_literal"
    if TIME_RE.search(value):
        return "datetime_explicit_numeric_offset" if NUMERIC_OFFSET_RE.search(value) else "datetime_no_offset"
    if len(value) >= 10:
        try:
            datetime.fromisoformat(value[:10])
            return "date_only"
        except ValueError:
            pass
    return "other"


def day(value: str) -> str | None:
    value = (value or "").strip()
    if len(value) < 10:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date().isoformat()
    except ValueError:
        return None


def main() -> None:
    headers = {
        "Range": f"bytes=0-{MAX_RANGE_BYTES - 1}",
        "User-Agent": "research-compute/1.0",
    }
    with requests.get(URL, headers=headers, stream=True, timeout=(30, 300), allow_redirects=True) as response:
        response.raise_for_status()
        wrapper = io.TextIOWrapper(response.raw, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(wrapper)
        required = {"Date", "Stock_symbol", "Url", "Publisher", "Article_title"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise RuntimeError(f"unexpected source schema: {reader.fieldnames}")

        counts = Counter()
        years = defaultdict(Counter)
        shapes = Counter()
        min_ts: dict[str, str] = {}
        max_ts: dict[str, str] = {}
        seen_urls: set[str] = set()
        duplicate_urls = 0
        last_symbol = ""
        monotonic_violations = 0
        scanned_rows = 0
        saw_after_target = False
        output_rows: list[dict[str, str]] = []

        for row in reader:
            scanned_rows += 1
            symbol = (row.get("Stock_symbol") or "").strip().upper()
            if symbol and last_symbol and symbol < last_symbol:
                monotonic_violations += 1
            if symbol:
                last_symbol = symbol

            if all(counts[t] > 0 for t in TARGETS) and symbol > max(TARGETS):
                saw_after_target = True
                break

            if symbol not in TARGETS:
                continue
            raw_date = (row.get("Date") or "").strip()
            d = day(raw_date)
            if d is None or not (START <= d <= END):
                continue
            url = (row.get("Url") or "").strip()
            if url:
                if url in seen_urls:
                    duplicate_urls += 1
                seen_urls.add(url)
            counts[symbol] += 1
            years[symbol][d[:4]] += 1
            shapes[shape(raw_date)] += 1
            min_ts[symbol] = min(min_ts.get(symbol, raw_date), raw_date)
            max_ts[symbol] = max(max_ts.get(symbol, raw_date), raw_date)
            output_rows.append({
                "Date": raw_date,
                "Stock_symbol": symbol,
                "Article_title": (row.get("Article_title") or "").strip(),
                "Url": url,
                "Publisher": (row.get("Publisher") or "").strip(),
            })

        content_range = response.headers.get("content-range")

    if monotonic_violations:
        raise RuntimeError(f"source Stock_symbol order is not monotonic: violations={monotonic_violations}")
    missing = [t for t in TARGETS if counts[t] == 0]
    if missing:
        raise RuntimeError(f"target symbols not reached inside bounded source range: {missing}; last_symbol={last_symbol}")
    if not saw_after_target:
        raise RuntimeError(f"bounded read did not prove completion beyond {max(TARGETS)}; last_symbol={last_symbol}")

    with open("fnspid-bounded-semis-20260906.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Date", "Stock_symbol", "Article_title", "Url", "Publisher"])
        writer.writeheader()
        writer.writerows(output_rows)

    report = {
        "schema": "research.fnspid_bounded_semis_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": URL,
        "source_commit": SOURCE_COMMIT,
        "expected_source_sha256": EXPECTED_SHA256,
        "source_sha_status": "PINNED_FROM_UPSTREAM_METADATA_NOT_FULL_REHASHED",
        "content_range": content_range,
        "scanned_rows_before_bound_exit": scanned_rows,
        "last_symbol_before_exit": last_symbol,
        "symbol_order_monotonic_violations": monotonic_violations,
        "requested_symbols": list(TARGETS),
        "requested_date_range": {"start": START, "end": END},
        "rows": int(sum(counts.values())),
        "coverage": {
            s: {
                "rows": counts[s],
                "min_raw_publication": min_ts.get(s),
                "max_raw_publication": max_ts.get(s),
                "years": dict(sorted(years[s].items())),
            }
            for s in TARGETS
        },
        "timestamp_shape_counts": dict(sorted(shapes.items())),
        "duplicate_url_rows": duplicate_urls,
        "unique_urls": len(seen_urls),
        "upstream_timestamp_semantics": {
            "processor_repo": "Zdong104/FNSPID_Financial_News_Dataset",
            "processor_commit": UPSTREAM_PROCESSOR_COMMIT,
            "processor_path": "data_processor/preprocess.py",
            "finding": "EDT/EST raw timestamps are shifted with negative four/five hour offsets before being labeled UTC; this is opposite the required local-to-UTC direction and can make publication timestamps appear earlier than true time.",
        },
        "causal_intraday_admission": "REJECT_UPSTREAM_UTC_CONVERSION_UNSAFE",
        "conservative_daily_candidate": "STRICT_NEXT_TRADING_SESSION_AFTER_RECORDED_DATE_ONLY",
        "daily_candidate_status": "READY_FOR_SEPARATE_NO_SAME_SESSION_ECONOMIC_ABLATION",
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_authority": False,
        "live_trading_change": False,
    }
    with open("fnspid-bounded-semis-receipt-20260906.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("FNSPID_BOUNDED_SEMIS=" + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
