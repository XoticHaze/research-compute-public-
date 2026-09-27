from __future__ import annotations

"""Data E1 HFDL equity/ETF deep-history acquisition and normalization.

This is a public-compute research-data producer. It does not rank sources,
construct targets, mutate MM runtime state, or submit broker orders.

The provider file is downloaded with a sealed HFDL API key, hashed in full, and
then reduced to the admitted pre-March-2022 PiTrading source regime requested by
Data E1. Provider Eastern-Time labels are localized with DST-aware
America/New_York semantics and converted to UTC. Prices are never locally
adjusted or rewritten.
"""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

BASE_URL = "https://api.hfdatalibrary.com/v1"
PROVIDER = "HF Data Library"
DOI = "10.5281/zenodo.19501605"
VERSION = "raw"
TIMEFRAME = "1min"
FORMAT = "parquet"
SOURCE_REGIME = "pitrading"
SOURCE_REGIME_CUTOFF = pd.Timestamp("2022-03-01", tz="America/New_York")
USER_AGENT = "XoticHaze-Data-E1-HFDL/1.0"
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
REQUIRED_OUTPUT = ("timestamp", "open", "high", "low", "close", "volume")


class AcquisitionError(RuntimeError):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_symbol(value: str) -> str:
    symbol = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9.^_-]{1,20}", symbol):
        raise ValueError(f"invalid_symbol:{value!r}")
    return symbol


def _request_bytes_with_headers(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> tuple[bytes, dict[str, str]]:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            **dict(headers or {}),
        },
    )
    try:
        with urlopen(req, timeout=120) as response:
            raw = response.read(max_bytes + 1)
            status = int(response.status)
            response_headers = {str(k): str(v) for k, v in response.headers.items()}
    except HTTPError as exc:
        # Never surface credential-bearing headers or signed URLs.
        raise AcquisitionError(f"provider_http_{int(exc.code)}") from None
    except URLError as exc:
        raise AcquisitionError(f"provider_transport_{type(exc.reason).__name__}") from None
    if status != 200:
        raise AcquisitionError(f"provider_http_{status}")
    if len(raw) > max_bytes:
        raise AcquisitionError("provider_download_too_large")
    return raw, response_headers


def _request_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> bytes:
    raw, _ = _request_bytes_with_headers(
        url,
        headers=headers,
        max_bytes=max_bytes,
    )
    return raw


def _request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    raw = _request_bytes(url, headers=headers, max_bytes=1024 * 1024)
    try:
        node = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise AcquisitionError("provider_json_invalid") from exc
    if not isinstance(node, dict):
        raise AcquisitionError("provider_json_not_object")
    return node


def public_symbol_metadata(symbol: str) -> dict[str, Any]:
    symbol = _safe_symbol(symbol)
    node = _request_json(f"{BASE_URL}/symbols/{symbol}")
    ticker = str(node.get("ticker") or symbol).upper()
    versions = node.get("versions") if isinstance(node.get("versions"), dict) else {}
    return {
        "ticker": ticker,
        "versions": versions,
        "public_endpoint": f"{BASE_URL}/symbols/{symbol}",
        "authentication_required": False,
    }


def _read_api_key(path: Path) -> str:
    if not path.is_file():
        raise AcquisitionError("PRIVATE_INPUT_FULFILLMENT_FAILURE:hfdl_api_key_file_missing")
    key = path.read_text(encoding="utf-8").strip()
    if not key or len(key) > 512 or any(ch in key for ch in "\r\n\0"):
        raise AcquisitionError("PRIVATE_INPUT_FULFILLMENT_FAILURE:hfdl_api_key_invalid")
    return key


def _bars_download(symbol: str, *, api_key: str) -> tuple[bytes, dict[str, Any]]:
    symbol = _safe_symbol(symbol)
    raw, headers = _request_bytes_with_headers(
        f"{BASE_URL}/bars/{symbol}?version={VERSION}",
        headers={"X-API-Key": api_key, "Accept": "application/octet-stream"},
        max_bytes=MAX_DOWNLOAD_BYTES,
    )
    content_type = ""
    disposition = ""
    rate_remaining = None
    rate_reset = None
    for key, value in headers.items():
        lower = key.lower()
        if lower == "content-type":
            content_type = value
        elif lower == "content-disposition":
            disposition = value
        elif lower == "x-ratelimit-remaining":
            rate_remaining = value
        elif lower == "x-ratelimit-reset":
            rate_reset = value
    if "application/octet-stream" not in content_type.lower():
        raise AcquisitionError("provider_bars_content_type_rejected")
    return raw, {
        "endpoint": f"/v1/bars/{symbol}",
        "version": VERSION,
        "timeframe": TIMEFRAME,
        "format": FORMAT,
        "content_type": content_type,
        "content_disposition": disposition,
        "rate_limit_remaining": rate_remaining,
        "rate_limit_reset": rate_reset,
        "signed_url_persisted": False,
    }


