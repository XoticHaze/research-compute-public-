from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from .base import BaseStrategy


class DynamicBreakoutIIStrategy(BaseStrategy):
    def name(self) -> str:
        return "dynamic_breakout_ii"

    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[str], dict[str, object]]:
        if df is None or df.empty:
            return None, {"reason": "empty"}
        base_lookback = int(self.config.get("DB2_LOOKBACK", 20))
        vol_window = int(self.config.get("DB2_VOL_WINDOW", 20))
        band_mult = float(self.config.get("DB2_BAND_MULT", 2.0))
        closes = pd.to_numeric(df["close"], errors="coerce")
        if len(closes) < max(base_lookback, vol_window) + 5:
            return None, {"reason": "insufficient_data"}

        returns = closes.pct_change()
        recent_vol = float(returns.tail(vol_window).std())
        long_vol = float(returns.tail(vol_window * 2).std()) if len(returns) >= vol_window * 2 else recent_vol
        vol_ratio = recent_vol / long_vol if pd.notna(long_vol) and long_vol not in (0.0, -0.0) else 1.0
        dynamic_lookback = max(10, min(60, int(round(base_lookback * max(0.5, min(1.5, vol_ratio or 1.0))))))
        window = closes.iloc[-dynamic_lookback:]
        mean = float(window.mean())
        std = float(window.std())
        upper = mean + band_mult * std
        lower = mean - band_mult * std
        price = float(closes.iloc[-1])
        meta = {"price": price, "mean": mean, "upper": upper, "lower": lower, "dynamic_lookback": dynamic_lookback, "vol_ratio": vol_ratio, "band_mult": band_mult}
        if price > upper:
            return "BUY", meta
        if price < lower:
            return "SELL", meta
        return None, meta
