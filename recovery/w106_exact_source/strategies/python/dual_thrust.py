from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from .base import BaseStrategy


class DualThrustStrategy(BaseStrategy):
    def name(self) -> str:
        return "dual_thrust"

    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[str], dict[str, object]]:
        if df is None or df.empty:
            return None, {"reason": "empty"}
        lookback = int(self.config.get("DT_LOOKBACK", 4))
        k1 = float(self.config.get("DT_K1", 0.5))
        k2 = float(self.config.get("DT_K2", 0.5))
        if len(df) < lookback + 2:
            return None, {"reason": "insufficient_data"}

        closes = pd.to_numeric(df["close"], errors="coerce")
        opens = pd.to_numeric(df["open"], errors="coerce")
        hist = df.iloc[-(lookback + 1):-1]
        hh = float(pd.to_numeric(hist["high"], errors="coerce").max())
        hc = float(pd.to_numeric(hist["close"], errors="coerce").max())
        lc = float(pd.to_numeric(hist["close"], errors="coerce").min())
        ll = float(pd.to_numeric(hist["low"], errors="coerce").min())
        trigger_range = max(hh - lc, hc - ll)
        open_ref = float(opens.iloc[-1]) if pd.notna(opens.iloc[-1]) else float(closes.iloc[-2])
        buy_trigger = open_ref + k1 * trigger_range
        sell_trigger = open_ref - k2 * trigger_range
        price = float(closes.iloc[-1])
        meta = {"price": price, "buy_trigger": buy_trigger, "sell_trigger": sell_trigger, "range": trigger_range, "lookback": lookback, "k1": k1, "k2": k2}
        if price > buy_trigger:
            return "BUY", meta
        if price < sell_trigger:
            return "SELL", meta
        return None, meta
