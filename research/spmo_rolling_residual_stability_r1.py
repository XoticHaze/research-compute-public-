from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = ["SPMO", "SPY", "QQQ", "MTUM"]
START = "2015-10-01"
END = "2026-09-12"
ENDPOINT_COST = 0.0025
ROLLING_MONTHS = 36
OUT = Path("research/artifacts/spmo_rolling_residual_stability_r1.json")


def net_monthly(close: pd.DataFrame) -> pd.DataFrame:
    r = close.resample("ME").last().pct_change(fill_method=None).dropna()
    # Symmetric frozen implementation friction. Prices are already expense-net.
    for c in r.columns:
        if len(r[c].dropna()) >= 2:
            first = r[c].first_valid_index()
            last = r[c].last_valid_index()
            r.loc[first, c] -= ENDPOINT_COST
            r.loc[last, c] -= ENDPOINT_COST
    return r.dropna()


def ols_alpha(frame: pd.DataFrame) -> dict[str, object]:
    q = frame.dropna()
    if len(q) < 24:
        return {"months": int(len(q)), "annualized_alpha": None, "alpha_t": None, "betas": {}}
    y = q["SPMO"].to_numpy(float)
    X = np.column_stack([np.ones(len(q)), q[["SPY", "QQQ", "MTUM"]].to_numpy(float)])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    dof = len(y) - X.shape[1]
    sigma2 = float((resid @ resid) / dof)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se0 = float(np.sqrt(cov[0, 0]))
    alpha_m = float(coef[0])
    return {
        "months": int(len(q)),
        "annualized_alpha": alpha_m * 12.0,
        "alpha_t": alpha_m / se0 if se0 > 0 else None,
        "betas": {"SPY": float(coef[1]), "QQQ": float(coef[2]), "MTUM": float(coef[3])},
    }


def cagr(s: pd.Series) -> float | None:
    x = s.dropna().to_numpy(float)
    if len(x) < 12:
        return None
    w = float(np.prod(1.0 + x))
    if w <= 0:
        return None
    return w ** (12.0 / len(x)) - 1.0


def main() -> None:
    raw = yf.download(TICKERS, start=START, end=END, auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        raise SystemExit("SOURCE_FAILURE_EMPTY")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[TICKERS].dropna().astype(float)
    if len(close) < 500:
        raise SystemExit("SOURCE_FAILURE_INSUFFICIENT_COMMON_HISTORY")
    r = net_monthly(close)

    windows = {
        "full": ols_alpha(r),
        "pre2020": ols_alpha(r.loc[:"2019-12-31"]),
        "2020_plus": ols_alpha(r.loc["2020-01-01":]),
        "2023_plus": ols_alpha(r.loc["2023-01-01":]),
    }

    rolling = []
    for i in range(ROLLING_MONTHS - 1, len(r)):
        q = r.iloc[i - ROLLING_MONTHS + 1:i + 1]
        a = ols_alpha(q)
        rolling.append({
            "end": str(q.index[-1].date()),
            "annualized_alpha": a["annualized_alpha"],
            "alpha_t": a["alpha_t"],
        })
    valid = [x for x in rolling if x["annualized_alpha"] is not None]
    positive_fraction = float(np.mean([x["annualized_alpha"] > 0 for x in valid])) if valid else None
    worst_alpha = float(min(x["annualized_alpha"] for x in valid)) if valid else None
    median_alpha = float(np.median([x["annualized_alpha"] for x in valid])) if valid else None

    spmo_cagr = cagr(r["SPMO"])
    spy_cagr = cagr(r["SPY"])
    opportunity_cost_pp = None if spmo_cagr is None or spy_cagr is None else 100.0 * (spmo_cagr - spy_cagr)

    full_alpha = windows["full"]["annualized_alpha"]
    recent_alpha = windows["2023_plus"]["annualized_alpha"]
    passed = (
        full_alpha is not None and full_alpha > 0
        and recent_alpha is not None and recent_alpha > 0
        and positive_fraction is not None and positive_fraction >= 0.60
        and worst_alpha is not None and worst_alpha > -0.05
    )
    decision = "SPMO_ROLLING_RESIDUAL_STABILITY_SUPPORTED" if passed else "SPMO_ROLLING_RESIDUAL_STABILITY_NOT_SUPPORTED"

    result = {
        "schema": "research.spmo_rolling_residual_stability_r1.v1",
        "workload_id": "SPMO_ROLLING_RESIDUAL_STABILITY_R1",
        "parent": "CC-RF-MOMENTUM-CAUSAL-002",
        "claim": "SPMO retains positive implementation-specific alpha after fixed simultaneous SPY, QQQ, and MTUM attribution across chronology rather than only in full-sample regression.",
        "contract": {
            "symbols": TICKERS,
            "download_start": START,
            "download_end_exclusive": END,
            "endpoint_cost_bps_each": 25,
            "rolling_months": ROLLING_MONTHS,
            "factors": ["SPY", "QQQ", "MTUM"],
            "support_gate": "full annualized residual alpha > 0; 2023+ residual alpha > 0; >=60% of overlapping 36-month residual-alpha windows positive; worst rolling annualized residual alpha > -5%; no date/factor/horizon rescue",
            "parameter_search": False,
            "factor_search": False,
            "date_rescue": False,
        },
        "common_sample": {
            "months": int(len(r)),
            "first_month": str(r.index.min().date()),
            "last_month": str(r.index.max().date()),
        },
        "windows": windows,
        "rolling_36m": {
            "count": len(valid),
            "positive_fraction": positive_fraction,
            "median_annualized_alpha": median_alpha,
            "worst_annualized_alpha": worst_alpha,
            "series": valid,
        },
        "opportunity_cost": {
            "spmo_cagr": spmo_cagr,
            "spy_cagr": spy_cagr,
            "spmo_minus_spy_cagr_pp": opportunity_cost_pp,
        },
        "decision": decision,
        "scientific_consequence": (
            "Preserve SPMO as implementation-specific momentum survivor after a chronology-sensitive residual-attribution falsifier; continue orthogonal causal testing without product or parameter rescue."
            if passed else
            "Do not treat SPMO full-sample residual alpha as chronology-stable implementation alpha. Preserve prior matched-control evidence but reject this stronger stability claim without changing factors, dates, or rolling horizon."
        ),
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
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({
        "decision": decision,
        "months": len(r),
        "full_alpha_pct": None if full_alpha is None else round(full_alpha * 100, 3),
        "recent_alpha_pct": None if recent_alpha is None else round(recent_alpha * 100, 3),
        "rolling_positive_fraction": None if positive_fraction is None else round(positive_fraction, 3),
        "worst_rolling_alpha_pct": None if worst_alpha is None else round(worst_alpha * 100, 3),
        "spmo_minus_spy_cagr_pp": None if opportunity_cost_pp is None else round(opportunity_cost_pp, 3),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
