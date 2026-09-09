from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import p69_combination_capital_risk_r1 as p69


def regression(candidate: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    y = candidate.to_numpy(dtype=float)
    x = benchmark.to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(x)), x])
    alpha_m, beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ np.array([alpha_m, beta])
    active = y - x
    active_std = float(np.std(active, ddof=0))
    downside = x < 0
    upside = x >= 0
    return {
        "monthly_alpha": float(alpha_m),
        "annualized_alpha_linear": float(alpha_m * 12),
        "beta": float(beta),
        "residual_ann_vol": float(np.std(resid, ddof=0) * math.sqrt(12)),
        "active_ann_mean": float(np.mean(active) * 12),
        "tracking_error": float(active_std * math.sqrt(12)),
        "information_ratio": float((np.mean(active) * 12) / (active_std * math.sqrt(12))) if active_std else float("nan"),
        "monthly_hit_rate": float(np.mean(active > 0)),
        "up_capture_mean_ratio": float(np.mean(y[upside]) / np.mean(x[upside])) if upside.any() and np.mean(x[upside]) else float("nan"),
        "down_capture_mean_ratio": float(np.mean(y[downside]) / np.mean(x[downside])) if downside.any() and np.mean(x[downside]) else float("nan"),
        "correlation": float(np.corrcoef(y, x)[0, 1]),
    }


def main():
    fr, close = p69.frame()
    out = {
        "schema": "research.p71_combination_qqq_risk_adjusted_attribution_r1",
        "parents": ["P58", "P64"],
        "hypothesis": "P64's raw QQQ opportunity-cost deficit may partly reflect lower systematic equity beta rather than purely negative benchmark-adjusted alpha.",
        "scientific_contract": {
            "candidate": "fixed P64 50/50 P57+P52 combination",
            "costs_bps": [25, 50],
            "benchmarks": ["QQQ", "SPY", "fixed_matched_blend"],
            "tests": ["monthly OLS alpha/beta", "information ratio", "tracking error", "monthly active hit rate", "up/down capture", "correlation"],
            "no_parameter_weight_or_cadence_tuning": True
        },
        "source": {"provider": "Yahoo Finance via yfinance", "cross_panel_sha256": p69.base.source_hash(close)},
        "window": {"start": str(fr.index[0].date()), "end": str(fr.index[-1].date()), "months": int(len(fr))},
        "costs": {}
    }
    for bp in (25, 50):
        c = fr.gross - fr.turnover * bp / 10000
        out["costs"][str(bp)] = {
            "vs_qqq": regression(c, fr.qqq),
            "vs_spy": regression(c, fr.spy),
            "vs_matched": regression(c, fr.matched)
        }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p71_combination_qqq_risk_adjusted_attribution_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({bp: {b: {k: v for k, v in stats.items() if k in ("annualized_alpha_linear", "beta", "information_ratio", "monthly_hit_rate", "up_capture_mean_ratio", "down_capture_mean_ratio")} for b, stats in block.items()} for bp, block in out["costs"].items()}, sort_keys=True))


if __name__ == "__main__":
    main()
