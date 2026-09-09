from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import pandas as pd

REQUIRED_COLUMNS = (
    "symbol", "timestamp", "open", "high", "low", "close", "volume",
    "source", "asset_type", "bar_size", "session", "contract_id", "wap", "bar_count",
)

@dataclass(frozen=True)
class ForwardBarContract:
    schema: str = "research.forward_bar.v1"
    timestamp_semantics: str = "bar_end_or_source_native_timestamp_normalized_to_UTC"
    price_semantics: str = "source_native_ohlc_no_synthetic_gap_fill"
    volume_semantics: str = "source_native_volume_when_available"
    ibkr_mapping: str = (
        "IBKR BarData.date->timestamp; open/high/low/close/volume/wap/barCount map directly; "
        "Contract.conId/localSymbol may populate contract_id; symbol/asset_type/bar_size/session are adapter metadata."
    )


def normalize_frame(rows: pd.DataFrame | Iterable[dict]) -> pd.DataFrame:
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing normalized bar columns: {missing}")
    df = df.loc[:, REQUIRED_COLUMNS].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
    for c in ("open", "high", "low", "close", "volume", "wap", "bar_count"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("OHLC contains non-numeric/null values")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC must be positive")
    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high invariant failed")
    if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low invariant failed")
    if (df["volume"].fillna(0) < 0).any():
        raise ValueError("volume must be nonnegative")
    if df.duplicated(["symbol", "timestamp", "contract_id"]).any():
        raise ValueError("duplicate normalized bars")
    return df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
