from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/fcd1056328b3db04769d4530abe4158d086cffc1/Stock_news/nasdaq_exteral_data.csv"
EXPECTED_SHA256 = "1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da"
SOURCE_COMMIT = "fcd1056328b3db04769d4530abe4158d086cffc1"
UPSTREAM_PROCESSOR_COMMIT = "4054842ec476953b30ee874d4b7e8eea786a21fa"
TARGETS = ("AMAT", "AMD", "AVGO")
START = "2015-01-01"
END = "2023-12-31"
MAX_RANGE_BYTES = 2 * 1024 * 1024 * 1024
SEGMENT_BYTES = 128 * 1024 * 1024
TRANSFER_CHUNK = 8 * 1024 * 1024
SEGMENT_RETRIES = 3
CSV_FIELD_LIMIT = 64 * 1024 * 1024
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


def _download_segment(session: requests.Session, start: int, stop: int, output) -> dict:
    expected = stop - start + 1
    last_error: Exception | None = None
    for attempt in range(1, SEGMENT_RETRIES + 1):
        try:
            headers = {
                "Range": f"bytes={start}-{stop}",
                "Accept-Encoding": "identity",
                "User-Agent": "research-compute/1.0",
            }
            with session.get(URL, headers=headers, stream=True, timeout=(30, 180), allow_redirects=True) as response:
                response.raise_for_status()
                if response.status_code != 206:
                    raise RuntimeError(f"segment {start}-{stop}: expected HTTP 206, got {response.status_code}")
                content_range = response.headers.get("content-range") or ""
                expected_prefix = f"bytes {start}-{stop}/"
                if not content_range.startswith(expected_prefix):
                    raise RuntimeError(
                        f"segment {start}-{stop}: unexpected Content-Range {content_range!r}"
                    )
                temp = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024)
                received = 0
                for chunk in response.iter_content(chunk_size=TRANSFER_CHUNK):
                    if not chunk:
                        continue
                    temp.write(chunk)
                    received += len(chunk)
                if received != expected:
                    raise RuntimeError(
                        f"segment {start}-{stop}: short read {received} != {expected}"
                    )
                temp.seek(0)
                while True:
                    chunk = temp.read(TRANSFER_CHUNK)
                    if not chunk:
                        break
                    output.write(chunk)
                temp.close()
                return {
                    "start": start,
                    "stop": stop,
                    "bytes": received,
                    "attempt": attempt,
                    "content_range": content_range,
                }
        except Exception as exc:  # bounded deterministic retry of exact bytes
            last_error = exc
    raise RuntimeError(f"segment {start}-{stop} failed after {SEGMENT_RETRIES} attempts: {last_error}")


def _materialize_prefix(path: Path) -> list[dict]:
    receipts: list[dict] = []
    session = requests.Session()
    with path.open("wb") as output:
        start = 0
        while start < MAX_RANGE_BYTES:
            stop = min(MAX_RANGE_BYTES - 1, start + SEGMENT_BYTES - 1)
            receipt = _download_segment(session, start, stop, output)
            receipts.append(receipt)
            print("FNSPID_PREFIX_SEGMENT=" + json.dumps(receipt, sort_keys=True), flush=True)
            start = stop + 1
    size = path.stat().st_size
    if size != MAX_RANGE_BYTES:
        raise RuntimeError(f"fixed prefix size mismatch {size} != {MAX_RANGE_BYTES}")
    return receipts


