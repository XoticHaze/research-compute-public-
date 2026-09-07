from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "p11.publication_authoritative_source_probe.v2"
PROVIDER = "ActuallyFreeAPI"
BASE_URL = "https://actually-free-api.vercel.app/api/news"
SEMICONDUCTORS = ("AMAT", "NVDA", "AMD", "AVGO", "KLAC", "LRCX")
HOMEBUILDERS = ("DHI", "LEN", "PHM", "TOL")
REQUIRED_HISTORY_DAYS = 180
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "MM-IBKR-P11-publication-source-probe/2.0"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _get_json(url: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        status = int(response.status)
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider response root is not an object")
    return status, payload


def _probe_symbol(symbol: str, start_date: str, max_pages: int = 3) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    request_refs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    duplicate_ids = 0
    pagination_total = None
    pagination_total_pages = None
    failure: dict[str, Any] | None = None

    for page in range(1, max_pages + 1):
        query = urllib.parse.urlencode(
            {"ticker": symbol, "startDate": start_date, "page": page, "limit": 100}
        )
        url = f"{BASE_URL}?{query}"
        try:
            status, payload = _get_json(url)
        except urllib.error.HTTPError as exc:
            failure = {
                "kind": "HTTP_ERROR",
                "status": int(exc.code),
                "page": page,
                "url": url,
            }
            break
        except Exception as exc:  # noqa: BLE001 - exact provider failure belongs in receipt
            failure = {
                "kind": "REQUEST_ERROR",
                "error": repr(exc),
                "page": page,
                "url": url,
            }
            break

        data = payload.get("data")
        pagination = payload.get("pagination")
        if not isinstance(data, list) or not isinstance(pagination, dict):
            failure = {
                "kind": "SCHEMA_ERROR",
                "page": page,
                "url": url,
                "top_level_keys": sorted(payload),
            }
            break

        pagination_total = pagination.get("total", pagination_total)
        pagination_total_pages = pagination.get("totalPages", pagination_total_pages)
        request_refs.append(
            {
                "page": page,
                "status": status,
                "row_count": len(data),
                "reported_total": pagination.get("total"),
                "reported_total_pages": pagination.get("totalPages"),
            }
        )

        for raw in data:
            if not isinstance(raw, dict):
                continue
            article_id = str(raw.get("id") or "").strip()
            if article_id and article_id in seen_ids:
                duplicate_ids += 1
            if article_id:
                seen_ids.add(article_id)
            rows.append(raw)

        if not data:
            break
        try:
            if page >= int(pagination.get("totalPages") or page):
                break
        except Exception:
            pass
        time.sleep(0.15)

    timestamps = [_parse_timestamp(row.get("pub_date")) for row in rows]
    valid_timestamps = [value for value in timestamps if value is not None]
    required_fields = ("id", "title", "link", "pub_date", "source", "tickers")
    field_failures = {
        field: sum(1 for row in rows if row.get(field) in (None, "", []))
        for field in required_fields
    }
    attribution_hits = sum(
        1
        for row in rows
        if symbol
        in {
            str(item or "").strip().upper()
            for item in (row.get("tickers") or [])
        }
    )

    return {
        "symbol": symbol,
        "ok": failure is None,
        "failure": failure,
        "rows_observed": len(rows),
        "unique_ids": len(seen_ids),
        "duplicate_ids": duplicate_ids,
        "reported_total": pagination_total,
        "reported_total_pages": pagination_total_pages,
        "earliest_pub_date": _iso(min(valid_timestamps)) if valid_timestamps else None,
        "latest_pub_date": _iso(max(valid_timestamps)) if valid_timestamps else None,
        "valid_pub_timestamp_rows": len(valid_timestamps),
        "ticker_attribution_hits": attribution_hits,
        "required_field_missing_counts": field_failures,
        "requests": request_refs,
    }


def _sector_coverage(
    name: str,
    symbols: tuple[str, ...],
    results: list[dict[str, Any]],
    observed_at: dt.datetime,
) -> dict[str, Any]:
    rows = [row for row in results if row.get("symbol") in symbols]
    rows_by_symbol = {str(row.get("symbol")): int(row.get("rows_observed") or 0) for row in rows}
    missing_symbols = [symbol for symbol in symbols if rows_by_symbol.get(symbol, 0) <= 0]
    earliest = [
        _parse_timestamp(row.get("earliest_pub_date"))
        for row in rows
        if row.get("earliest_pub_date")
    ]
    earliest = [value for value in earliest if value is not None]
    oldest = min(earliest) if earliest else None
    history_days = (observed_at - oldest).total_seconds() / 86400.0 if oldest else 0.0
    return {
        "sector": name,
        "required_symbols": list(symbols),
        "rows_by_symbol": rows_by_symbol,
        "missing_symbols": missing_symbols,
        "all_required_symbols_present": not missing_symbols,
        "earliest_pub_date": _iso(oldest) if oldest else None,
        "history_days": round(history_days, 4),
        "history_pass": history_days >= REQUIRED_HISTORY_DAYS,
        "total_rows_observed": sum(rows_by_symbol.values()),
    }


def build_receipt() -> dict[str, Any]:
    observed_at = _utc_now()
    requested_start = (observed_at - dt.timedelta(days=REQUIRED_HISTORY_DAYS)).date().isoformat()
    symbols = [*SEMICONDUCTORS, *HOMEBUILDERS]
    results = [_probe_symbol(symbol, requested_start) for symbol in symbols]
    successful = [row for row in results if row.get("ok")]

    schema_pass = bool(successful) and all(
        row.get("rows_observed", 0) == 0
        or (
            row.get("valid_pub_timestamp_rows") == row.get("rows_observed")
            and row.get("ticker_attribution_hits") == row.get("rows_observed")
            and all(
                value == 0
                for value in (row.get("required_field_missing_counts") or {}).values()
            )
        )
        for row in successful
    )
    provider_access_pass = len(successful) == len(results)
    sector_coverage = {
        "semiconductors": _sector_coverage(
            "semiconductors", SEMICONDUCTORS, results, observed_at
        ),
        "homebuilders": _sector_coverage(
            "homebuilders", HOMEBUILDERS, results, observed_at
        ),
    }
    required_symbol_coverage_pass = all(
        sector["all_required_symbols_present"] for sector in sector_coverage.values()
    )
    sector_history_pass = all(
        sector["history_pass"] for sector in sector_coverage.values()
    )

    if not provider_access_pass:
        decision = "REJECT_PROVIDER_ACCESS_OR_SCHEMA"
    elif not schema_pass:
        decision = "REJECT_PUBLICATION_OR_ATTRIBUTION_SCHEMA"
    elif not required_symbol_coverage_pass:
        decision = "REJECT_SECTOR_COVERAGE"
    elif not sector_history_pass:
        decision = "REJECT_INSUFFICIENT_SECTOR_HISTORY"
    else:
        decision = "ADMIT_SOURCE_CAUSALITY_FOR_SCORER_CALIBRATION"

    return {
        "schema": SCHEMA,
        "provider": PROVIDER,
        "endpoint": BASE_URL,
        "observed_at": _iso(observed_at),
        "purpose": "P11 publication-authoritative news-source rotation gate",
        "publication_semantics": {
            "article_id_field": "id",
            "publication_time_field": "pub_date",
            "source_field": "source",
            "canonical_link_field": "link",
            "symbol_attribution_field": "tickers",
            "retrieval_time_available": False,
            "full_text_required_for_this_gate": False,
        },
        "frozen_gate": {
            "required_history_days": REQUIRED_HISTORY_DAYS,
            "requested_start_date": requested_start,
            "required_sectors": {
                "semiconductors": list(SEMICONDUCTORS),
                "homebuilders": list(HOMEBUILDERS),
            },
            "requires_explicit_publication_time": True,
            "requires_article_id": True,
            "requires_ticker_attribution": True,
            "requires_every_declared_symbol_to_have_observed_coverage": True,
            "requires_each_sector_to_span_required_history": True,
            "note": "v2 fixes the v1 global-history loophole; sector sufficiency is evaluated independently and no economic threshold is tuned from observed results.",
        },
        "provider_access_pass": provider_access_pass,
        "schema_pass": schema_pass,
        "required_symbol_coverage_pass": required_symbol_coverage_pass,
        "sector_history_pass": sector_history_pass,
        "sector_coverage": sector_coverage,
        "decision": decision,
        "rows": results,
        "downstream": (
            "release_existing_scorer_calibration_consumer"
            if decision == "ADMIT_SOURCE_CAUSALITY_FOR_SCORER_CALIBRATION"
            else "rotate_to_next_publication_authoritative_source_without_weakening_timestamp_gate"
        ),
        "safety": {
            "private_input": False,
            "broker_calls": False,
            "strategy_spec_write": False,
            "runtime_mutation": False,
            "live_trading_change": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="research/results/p11_publication_authoritative_source_probe.json",
    )
    args = parser.parse_args()
    receipt = build_receipt()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "schema": receipt["schema"],
                "provider": receipt["provider"],
                "decision": receipt["decision"],
                "provider_access_pass": receipt["provider_access_pass"],
                "schema_pass": receipt["schema_pass"],
                "required_symbol_coverage_pass": receipt[
                    "required_symbol_coverage_pass"
                ],
                "sector_history_pass": receipt["sector_history_pass"],
                "sector_coverage": receipt["sector_coverage"],
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
