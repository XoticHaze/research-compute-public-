from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = ["GDX", "RING", "GLD", "SPY"]
MINERS = ["GDX", "RING"]
START = "2012-01-01"
END = "2026-09-12"  # exclusive; preserve parent R1 completed-session boundary
ENDPOINT_COST = 0.0025
HAC_LAGS = 5
ONE_SIDED_95_T = 1.645
OUT = Path("research/artifacts/gold_miner_gld_spy_attribution_r1.json")

WINDOWS = {
    "2013+": ("2013-01-01", None),
    "2016+": ("2016-01-01", None),
    "2020+": ("2020-01-01", None),
    "2022+": ("2022-01-01", None),
}
BLOCKS = {
    "2013_2015": ("2013-01-01", "2015-12-31"),
    "2016_2018": ("2016-01-01", "2018-12-31"),
    "2019_2021": ("2019-01-01", "2021-12-31"),
    "2022_2024": ("2022-01-01", "2024-12-31"),
    "2025_plus": ("2025-01-01", None),
}


def hac_ols(y: np.ndarray, factors: np.ndarray, lags: int = HAC_LAGS) -> dict[str, float | int | None]:
    n = len(y)
    if n < 252:
        return {"days": int(n)}
    x = np.column_stack([np.ones(n), factors])
    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ y
    resid = y - x @ beta
    k = x.shape[1]
    meat = np.zeros((k, k), dtype=float)
    for t in range(n):
        z = x[t] * resid[t]
        meat += np.outer(z, z)
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1.0 - lag / (lags + 1.0)
        cross = np.zeros((k, k), dtype=float)
        for t in range(lag, n):
            cross += np.outer(x[t] * resid[t], x[t - lag] * resid[t - lag])
        meat += weight * (cross + cross.T)
    cov = xtx_inv @ meat @ xtx_inv
    alpha_se = math.sqrt(max(float(cov[0, 0]), 0.0))
    alpha = float(beta[0])
    t_alpha = alpha / alpha_se if alpha_se > 0 else None
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    ss_res = float(np.sum(resid**2))
    r2 = None if ss_tot <= 0 else 1.0 - ss_res / ss_tot
    residual_return = y - float(beta[1]) * factors[:, 0] - float(beta[2]) * factors[:, 1]
    rr = residual_return.copy()
    rr[0] -= ENDPOINT_COST
    rr[-1] -= ENDPOINT_COST
    wealth = np.cumprod(1.0 + rr)
    years = n / 252.0
    residual_cagr = None if wealth[-1] <= 0 else float(wealth[-1] ** (1.0 / years) - 1.0)
    return {
        "days": int(n),
        "alpha_daily": alpha,
        "alpha_annualized_pp": 100.0 * 252.0 * alpha,
        "alpha_hac_se_daily": alpha_se,
        "alpha_hac_t": t_alpha,
        "alpha_one_sided_95_positive": bool(t_alpha is not None and t_alpha >= ONE_SIDED_95_T),
        "beta_gld": float(beta[1]),
        "beta_spy": float(beta[2]),
        "r2": r2,
        "residual_cagr_after_endpoint_cost": residual_cagr,
    }


def evaluate_period(px: pd.DataFrame, start: str, end: str | None) -> dict[str, object]:
    q = px.loc[start:end, TICKERS].dropna()
    r = q.pct_change(fill_method=None).dropna()
    factors = r[["GLD", "SPY"]].to_numpy(float)
    return {miner: hac_ols(r[miner].to_numpy(float), factors) for miner in MINERS}


def pack(px: pd.DataFrame, periods: dict[str, tuple[str, str | None]]) -> dict[str, object]:
    return {name: evaluate_period(px, start, end) for name, (start, end) in periods.items()}


def main() -> int:
    raw = yf.download(TICKERS, start=START, end=END, auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        raise SystemExit("SOURCE_FAILURE_EMPTY")
    px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    px = px[TICKERS].dropna(how="all")
    windows = pack(px, WINDOWS)
    blocks = pack(px, BLOCKS)

    positive_windows = {
        m: sum(float(windows[k][m].get("alpha_annualized_pp", -999.0)) > 0 for k in WINDOWS)
        for m in MINERS
    }
    positive_blocks = {
        m: sum(float(blocks[k][m].get("alpha_annualized_pp", -999.0)) > 0 for k in BLOCKS)
        for m in MINERS
    }
    persistence = {
        m: bool(
            positive_windows[m] >= 3
            and positive_blocks[m] >= 3
            and float(windows["2022+"][m].get("alpha_annualized_pp", -999.0)) > 0
        )
        for m in MINERS
    }
    long_inference = {
        m: bool(windows["2013+"][m].get("alpha_one_sided_95_positive") is True)
        for m in MINERS
    }

    if all(persistence.values()) and all(long_inference.values()):
        decision = "GOLD_MINER_INDEPENDENT_ALPHA_SUPPORTED_AFTER_GLD_SPY_ATTRIBUTION"
    elif all(persistence.values()):
        decision = "GOLD_MINER_RESIDUAL_PERSISTS_BUT_LONG_HORIZON_INFERENCE_WEAK"
    else:
        decision = "GOLD_MINER_SEAM_EXPLAINED_OR_NOT_PERSISTENT_AFTER_GLD_SPY_ATTRIBUTION"

    result = {
        "schema": "research.gold_miner_gld_spy_attribution_r1.v1",
        "workload_id": "GOLD_MINER_GLD_SPY_ATTRIBUTION_R1",
        "parent": "MR_GOLD_MINERS_20260911_R1",
        "hypothesis": "The predeclared GDX/RING producer-over-metal seam retains positive intercept alpha after fixed GLD and SPY daily-return attribution.",
        "contract": {
            "candidates": MINERS,
            "fixed_factors": ["GLD", "SPY"],
            "parent_endpoint_cost_bps_each_side": 25,
            "regression": "daily_simple_return_ols_with_intercept",
            "hac_lags": HAC_LAGS,
            "long_horizon_inference_gate": "one_sided_95pct_t_ge_1.645_on_2013plus",
            "windows": WINDOWS,
            "blocks": BLOCKS,
            "factor_search": False,
            "date_search": False,
            "product_search": False,
            "cost_search": False,
        },
        "windows": windows,
        "blocks": blocks,
        "positive_alpha_windows": positive_windows,
        "positive_alpha_blocks": positive_blocks,
        "persistence_pass": persistence,
        "long_horizon_inference_pass": long_inference,
        "decision_rule": "Independent-alpha support requires each of GDX and RING to have positive GLD+SPY intercept alpha in >=3/4 fixed windows and >=3/5 fixed chronology blocks, positive alpha from 2022+, and a positive one-sided 95% HAC intercept test in 2013+. Persistence without the long-horizon inference gate is retained as scoped residual evidence, not independent-alpha promotion. No post-result rescue.",
        "decision": decision,
        "boundaries": {
            "scientific_authority": True,
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "decision": decision,
        "positive_alpha_windows": positive_windows,
        "positive_alpha_blocks": positive_blocks,
        "long_horizon_inference_pass": long_inference,
        "2013plus_alpha_pp": {m: round(float(windows["2013+"][m].get("alpha_annualized_pp", -999)), 3) for m in MINERS},
        "2022plus_alpha_pp": {m: round(float(windows["2022+"][m].get("alpha_annualized_pp", -999)), 3) for m in MINERS},
        "2013plus_t": {m: round(float(windows["2013+"][m].get("alpha_hac_t") or 0), 3) for m in MINERS},
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
