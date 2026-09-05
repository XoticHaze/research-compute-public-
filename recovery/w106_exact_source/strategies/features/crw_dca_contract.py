"""Canonical CRW DCA tier/reference contract.

This module is intentionally calculation-only. It does not submit orders, mutate
runtime state, or own broker routing. It normalizes the ordered DCA ladder used
by TradingView parity, Python feature evaluation, backtests, and Builder/runtime
StrategySpec plumbing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

CANONICAL_TIER_KEY = "DCA_TIER_DRAWDOWNS_PCT"
TIER_KEY_ALIASES = (
    CANONICAL_TIER_KEY,
    "dca_tier_drawdowns_pct",
    "dcaTierDrawdownsPct",
    "dca_tier_drawdowns",
    "dcaTierDrawdowns",
    "dcaTierDrawdownsPctCsv",
)

REFERENCE_MODE_TV_SIGNAL_CLOSE = "tv_signal_close"
REFERENCE_MODE_SIMULATED_LAST_FILL = "simulated_last_fill"
REFERENCE_MODE_POSITION_AVERAGE_COST = "position_average_cost"
REFERENCE_MODES = {
    REFERENCE_MODE_TV_SIGNAL_CLOSE,
    REFERENCE_MODE_SIMULATED_LAST_FILL,
    REFERENCE_MODE_POSITION_AVERAGE_COST,
}

TIER_SEMANTICS_CORRECTED = "corrected_tier_order"
TIER_SEMANTICS_LEGACY_V0_2 = "legacy_pine_v0_2"


def _value(config: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in config:
            return config.get(key)
        upper = key.upper()
        if upper in config:
            return config.get(upper)
        lower = key.lower()
        if lower in config:
            return config.get(lower)
    return default


def _float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:  # NaN
        return None
    return out


def _parse_pct_list(raw: Any) -> list[float]:
    values: Sequence[Any]
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                decoded = json.loads(text)
                values = decoded if isinstance(decoded, list) else []
            except Exception:
                values = [part.strip() for part in text.strip("[]").split(",")]
        else:
            values = [part.strip() for part in text.split(",")]
    elif isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = [raw]

    out: list[float] = []
    for item in values:
        number = _float(item)
        if number is None or number < 0:
            continue
        out.append(float(number))
    return out


def configured_max_adds(config: Mapping[str, Any], default: int = 0) -> int:
    raw = _value(
        config,
        "DCA_MAX_ADDS",
        "max_dca_adds",
        "dca_max_adds",
        "max_dca_count",
        default=None,
    )
    number = _float(raw)
    if number is not None:
        return max(0, int(number))

    max_buys = _float(
        _value(
            config,
            "dcaMaxBuys",
            "dca_max_buys",
            "max_buys_before_sell",
            default=None,
        )
    )
    if max_buys is not None:
        return max(0, int(max_buys) - 1)
    return max(0, int(default))


def _legacy_tier_pct(config: Mapping[str, Any], tier_number: int) -> float:
    raw = _value(
        config,
        f"dcaDrawdown{tier_number}",
        f"dca_drawdown_{tier_number}",
        f"drawdown_for_buy_{tier_number}",
        f"drawdown_for_buy_{tier_number}_pct",
        default=None,
    )
    number = _float(raw)
    if number is None:
        return float(tier_number)

    # Compatibility with the existing parity/replay convention: old Pine-like
    # values can arrive as fractions (0.01 == 1%) while operator presets have
    # also historically stored percent points (1 == 1%).
    if 0 <= number <= 0.5:
        return float(number * 100.0)
    return float(number)


@dataclass(frozen=True)
class DcaTierContract:
    drawdowns_pct: tuple[float, ...]
    explicit_ordered_list: bool
    max_adds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "drawdowns_pct": list(self.drawdowns_pct),
            "explicit_ordered_list": self.explicit_ordered_list,
            "max_adds": self.max_adds,
            "count_source": "ordered_tier_list" if self.explicit_ordered_list else "compatibility_max_adds",
        }


@dataclass(frozen=True)
class DcaTierSelection:
    semantics: str
    completed_dca_count: int
    buy_counter: int
    tier_index: int
    tier_number: int
    drawdown_pct: float | None
    drawdown_fraction: float | None
    available: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "semantics": self.semantics,
            "completed_dca_count": self.completed_dca_count,
            "buy_counter": self.buy_counter,
            "tier_index": self.tier_index,
            "tier_number": self.tier_number,
            "drawdown_pct": self.drawdown_pct,
            "drawdown_fraction": self.drawdown_fraction,
            "available": self.available,
        }


def normalize_dca_tier_contract(
    config: Mapping[str, Any],
    *,
    default_max_adds: int = 0,
) -> DcaTierContract:
    explicit_raw = None
    for key in TIER_KEY_ALIASES:
        explicit_raw = _value(config, key, default=None)
        if explicit_raw is not None:
            break

    explicit = explicit_raw is not None
    if explicit:
        values = _parse_pct_list(explicit_raw)
        return DcaTierContract(tuple(values), True, len(values))

    max_adds = configured_max_adds(config, default=default_max_adds)
    values = [_legacy_tier_pct(config, tier) for tier in range(1, max_adds + 1)]
    return DcaTierContract(tuple(values), False, max_adds)


def select_next_dca_tier(
    contract: DcaTierContract,
    *,
    dca_count: int | None = None,
    buy_counter: int | None = None,
    semantics: str = TIER_SEMANTICS_CORRECTED,
) -> DcaTierSelection:
    safe_buy_counter = max(0, int(buy_counter or 0))
    safe_dca_count = (
        max(0, int(dca_count))
        if dca_count is not None
        else max(0, safe_buy_counter - 1)
    )

    if semantics == TIER_SEMANTICS_LEGACY_V0_2:
        # Original V0.2 used getDcaDrawdown(buyCounter + 1). With buyCounter=1
        # after the initial entry, the first DCA consumes the second tier.
        tier_index = safe_buy_counter
    else:
        # Corrected modular intent: ordered_tiers[0] is DCA1, [1] is DCA2, etc.
        tier_index = safe_dca_count
        semantics = TIER_SEMANTICS_CORRECTED

    available = 0 <= tier_index < len(contract.drawdowns_pct)
    drawdown_pct = float(contract.drawdowns_pct[tier_index]) if available else None
    drawdown_fraction = drawdown_pct / 100.0 if drawdown_pct is not None else None

    return DcaTierSelection(
        semantics=semantics,
        completed_dca_count=safe_dca_count,
        buy_counter=safe_buy_counter,
        tier_index=tier_index,
        tier_number=tier_index + 1,
        drawdown_pct=drawdown_pct,
        drawdown_fraction=drawdown_fraction,
        available=available,
    )


def normalize_reference_model(value: Any, default: str = REFERENCE_MODE_TV_SIGNAL_CLOSE) -> str:
    text = str(value or default).strip().lower().replace(" ", "_")
    aliases = {
        "tv": REFERENCE_MODE_TV_SIGNAL_CLOSE,
        "tv_close": REFERENCE_MODE_TV_SIGNAL_CLOSE,
        "signal_close": REFERENCE_MODE_TV_SIGNAL_CLOSE,
        "last_fill": REFERENCE_MODE_SIMULATED_LAST_FILL,
        "simulated_fill": REFERENCE_MODE_SIMULATED_LAST_FILL,
        "average_cost": REFERENCE_MODE_POSITION_AVERAGE_COST,
        "avg_cost": REFERENCE_MODE_POSITION_AVERAGE_COST,
    }
    text = aliases.get(text, text)
    return text if text in REFERENCE_MODES else default
