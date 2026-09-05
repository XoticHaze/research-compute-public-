from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from .base import BaseStrategy


class MACrossoverStrategy(BaseStrategy):
    def name(self) -> str:
        return "ma_crossover"

    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[str], dict[str, object]]:
        if df is None or df.empty:
            return None, {"reason": "empty"}
        fast = int(self.config.get("MA_FAST", 9))
        slow = int(self.config.get("MA_SLOW", 21))
        fcol = f"EMA_{fast}"
        scol = f"EMA_{slow}"
        if fcol not in df.columns or scol not in df.columns:
            return None, {"reason": "missing_columns", "missing_columns": [col for col in (fcol, scol) if col not in df.columns]}

        f = df[fcol].astype(float)
        s = df[scol].astype(float)
        if len(df) < 3 or f.isna().any() or s.isna().any():
            return None, {"reason": "insufficient_data"}

        f_prev, s_prev = float(f.iloc[-2]), float(s.iloc[-2])
        f_now, s_now = float(f.iloc[-1]), float(s.iloc[-1])
        if f_prev <= s_prev and f_now > s_now:
            return "BUY", {"fast": f_now, "slow": s_now}
        if f_prev >= s_prev and f_now < s_now:
            return "SELL", {"fast": f_now, "slow": s_now}
        return None, {"fast": f_now, "slow": s_now}
