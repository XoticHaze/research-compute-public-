from .base import BaseStrategy
from .python.breakout import BreakoutStrategy
from .python.crw_score_modular import CRWScoreModularStrategy
from .python.dual_thrust import DualThrustStrategy
from .python.dynamic_breakout_ii import DynamicBreakoutIIStrategy
from .python.ma_crossover import MACrossoverStrategy
from .python.mean_reversion import MeanReversionStrategy
from .python.mean_reversion_zscore import MeanReversionZScoreStrategy
from .python.crw_score_multi_mode import CrwScoreMultiModeStrategy
from .python.rsi_bb import RSIBBStrategy

REGISTRY = {
    "crw_score_multi_mode": CrwScoreMultiModeStrategy,
    "crw_score_modular": CRWScoreModularStrategy,
    "rsi_bb": RSIBBStrategy,
    "ma_crossover": MACrossoverStrategy,
    "breakout": BreakoutStrategy,
    "mean_reversion": MeanReversionStrategy,
    "mean_reversion_zscore": MeanReversionZScoreStrategy,
    "dual_thrust": DualThrustStrategy,
    "dynamic_breakout_ii": DynamicBreakoutIIStrategy,
}

PRIMARY_STRATEGY_ID = "crw_score_multi_mode"
# Keep the proven multi-mode runtime and the isolated modular composition adapter
# as distinct registry identities.  Only the historical shorthand is aliased.
STRATEGY_ALIASES = {
    "crw_modular": "crw_score_modular",
}
LEGACY_STRATEGY_LABELS = {
    "mean_reversion_zscore": "Legacy: mean_reversion_zscore",
}


def canonical_strategy_id(name: str) -> str:
    raw = str(name or "").strip()
    return STRATEGY_ALIASES.get(raw, raw)


def create(name: str, **kwargs) -> BaseStrategy:
    cls = REGISTRY.get(canonical_strategy_id(name))
    if not cls:
        raise ValueError(f"Unknown strategy: {name}")
    return cls(**kwargs)