def _normalized_column_map(columns: list[str]) -> dict[str, str]:
    norm = {re.sub(r"[^a-z0-9]", "", str(c).lower()): str(c) for c in columns}

    def one(*aliases: str) -> str:
        for alias in aliases:
            key = re.sub(r"[^a-z0-9]", "", alias.lower())
            if key in norm:
                return norm[key]
        raise AcquisitionError(f"provider_column_missing:{aliases[0]}")

    return {
        "timestamp": one("datetime", "timestamp", "date"),
        "open": one("open"),
        "high": one("high"),
        "low": one("low"),
        "close": one("close"),
        "volume": one("volume"),
        "source": one("source"),
    }


def normalize_pitrading_1min(
    raw_download: bytes,
    *,
    symbol: str,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    symbol = _safe_symbol(symbol)
    try:
        provider = pd.read_parquet(BytesIO(raw_download))
    except Exception as exc:
        raise AcquisitionError(f"provider_parquet_parse_failed:{type(exc).__name__}") from exc
    if provider.empty:
        raise AcquisitionError("provider_parquet_empty")

    cmap = _normalized_column_map([str(c) for c in provider.columns])
    source_labels = provider[cmap["source"]].astype(str).str.strip().str.lower()
    pitrading = provider.loc[source_labels.eq(SOURCE_REGIME)].copy()
    if pitrading.empty:
        raise AcquisitionError("provider_pitrading_regime_missing")

    parsed = pd.to_datetime(pitrading[cmap["timestamp"]], errors="coerce")
    timestamp_nulls = int(parsed.isna().sum())
    if timestamp_nulls:
        raise AcquisitionError(f"provider_timestamp_parse_nulls:{timestamp_nulls}")
    if getattr(parsed.dt, "tz", None) is None:
        try:
            eastern = parsed.dt.tz_localize(
                "America/New_York",
                ambiguous="raise",
                nonexistent="raise",
            )
        except Exception as exc:
            raise AcquisitionError(
                f"provider_timestamp_localization_failed:{type(exc).__name__}"
            ) from exc
    else:
        eastern = parsed.dt.tz_convert("America/New_York")

    cutoff_mask = eastern < SOURCE_REGIME_CUTOFF
    if not bool(cutoff_mask.all()):
        pitrading = pitrading.loc[cutoff_mask].copy()
        eastern = eastern.loc[cutoff_mask]

    start = pd.Timestamp(start_date, tz="America/New_York")
    end_exclusive = pd.Timestamp(end_date, tz="America/New_York") + pd.Timedelta(days=1)
    window_mask = (eastern >= start) & (eastern < end_exclusive)
    pitrading = pitrading.loc[window_mask].copy()
    eastern = eastern.loc[window_mask]
    if pitrading.empty:
        raise AcquisitionError("provider_requested_window_empty")

    out = pd.DataFrame(
        {
            "timestamp": eastern.dt.tz_convert("UTC"),
            "open": pd.to_numeric(pitrading[cmap["open"]], errors="coerce"),
            "high": pd.to_numeric(pitrading[cmap["high"]], errors="coerce"),
            "low": pd.to_numeric(pitrading[cmap["low"]], errors="coerce"),
            "close": pd.to_numeric(pitrading[cmap["close"]], errors="coerce"),
            "volume": pd.to_numeric(pitrading[cmap["volume"]], errors="coerce"),
        }
    )
    null_counts = {col: int(out[col].isna().sum()) for col in REQUIRED_OUTPUT}
    if any(null_counts.values()):
        raise AcquisitionError(f"provider_normalized_nulls:{null_counts}")

    duplicate_rows = int(out["timestamp"].duplicated(keep=False).sum())
    out = out.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)

    invalid_high = (
        out["high"] < out[["open", "close", "low"]].max(axis=1)
    )
    invalid_low = (
        out["low"] > out[["open", "close", "high"]].min(axis=1)
    )
    invalid_nonpositive = (out[["open", "high", "low", "close"]] <= 0).any(axis=1)
    invalid_volume = out["volume"] < 0

    ordered = out["timestamp"].sort_values()
    gaps = ordered.diff().dropna()
    qa = {
        "schema": "public_research.hfdl_e1_symbol_qa.v1",
        "symbol": symbol,
        "provider_rows_total": int(len(provider)),
        "pitrading_rows_in_requested_window": int(len(out)),
        "duplicate_timestamp_rows_before_dedupe": duplicate_rows,
        "null_counts": null_counts,
        "ohlc_invalid_high": int(invalid_high.sum()),
        "ohlc_invalid_low": int(invalid_low.sum()),
        "nonpositive_price_rows": int(invalid_nonpositive.sum()),
        "negative_volume_rows": int(invalid_volume.sum()),
        "first_timestamp_utc": out["timestamp"].iloc[0].isoformat(),
        "last_timestamp_utc": out["timestamp"].iloc[-1].isoformat(),
        "max_gap_minutes": (
            None if gaps.empty else float(gaps.max() / pd.Timedelta(minutes=1))
        ),
        "modal_positive_interval_seconds": (
            None
            if gaps.empty
            else float(gaps[gaps > pd.Timedelta(0)].mode().iloc[0] / pd.Timedelta(seconds=1))
            if not gaps[gaps > pd.Timedelta(0)].mode().empty
            else None
        ),
        "source_regime": SOURCE_REGIME,
        "source_regime_cutoff_exclusive": SOURCE_REGIME_CUTOFF.isoformat(),
        "timestamp_source_timezone": "America/New_York",
        "timestamp_output_timezone": "UTC",
        "forward_fill_applied": False,
        "local_price_adjustment_applied": False,
    }
    qa["admission_ready"] = not any(
        [
            qa["ohlc_invalid_high"],
            qa["ohlc_invalid_low"],
            qa["nonpositive_price_rows"],
            qa["negative_volume_rows"],
        ]
    )
    return out, qa


