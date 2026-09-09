from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import fixed_multifactor_cross_sectional_r1 as base

SYMBOLS = base.UNIVERSES["crossasset"]
FACTORS = ("mom6", "trend200", "low_vol6", "drawdown6")


def build(close: pd.DataFrame) -> pd.DataFrame:
    monthly = close.resample("ME").last()
    last = pd.Timestamp(close.index.max())
    if last.tzinfo is not None:
        last = last.tz_localize(None)
    monthly = monthly.loc[monthly.index <= last.normalize()].copy()
    daily_r = close.pct_change()
    vol6 = (daily_r.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)).resample("ME").last()
    trend200 = (close / close.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    dd6 = (close / close.rolling(126, min_periods=100).max() - 1).resample("ME").last()
    mom6 = monthly.pct_change(6)

    prev_active = {s: 0.0 for s in SYMBOLS}
    prev_hybrid = {s: 0.0 for s in SYMBOLS}
    rows = []
    for month in monthly.index:
        block = pd.DataFrame(index=list(SYMBOLS))
        block["mom6"] = mom6.loc[month, list(SYMBOLS)]
        block["trend200"] = trend200.loc[month, list(SYMBOLS)]
        block["low_vol6"] = -vol6.loc[month, list(SYMBOLS)]
        block["drawdown6"] = dd6.loc[month, list(SYMBOLS)]
        if block.isna().any().any():
            continue
        score = block.rank(axis=0, pct=True, method="average").mean(axis=1)
        chosen = score.sort_values(ascending=False).head(2).index.tolist()
        loc = monthly.index.get_loc(month)
        if not isinstance(loc, (int, np.integer)) or loc + 1 >= len(monthly):
            continue
        nxt = monthly.index[loc + 1]
        realized = monthly.loc[nxt, list(SYMBOLS)] / monthly.loc[month, list(SYMBOLS)] - 1
        if realized.isna().any():
            continue
        risk_on = float(mom6.at[month, "SPY"]) > 0.0
        active_w = {s: (0.5 if s in chosen else 0.0) for s in SYMBOLS}
        hybrid_w = active_w if risk_on else {s: 1.0 / len(SYMBOLS) for s in SYMBOLS}
        active_turnover = 0.5 * sum(abs(active_w[s] - prev_active[s]) for s in SYMBOLS)
        hybrid_turnover = 0.5 * sum(abs(hybrid_w[s] - prev_hybrid[s]) for s in SYMBOLS)
        active_gross = sum(active_w[s] * float(realized[s]) for s in SYMBOLS)
        hybrid_gross = sum(hybrid_w[s] * float(realized[s]) for s in SYMBOLS)
        ew = float(realized.mean())
        spy = float(monthly.at[nxt, "SPY"] / monthly.at[month, "SPY"] - 1)
        qqq = float(monthly.at[nxt, "QQQ"] / monthly.at[month, "QQQ"] - 1)
        rows.append({
            "date": nxt,
            "risk_on": risk_on,
            "active_gross": active_gross,
            "hybrid_gross": hybrid_gross,
            "active_turnover": active_turnover,
            "hybrid_turnover": hybrid_turnover,
            "ew": ew,
            "spy": spy,
            "qqq": qqq,
        })
        prev_active, prev_hybrid = active_w, hybrid_w
    return pd.DataFrame(rows).set_index("date")


def score(frame: pd.DataFrame, bps: int) -> dict:
    active = frame.active_gross - frame.active_turnover * (bps / 10000)
    hybrid = frame.hybrid_gross - frame.hybrid_turnover * (bps / 10000)
    ew = frame.ew
    hm, am, em = base.metrics(hybrid), base.metrics(active), base.metrics(ew)
    pos_ew, folds_ew = base.fold_count(hybrid, ew)
    pos_active, folds_active = base.fold_count(hybrid, active)
    return {
        "hybrid": hm,
        "original_active": am,
        "matched_equal_weight": em,
        "spy": base.metrics(frame.spy),
        "qqq": base.metrics(frame.qqq),
        "excess_cagr_vs_equal_weight": hm["cagr"] - em["cagr"],
        "excess_cagr_vs_original_active": hm["cagr"] - am["cagr"],
        "positive_folds_vs_equal_weight": pos_ew,
        "positive_folds_vs_original_active": pos_active,
        "folds_vs_equal_weight": folds_ew,
        "folds_vs_original_active": folds_active,
    }


def main() -> None:
    close = base.load(SYMBOLS)
    frame = build(close)
    out = {
        "schema": "research.p81_p46_riskoff_deactivation_r1",
        "parent_ids": ["P46", "P81"],
        "scientific_contract": {
            "primary": "Preserve P46 four-factor top-2 selection only when prior SPY six-month return is positive; during prior-SPY six-month <=0 months use same-universe equal weight.",
            "comparators": ["original_P46_active", "same_universe_equal_weight", "SPY", "QQQ"],
            "costs_bps": [25, 50],
            "regime_threshold": "prior SPY 6m return > 0; frozen from prior attribution definition",
            "no_parameter_tuning": True,
            "complete_months_only": True,
        },
        "source": {"provider": "Yahoo Finance via yfinance", "normalized_price_panel_sha256": base.source_hash(close)},
        "window": {"start": str(frame.index.min().date()), "end": str(frame.index.max().date()), "months": int(len(frame))},
        "risk_on_months": int(frame.risk_on.sum()),
        "risk_off_months": int((~frame.risk_on).sum()),
        "mean_annual_turnover": {
            "hybrid": float(frame.hybrid_turnover.mean() * 12),
            "original_active": float(frame.active_turnover.mean() * 12),
        },
        "costs": {"25": score(frame, 25), "50": score(frame, 50)},
    }
    p25, p50 = out["costs"]["25"], out["costs"]["50"]
    improved = (
        p25["excess_cagr_vs_equal_weight"] > 0
        and p25["excess_cagr_vs_original_active"] > 0
        and p25["positive_folds_vs_equal_weight"] >= 3
        and p50["excess_cagr_vs_equal_weight"] > 0
        and p50["excess_cagr_vs_original_active"] > 0
    )
    out["decision"] = "SUPPORTED_RISKOFF_DEACTIVATION_REQUIRES_HOLDOUT" if improved else "NOT_SUPPORTED_KEEP_ORIGINAL_OR_PARK"
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p81_p46_riskoff_deactivation_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({
        "decision": out["decision"],
        "window": out["window"],
        "25": {
            "excess_vs_ew": p25["excess_cagr_vs_equal_weight"],
            "excess_vs_original": p25["excess_cagr_vs_original_active"],
            "folds_vs_ew": p25["positive_folds_vs_equal_weight"],
            "folds_vs_original": p25["positive_folds_vs_original_active"],
        },
        "50": {
            "excess_vs_ew": p50["excess_cagr_vs_equal_weight"],
            "excess_vs_original": p50["excess_cagr_vs_original_active"],
        },
        "turnover": out["mean_annual_turnover"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
