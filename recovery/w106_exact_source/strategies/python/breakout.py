from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from .base import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    def name(self) -> str:
        return "breakout"

    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[str], dict[str, object]]:
        if df is None or df.empty:
            return None, {"reason": "empty"}
        n = int(self.config.get("BREAKOUT_LOOKBACK", 20))
        if len(df) < n + 2:
            return None, {"reason": "insufficient_data"}
        highs = pd.to_numeric(df["high"], errors="coerce")
        lows = pd.to_numeric(df["low"], errors="coerce")
        price = float(pd.to_numeric(df["close"].iloc[-1], errors="coerce"))
        hh = float(highs.iloc[-(n + 1):-1].max())
        ll = float(lows.iloc[-(n + 1):-1].min())
        if price > hh:
            return "BUY", {"price": price, "high_break": hh, "lookback": n}
        if price < ll:
            return "SELL", {"price": price, "low_break": ll, "lookback": n}
        return None, {"price": price, "high_break": hh, "low_break": ll, "lookback": n}