def main() -> None:
    # Article bodies can exceed Python's default 128 KiB CSV-field cap. Article
    # is not persisted, but the parser must traverse it to reach later rows.
    csv.field_size_limit(CSV_FIELD_LIMIT)

    prefix_path = Path("fnspid-fixed-prefix-2gib.tmp")
    segment_receipts = _materialize_prefix(prefix_path)
    prefix_sha256 = hashlib.sha256()
    with prefix_path.open("rb") as raw:
        for chunk in iter(lambda: raw.read(TRANSFER_CHUNK), b""):
            prefix_sha256.update(chunk)

    counts = Counter()
    years = defaultdict(Counter)
    shapes = Counter()
    min_ts: dict[str, str] = {}
    max_ts: dict[str, str] = {}
    first_row_index: dict[str, int] = {}
    last_row_index: dict[str, int] = {}
    seen_urls: set[str] = set()
    duplicate_urls = 0
    last_symbol = ""
    monotonic_violations = 0
    violation_examples: list[dict[str, object]] = []
    scanned_rows = 0
    output_rows: list[dict[str, str]] = []
    truncated_tail_row = False

    with prefix_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"Date", "Stock_symbol", "Url", "Publisher", "Article_title"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise RuntimeError(f"unexpected source schema: {reader.fieldnames}")
        while True:
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error as exc:
                # The deterministic 2GiB prefix can terminate inside one quoted
                # Article field. Only a parser error at the physical prefix tail
                # is admissible; earlier parser errors remain fatal.
                if fh.tell() >= MAX_RANGE_BYTES - TRANSFER_CHUNK:
                    truncated_tail_row = True
                    break
                raise RuntimeError(f"CSV parse error before prefix tail at byte {fh.tell()}: {exc}") from exc
            scanned_rows += 1
            symbol = (row.get("Stock_symbol") or "").strip().upper()
            if symbol and last_symbol and symbol < last_symbol:
                monotonic_violations += 1
                if len(violation_examples) < 20:
                    violation_examples.append({
                        "row": scanned_rows,
                        "previous_symbol": last_symbol,
                        "current_symbol": symbol,
                    })
            if symbol:
                last_symbol = symbol

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
            first_row_index.setdefault(symbol, scanned_rows)
            last_row_index[symbol] = scanned_rows
            output_rows.append({
                "Date": raw_date,
                "Stock_symbol": symbol,
                "Article_title": (row.get("Article_title") or "").strip(),
                "Url": url,
                "Publisher": (row.get("Publisher") or "").strip(),
            })

    missing = [t for t in TARGETS if counts[t] == 0]
    if missing:
        raise RuntimeError(f"target symbols absent from fixed 2GiB prefix: {missing}; last_symbol={last_symbol}")

    with open("fnspid-bounded-semis-20260906.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Date", "Stock_symbol", "Article_title", "Url", "Publisher"])
        writer.writeheader()
        writer.writerows(output_rows)

    report = {
        "schema": "research.fnspid_bounded_semis_receipt.v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": URL,
        "source_commit": SOURCE_COMMIT,
        "expected_source_sha256": EXPECTED_SHA256,
        "source_sha_status": "PINNED_FROM_UPSTREAM_METADATA_NOT_FULL_REHASHED",
        "source_slice": {
            "type": "DETERMINISTIC_FIXED_BYTE_PREFIX",
            "requested_bytes": MAX_RANGE_BYTES,
            "prefix_sha256": prefix_sha256.hexdigest(),
            "segment_bytes": SEGMENT_BYTES,
            "segment_receipts": segment_receipts,
            "truncated_tail_row_discarded": truncated_tail_row,
            "completeness": "BOUNDED_PREFIX_NOT_FULL_SOURCE",
            "reason": "raw Stock_symbol order is not globally monotonic, so this receipt does not claim complete per-symbol FNSPID coverage",
        },
        "scanned_rows": scanned_rows,
        "last_symbol": last_symbol,
        "symbol_order_monotonic_violations": monotonic_violations,
        "symbol_order_violation_examples": violation_examples,
        "requested_symbols": list(TARGETS),
        "requested_date_range": {"start": START, "end": END},
        "rows": int(sum(counts.values())),
        "coverage": {
            s: {
                "rows": counts[s],
                "min_raw_publication": min_ts.get(s),
                "max_raw_publication": max_ts.get(s),
                "first_scanned_row": first_row_index.get(s),
                "last_scanned_row": last_row_index.get(s),
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
        "daily_candidate_status": "BOUNDED_PREFIX_MATERIALIZED_AWAIT_COVERAGE_GATE",
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
    prefix_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
