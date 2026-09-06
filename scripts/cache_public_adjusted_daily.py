#!/usr/bin/env python3
"""Materialize reusable public adjusted-daily market data.

This utility is intentionally market-data-only. It contains no private strategy,
research, runtime, broker, or promotion logic. Yahoo chart semantics mirror the
public adjusted-close loader used by the private Foundry experiments so private
consumers can parity-check and reuse the resulting immutable artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

HOST = "https://query1.finance.yahoo.com/v8/finance/chart"


def _epoch(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(symbol: str, start: str, end: str) -> pd.DataFrame:
    query = urlencode({
        "period1": _epoch(start),
        "period2": _epoch(end),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    })
    req = Request(
        f"{HOST}/{symbol}?{query}",
        headers={"User-Agent": "Mozilla/5.0 research-compute-public/1.0"},
    )
    with urlopen(req, timeout=60) as response:  # noqa: S310 fixed HTTPS host
        payload = json.loads(response.read().decode("utf-8"))
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no Yahoo chart result")
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {})
    adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    close = adjusted or (indicators.get("quote") or [{}])[0].get("close")
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
        "price": pd.to_numeric(pd.Series(close), errors="coerce"),
    }).dropna()
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    frame.insert(0, "symbol", symbol)
    if frame.empty:
        raise RuntimeError(f"{symbol}: empty adjusted-close series")
    return frame


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--output-root", type=Path, required=True)
    args = p.parse_args()

    symbols = tuple(dict.fromkeys(s.upper().strip() for s in args.symbols if s.strip()))
    if not symbols:
        raise SystemExit("no symbols")
    args.output_root.mkdir(parents=True, exist_ok=True)
    frames = [_load(symbol, args.start, args.end) for symbol in symbols]
    combined = pd.concat(frames, ignore_index=True)
    csv_path = args.output_root / "adjusted-daily.csv"
    combined.to_csv(csv_path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")

    rows = {}
    for symbol, group in combined.groupby("symbol", sort=True):
        rows[str(symbol)] = {
            "rows": int(len(group)),
            "first": pd.Timestamp(group["timestamp"].iloc[0]).isoformat(),
            "last": pd.Timestamp(group["timestamp"].iloc[-1]).isoformat(),
        }
    receipt = {
        "schema": "research_compute.public_adjusted_daily_cache.v1",
        "public_data_only": True,
        "source": "query1.finance.yahoo.com chart API",
        "loader_semantics": "adjusted close; interval=1d; events=history; includeAdjustedClose=true; UTC epoch bounds",
        "symbols": list(symbols),
        "start": args.start,
        "end": args.end,
        "rows": rows,
        "csv_sha256": _sha256(csv_path),
        "private_source_included": False,
        "runtime_authority": False,
        "promotion_authority": False,
        "broker_authority": False,
    }
    (args.output_root / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
