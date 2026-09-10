from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Any
import pandas as pd

REQUIRED_COLUMNS = (
    "symbol", "timestamp", "open", "high", "low", "close", "volume",
    "source", "asset_type", "bar_size", "session", "contract_id", "wap", "bar_count",
)


@dataclass(frozen=True)
class ForwardBarContract:
    schema: str = "research.forward_bar.v2"
    timestamp_semantics: str = "source timestamp normalized to UTC; daily equity bars represent the completed source session"
    price_semantics: str = "source-native or provider-consistently-adjusted OHLC; no synthetic gap fill"
    volume_semantics: str = "source-native volume when available"
    ibkr_mapping: str = (
        "BarData.date->timestamp; BarData.open/high/low/close/volume/wap/barCount map directly; "
        "Contract.conId or localSymbol->contract_id; symbol/secType/barSize/session are adapter metadata"
    )


def _finite_numeric(df: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for c in columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df[list(columns)].isna().any().any():
        raise ValueError(f"non-numeric/null values in required numeric columns {columns}")


def normalize_frame(rows: pd.DataFrame | Iterable[dict], *, relative_ohlc_tolerance: float = 1e-7) -> pd.DataFrame:
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing normalized bar columns: {missing}")
    df = df.loc[:, REQUIRED_COLUMNS].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
    _finite_numeric(df, ("open", "high", "low", "close"))
    for c in ("volume", "wap", "bar_count"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC must be positive")
    row_scale = df[["open", "high", "low", "close"]].abs().max(axis=1).clip(lower=1.0)
    tol = relative_ohlc_tolerance * row_scale
    row_max = df[["open", "close", "low"]].max(axis=1)
    row_min = df[["open", "close", "high"]].min(axis=1)
    if ((row_max - df["high"]) > tol).any():
        raise ValueError("high invariant failed beyond numeric tolerance")
    if ((df["low"] - row_min) > tol).any():
        raise ValueError("low invariant failed beyond numeric tolerance")
    if (df["volume"].fillna(0) < 0).any():
        raise ValueError("volume must be nonnegative")
    if df.duplicated(["symbol", "timestamp", "contract_id"]).any():
        raise ValueError("duplicate normalized bars")
    return df.sort_values(["symbol", "timestamp", "contract_id"]).reset_index(drop=True)


def ibkr_bar_to_record(
    bar: Any,
    contract: Any,
    *,
    symbol: str,
    asset_type: str,
    bar_size: str,
    session: str,
    source: str = "ibkr",
) -> dict:
    """Adapter boundary only; intentionally does not import ibapi/ib_insync."""
    con_id = getattr(contract, "conId", None)
    local_symbol = getattr(contract, "localSymbol", None)
    contract_id = f"conid:{con_id}" if con_id not in (None, 0, "") else str(local_symbol or symbol)
    return {
        "symbol": symbol,
        "timestamp": getattr(bar, "date"),
        "open": getattr(bar, "open"),
        "high": getattr(bar, "high"),
        "low": getattr(bar, "low"),
        "close": getattr(bar, "close"),
        "volume": getattr(bar, "volume", None),
        "source": source,
        "asset_type": asset_type,
        "bar_size": bar_size,
        "session": session,
        "contract_id": contract_id,
        "wap": getattr(bar, "wap", None),
        "bar_count": getattr(bar, "barCount", None),
    }
