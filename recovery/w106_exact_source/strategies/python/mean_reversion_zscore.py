from __future__ import annotations

from typing import Any, Optional, Tuple

import pandas as pd

from .base import BaseStrategy


class MeanReversionZScoreStrategy(BaseStrategy):
    """Long-only z-score mean reversion proof adapter.

    Consumes indicator-registry fields instead of recomputing hidden rolling bands.
    Exits are surfaced as condition state, but no SELL signal is emitted by
    default because the first proof does not have strategy-managed position state.
    """

    DEFAULTS: dict[str, Any] = {
        "ENTRY_Z_THRESHOLD": -1.5,
        "EXIT_Z_THRESHOLD": 0.5,
        "ENABLE_VOLUME_GATE": True,
        "MIN_VOLUME_Z": -0.5,
        "ENABLE_EXIT_SIGNAL_WITHOUT_POSITION": False,
    }

    def name(self) -> str:
        return "mean_reversion_zscore"

    @classmethod
    def parameter_schema(cls) -> dict[str, dict[str, Any]]:
        return {
            "ENTRY_Z_THRESHOLD": {"type": "float", "default": cls.DEFAULTS["ENTRY_Z_THRESHOLD"], "group": "Signal", "label": "Entry z-score threshold", "description": "Buy when Z_CLOSE_20 is less than or equal to this value."},
            "EXIT_Z_THRESHOLD": {"type": "float", "default": cls.DEFAULTS["EXIT_Z_THRESHOLD"], "group": "Signal", "label": "Exit z-score threshold", "description": "Exit long when Z_CLOSE_20 has reverted to this value or above."},
            "ENABLE_VOLUME_GATE": {"type": "bool", "default": cls.DEFAULTS["ENABLE_VOLUME_GATE"], "group": "Confirmation", "label": "Require volume z-score gate", "description": "When enabled, entry also requires Z_VOLUME_20 above MIN_VOLUME_Z."},
            "MIN_VOLUME_Z": {"type": "float", "default": cls.DEFAULTS["MIN_VOLUME_Z"], "group": "Confirmation", "label": "Minimum volume z-score", "description": "Volume confirmation threshold for Z_VOLUME_20."},
        }

    @classmethod
    def condition_spec(cls) -> dict[str, Any]:
        return {
            "entry_long": {
                "label": "Buy mean-reversion stretch",
                "logic": "all",
                "items": [
                    {"id": "z_close_oversold", "label": "Z_CLOSE_20 below entry threshold", "left": "Z_CLOSE_20", "operator": "<=", "right_param": "ENTRY_Z_THRESHOLD"},
                    {"id": "volume_gate", "label": "Volume z-score confirms entry", "enabled_param": "ENABLE_VOLUME_GATE", "left": "Z_VOLUME_20", "operator": ">=", "right_param": "MIN_VOLUME_Z"},
                ],
            },
            "exit_long": {
                "label": "Exit after mean reversion",
                "logic": "all",
                "items": [
                    {"id": "z_close_reverted", "label": "Z_CLOSE_20 reached exit threshold", "left": "Z_CLOSE_20", "operator": ">=", "right_param": "EXIT_Z_THRESHOLD"}
                ],
            },
        }

    def _param(self, key: str) -> Any:
        return self.config.get(key, self.DEFAULTS.get(key))

    def _float_param(self, key: str) -> float:
        try:
            return float(self._param(key))
        except Exception:
            return float(self.DEFAULTS[key])

    def _bool_param(self, key: str) -> bool:
        value = self._param(key)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _last_float(df: pd.DataFrame, column: str) -> Optional[float]:
        if df is None or df.empty or column not in df.columns:
            return None
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            return None
        value = float(series.iloc[-1])
        if pd.isna(value):
            return None
        return value

    def evaluate_conditions(self, df: pd.DataFrame) -> dict[str, Any]:
        close = self._last_float(df, "close")
        z_close = self._last_float(df, "Z_CLOSE_20")
        z_volume = self._last_float(df, "Z_VOLUME_20")
        entry_threshold = self._float_param("ENTRY_Z_THRESHOLD")
        exit_threshold = self._float_param("EXIT_Z_THRESHOLD")
        min_volume_z = self._float_param("MIN_VOLUME_Z")
        enable_volume_gate = self._bool_param("ENABLE_VOLUME_GATE")

        entry_z_pass = z_close is not None and z_close <= entry_threshold
        volume_pass = (not enable_volume_gate) or (z_volume is not None and z_volume >= min_volume_z)
        exit_z_pass = z_close is not None and z_close >= exit_threshold

        return {
            "current_values": {"close": close, "Z_CLOSE_20": z_close, "Z_VOLUME_20": z_volume},
            "parameters": {"ENTRY_Z_THRESHOLD": entry_threshold, "EXIT_Z_THRESHOLD": exit_threshold, "ENABLE_VOLUME_GATE": enable_volume_gate, "MIN_VOLUME_Z": min_volume_z},
            "entry_long": {
                "passed": bool(entry_z_pass and volume_pass),
                "logic": "all",
                "items": [
                    {"id": "z_close_oversold", "label": "Z_CLOSE_20 below entry threshold", "left": "Z_CLOSE_20", "left_value": z_close, "operator": "<=", "right_param": "ENTRY_Z_THRESHOLD", "right_value": entry_threshold, "passed": bool(entry_z_pass)},
                    {"id": "volume_gate", "label": "Volume z-score confirms entry", "enabled": bool(enable_volume_gate), "left": "Z_VOLUME_20", "left_value": z_volume, "operator": ">=", "right_param": "MIN_VOLUME_Z", "right_value": min_volume_z, "passed": bool(volume_pass)},
                ],
            },
            "exit_long": {
                "passed": bool(exit_z_pass),
                "logic": "all",
                "items": [
                    {"id": "z_close_reverted", "label": "Z_CLOSE_20 reached exit threshold", "left": "Z_CLOSE_20", "left_value": z_close, "operator": ">=", "right_param": "EXIT_Z_THRESHOLD", "right_value": exit_threshold, "passed": bool(exit_z_pass)}
                ],
            },
        }

    def evaluate(self, df: pd.DataFrame) -> Tuple[Optional[str], dict[str, Any]]:
        if df is None or df.empty:
            return None, {"reason": "empty"}
        conditions = self.evaluate_conditions(df)
        current_values = conditions.get("current_values", {})
        meta: dict[str, Any] = {
            "reason": "condition_evaluation",
            "price": current_values.get("close"),
            "z_close": current_values.get("Z_CLOSE_20"),
            "z_volume": current_values.get("Z_VOLUME_20"),
            "conditions": conditions,
            "condition_spec": self.condition_spec(),
            "parameter_schema": self.parameter_schema(),
        }
        if conditions.get("entry_long", {}).get("passed"):
            return "BUY", {**meta, "reason": "entry_long_passed"}
        if conditions.get("exit_long", {}).get("passed"):
            meta["reason"] = "exit_long_passed_position_required"
            if self._bool_param("ENABLE_EXIT_SIGNAL_WITHOUT_POSITION"):
                return "SELL", meta
        return None, meta
