"""CRW strategy-to-feature DCA config bridge.

Keeps StrategySpec/runtime aliases compatible with the canonical CRW feature
builder without manufacturing an explicit tier ladder. An absent ordered ladder
must remain absent so ``DCA_MAX_ADDS`` can drive compatibility tier resolution;
an explicitly supplied empty ladder remains an intentional zero-add contract.

This module is calculation-only. It does not submit orders or mutate runtime.
"""
from __future__ import annotations

from typing import Any, Mapping

from .crw_dca_contract import TIER_KEY_ALIASES


def build_dca_feature_config(
    config: Mapping[str, Any],
    *,
    enabled: bool,
    max_adds: int,
    max_contracts: int,
    trigger_mode: str,
    reference_model: str,
) -> dict[str, Any]:
    """Return feature-builder config without inventing an explicit tier list."""
    out = dict(config or {})
    out.setdefault("enableDCA", bool(enabled))
    out.setdefault("DCA_MAX_ADDS", int(max_adds))
    out.setdefault("DCA_MAX_CONTRACTS", int(max_contracts))
    out.setdefault("dcaTriggerMode", str(trigger_mode))
    out.setdefault("DCA_REFERENCE_MODEL", str(reference_model))

    # Do not default DCA_TIER_DRAWDOWNS_PCT to []. normalize_dca_tier_contract()
    # defines any present tier key, including an empty list, as an explicit
    # ordered ladder whose length is the add capacity. Preserving absence here
    # lets max_dca_adds/DCA_MAX_ADDS compatibility resolve the intended ladder.
    explicit_tier_key = next((key for key in TIER_KEY_ALIASES if key in out), None)
    if explicit_tier_key is not None and explicit_tier_key != "DCA_TIER_DRAWDOWNS_PCT":
        out.setdefault("DCA_TIER_DRAWDOWNS_PCT", out[explicit_tier_key])
    return out
