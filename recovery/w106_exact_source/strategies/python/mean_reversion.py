from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from .base import BaseStrategy


class MeanReversionStrategy(BaseStrategy):
    def name(self) -> str:
        return "mean_reversion"

    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[str], dict[str, object]]:
        if df is None or df.empty:
            return None, {"reason": "empty"}
        period = int(self.config.get("MR_MA_PERIOD", 20))
        mult = float(self.config.get("MR_STD_MULT", 2.0))
        close = pd.to_numeric(df["close"], errors="coerce")
        if len(close) < period + 2:
            return None, {"reason": "insufficient_data"}
        ma = close.rolling(period).mean()
        sd = close.rolling(period).std()
        mu = float(ma.iloc[-1])
        sigma = float(sd.iloc[-1])
        price = float(close.iloc[-1])
        upper = mu + mult * sigma
        lower = mu - mult * sigma
        zscore = (price - mu) / sigma if pd.notna(sigma) and sigma not in (0.0, -0.0) else 0.0
        if price < lower:
            return "BUY", {"price": price, "mu": mu, "upper": upper, "lower": lower, "zscore": zscore, "period": period}
        if price > upper:
            return "SELL", {"price": price, "mu": mu, "upper": upper, "lower": lower, "zscore": zscore, "period": period}
        return None, {"price": price, "mu": mu, "upper": upper, "lower": lower, "zscore": zscore, "period": period}