def acquire_symbol(
    symbol: str,
    *,
    api_key: str,
    output_root: Path,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    symbol = _safe_symbol(symbol)
    metadata = public_symbol_metadata(symbol)
    raw, download_receipt = _bars_download(symbol, api_key=api_key)
    normalized, qa = normalize_pitrading_1min(
        raw,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )

    symbol_dir = output_root / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = symbol_dir / f"{symbol}_1Min.parquet"
    normalized.to_parquet(
        normalized_path,
        index=False,
        engine="pyarrow",
        compression="zstd",
    )
    normalized_bytes = normalized_path.read_bytes()
    normalized_sha = _sha256(normalized_bytes)
    raw_sha = _sha256(raw)

    lineage = {
        "schema": "public_research.hfdl_e1_source_lineage.v1",
        "authority": "research-compute-public-data-e1",
        "source_authority": "HF Data Library",
        "provider": PROVIDER,
        "doi": DOI,
        "symbol": symbol,
        "source_timeframe": "1Min",
        "source_sha256": normalized_sha,
        "raw_download_sha256": raw_sha,
        "raw_download_bytes": int(len(raw)),
        "raw_download_persisted": False,
        "provider_version": VERSION,
        "provider_timeframe": TIMEFRAME,
        "provider_format": FORMAT,
        "provider_endpoint": download_receipt["endpoint"],
        "source_regime": "hfdl_pitrading_consolidated_pre_2022",
        "source_regime_filter": "source == pitrading AND timestamp < 2022-03-01 America/New_York",
        "timestamp_semantics": (
            "HFDL provider 1-minute tz-naive Eastern-Time label localized with "
            "America/New_York DST rules and converted to UTC; no forward fill"
        ),
        "adjustment_policy": (
            "provider split/dividend adjusted; HFDL raw version; "
            "no local price adjustment; admitted rows exclude HFDL IEX regime"
        ),
        "license": (
            "HFDL compilation/documentation CC BY 4.0; upstream PiTrading "
            "source terms retained in provenance"
        ),
        "attribution": (
            "Elkassabgi, A. (2026). HF Data Library: High-Frequency U.S. "
            "Equity Data. Zenodo DOI 10.5281/zenodo.19501605"
        ),
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "actual_first_timestamp": qa["first_timestamp_utc"],
        "actual_last_timestamp": qa["last_timestamp_utc"],
        "row_count": int(len(normalized)),
        "public_symbol_metadata": metadata,
        "download_receipt": download_receipt,
        "qa": qa,
    }
    lineage_path = symbol_dir / f"{symbol}_1Min.lineage.json"
    lineage_path.write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    qa_path = symbol_dir / f"{symbol}_1Min.qa.json"
    qa_path.write_text(json.dumps(qa, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "symbol": symbol,
        "status": "ACQUIRED" if qa["admission_ready"] else "QA_REVIEW_REQUIRED",
        "normalized_path": str(normalized_path),
        "normalized_sha256": normalized_sha,
        "lineage_path": str(lineage_path),
        "lineage_sha256": hashlib.sha256(lineage_path.read_bytes()).hexdigest(),
        "qa_path": str(qa_path),
        "raw_download_sha256": raw_sha,
        "raw_download_bytes": int(len(raw)),
        "row_count": int(len(normalized)),
        "first_timestamp": qa["first_timestamp_utc"],
        "last_timestamp": qa["last_timestamp_utc"],
        "source_regime": lineage["source_regime"],
        "admission_ready": bool(qa["admission_ready"]),
    }


def metadata_probe(symbols: list[str], *, output_root: Path) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for raw_symbol in symbols:
        symbol = _safe_symbol(raw_symbol)
        try:
            results.append(
                {
                    "symbol": symbol,
                    "status": "AVAILABLE",
                    "metadata": public_symbol_metadata(symbol),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "symbol": symbol,
                    "status": "PROBE_FAILED",
                    "error_class": type(exc).__name__,
                    "error": str(exc)[:500],
                }
            )
    receipt = {
        "schema": "public_research.hfdl_e1_public_coverage_receipt.v1",
        "provider": PROVIDER,
        "doi": DOI,
        "authentication_required_for_metadata": False,
        "authentication_required_for_download": True,
        "symbols": results,
    }
    path = output_root / "coverage_receipt.json"
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def run(
    *,
    symbols: list[str],
    output_root: Path,
    api_key_file: Path | None,
    start_date: str,
    end_date: str,
    metadata_only: bool,
) -> dict[str, Any]:
    coverage = metadata_probe(symbols, output_root=output_root)
    if metadata_only:
        return {
            "schema": "public_research.hfdl_e1_run_receipt.v1",
            "status": "METADATA_PROBED",
            "coverage": coverage,
            "downloads_attempted": False,
        }

    if api_key_file is None:
        raise AcquisitionError(
            "PRIVATE_INPUT_FULFILLMENT_FAILURE:hfdl_api_key_file_not_supplied"
        )
    api_key = _read_api_key(api_key_file)
    acquisitions: list[dict[str, Any]] = []
    for symbol in symbols:
        acquisitions.append(
            acquire_symbol(
                symbol,
                api_key=api_key,
                output_root=output_root,
                start_date=start_date,
                end_date=end_date,
            )
        )
    complete = all(bool(row.get("admission_ready")) for row in acquisitions)
    receipt = {
        "schema": "public_research.hfdl_e1_run_receipt.v1",
        "status": "ACQUIRED" if complete else "QA_REVIEW_REQUIRED",
        "provider": PROVIDER,
        "doi": DOI,
        "version": VERSION,
        "timeframe": TIMEFRAME,
        "format": FORMAT,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "symbols": acquisitions,
        "api_key_persisted": False,
        "signed_urls_persisted": False,
        "raw_downloads_persisted": False,
        "acquisition_endpoint": "GET /v1/bars/{ticker}?version=raw",
        "one_download_request_per_ticker": True,
        "broker_credentials_used": False,
        "live_trading_allowed": False,
    }
    (output_root / "acquisition_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True, help="Comma-separated ticker list")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--start-date", default="2004-01-01")
    parser.add_argument("--end-date", default="2022-02-28")
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()

    symbols = [_safe_symbol(x) for x in args.symbols.split(",") if x.strip()]
    if not symbols:
        raise SystemExit("at least one symbol is required")
    try:
        receipt = run(
            symbols=symbols,
            output_root=args.output_root.resolve(),
            api_key_file=args.api_key_file,
            start_date=args.start_date,
            end_date=args.end_date,
            metadata_only=bool(args.metadata_only),
        )
    except AcquisitionError as exc:
        failure = {
            "schema": "public_research.hfdl_e1_run_receipt.v1",
            "status": (
                "PRIVATE_INPUT_FULFILLMENT_FAILURE"
                if str(exc).startswith("PRIVATE_INPUT_FULFILLMENT_FAILURE:")
                else "SOURCE_TRANSPORT_FAILURE"
            ),
            "error": str(exc),
            "symbols": symbols,
            "broker_credentials_used": False,
            "live_trading_allowed": False,
        }
        args.output_root.mkdir(parents=True, exist_ok=True)
        (args.output_root / "acquisition_receipt.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("HFDL_E1_RECEIPT=" + json.dumps(failure, sort_keys=True))
        return 2

    print("HFDL_E1_RECEIPT=" + json.dumps(receipt, sort_keys=True))
    return 0 if receipt.get("status") in {"METADATA_PROBED", "ACQUIRED"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
