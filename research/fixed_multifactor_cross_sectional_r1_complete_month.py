from __future__ import annotations

import pandas as pd

import fixed_multifactor_cross_sectional_r1 as base

_original_features = base.features


def _complete_month_features(close, symbols):
    panel, monthly = _original_features(close, symbols)
    last_observation = pd.Timestamp(close.index.max())
    if last_observation.tzinfo is not None:
        last_observation = last_observation.tz_localize(None)
    monthly = monthly.loc[monthly.index <= last_observation.normalize()].copy()
    if len(monthly) < 2:
        raise RuntimeError("insufficient_complete_months_after_guard")
    panel = panel[panel["month"].isin(monthly.index)].copy()
    return panel, monthly


base.features = _complete_month_features

if __name__ == "__main__":
    base.main()
