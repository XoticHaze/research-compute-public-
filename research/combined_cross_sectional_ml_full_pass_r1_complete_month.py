from __future__ import annotations

import pandas as pd

import combined_cross_sectional_ml_full_pass_r1 as base


_original_feature_panel = base._feature_panel


def _complete_month_feature_panel(close, symbols):
    panel, monthly = _original_feature_panel(close, symbols)
    last_observation = pd.Timestamp(close.index.max())
    if last_observation.tzinfo is not None:
        last_observation = last_observation.tz_localize(None)
    complete_monthly = monthly.loc[monthly.index <= last_observation.normalize()].copy()
    if len(complete_monthly) < 2:
        raise RuntimeError("insufficient_complete_months_after_guard")

    panel = panel[panel["month"].isin(complete_monthly.index)].copy()
    next_returns = complete_monthly.pct_change().shift(-1)
    universe_next_mean = next_returns.loc[:, list(symbols)].mean(axis=1)
    panel["target"] = [
        next_returns.at[row.month, row.symbol] - universe_next_mean.at[row.month]
        if row.month in next_returns.index and row.symbol in next_returns.columns
        else float("nan")
        for row in panel.itertuples()
    ]
    return panel, complete_monthly


base._feature_panel = _complete_month_feature_panel

if __name__ == "__main__":
    base.main()
