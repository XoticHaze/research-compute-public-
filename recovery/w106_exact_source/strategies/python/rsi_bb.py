from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from .base import BaseStrategy


def _bb_column_names(period: int, stddev: float, prefix: str) -> list[str]:
    names = [f"{prefix}_{period}_{float(stddev):g}"]
    if float(stddev).is_integer():
        names.append(f"{prefix}_{period}_{int(stddev)}")
    names.append(f"{prefix}_{period}_{stddev}")
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return seen


class RSIBBStrategy(BaseStrategy):
    def name(self) -> str:
        return "rsi_bb"

    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[str], dict[str, object]]:
        if df is None or df.empty:
            return None, {"reason": "empty"}
        row = df.iloc[-1]

        rsi_period = int(self.config.get("RSI_PERIOD", 14))
        bb_period = int(self.config.get("BB_PERIOD", 20))
        bb_std = float(self.config.get("BB_STDDEV_MULTIPLIER", 2.0))
        rsi_col = f"RSI_{rsi_period}"
        rsi = float(row.get(rsi_col, float("nan"))) if rsi_col in row else float("nan")
        ema50 = float(row.get("EMA_50", float("nan")))
        ema66 = float(row.get("EMA_66", float("nan")))
        ema200 = float(row.get("EMA_200", float("nan")))

        hi_above = float(self.config.get("RSI_LIMIT_HIGH_EMA50_ABOVE_EMA200", 40))
        hi_below = float(self.config.get("RSI_LIMIT_HIGH_EMA50_BELOW_EMA200", 35))
        hi_below66 = float(self.config.get("RSI_LIMIT_HIGH_EMA66_BELOW_EMA200", 30))

        if pd.isna(ema50) or pd.isna(ema66) or pd.isna(ema200):
            limit = hi_below
        elif ema50 > ema200:
            limit = hi_above
        elif ema50 < ema200 and ema66 < ema200:
            limit = hi_below66
        else:
            limit = hi_below

        price = float(row.get("close", float("nan")))
        bbl = None
        for col in _bb_column_names(bb_period, bb_std, "BBL"):
            if col in row:
                bbl = row.get(col)
                break
        bbu = None
        for col in _bb_column_names(bb_period, bb_std, "BBU"):
            if col in row:
                bbu = row.get(col)
                break

        use_rsi = bool(self.config.get("ENABLE_RSI_CONDITION", True))
        use_bb = bool(self.config.get("ENABLE_BB_CONDITION", False))
        conds = []
        if use_rsi and not pd.isna(rsi):
            conds.append(rsi < limit)
        if use_bb and bbl is not None and not pd.isna(bbl) and not pd.isna(price):
            conds.append(price > float(bbl))

        meta = {"rsi": rsi, "limit": limit, "bbl": bbl, "bbu": bbu, "price": price, "bb_period": bb_period, "bb_std": bb_std}
        if conds and all(conds):
            return "BUY", meta
        return None, meta
