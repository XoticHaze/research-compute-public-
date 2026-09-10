import hashlib, json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ASSETS = ["XMMO", "MDY", "IJH", "SPY"]
WINDOWS = {"2006": "2006-01-01", "2010": "2010-01-01", "2015": "2015-01-01", "2020": "2020-01-01"}
PRIMARY = "MDY"
REFERENCE = ["IJH", "SPY"]
ENTRY_EXIT_COST_BPS = 10


def apply_roundtrip_cost(r: pd.Series) -> pd.Series:
    q = pd.Series(r).dropna().copy()
    f = ENTRY_EXIT_COST_BPS / 10000.0
    if len(q):
        q.iloc[0] -= f
        q.iloc[-1] -= f
    return q


def ols_alpha(y: pd.Series, x: pd.Series) -> dict:
    d = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    yy = d["y"].to_numpy(float)
    xx = d["x"].to_numpy(float)
    X = np.column_stack([np.ones(len(d)), xx])
    coef, *_ = np.linalg.lstsq(X, yy, rcond=None)
    resid = yy - X @ coef
    dof = max(len(d) - X.shape[1], 1)
    s2 = float(resid @ resid / dof)
    cov = s2 * np.linalg.pinv(X.T @ X)
    se_alpha = float(np.sqrt(max(cov[0, 0], 0.0)))
    alpha_m = float(coef[0])
    beta = float(coef[1])
    t = alpha_m / se_alpha if se_alpha > 0 else None
    ss_tot = float(((yy - yy.mean()) ** 2).sum())
    r2 = 1.0 - float((resid ** 2).sum()) / ss_tot if ss_tot > 0 else None
    return {
        "rows": int(len(d)),
        "alpha_monthly": alpha_m,
        "alpha_annualized_arithmetic": alpha_m * 12.0,
        "alpha_t_stat_iid": t,
        "beta": beta,
        "r2": r2,
    }


def evaluate_window(monthly: pd.DataFrame) -> dict:
    costed = {a: apply_roundtrip_cost(monthly[a]) for a in ASSETS}
    regressions = {b: ols_alpha(costed["XMMO"], costed[b]) for b in [PRIMARY] + REFERENCE}
    folds = []
    for i, idx in enumerate(np.array_split(np.arange(len(monthly)), 5), 1):
        q = monthly.iloc[idx]
        if len(q) < 6:
            continue
        primary = ols_alpha(apply_roundtrip_cost(q["XMMO"]), apply_roundtrip_cost(q[PRIMARY]))
        folds.append({
            "fold": i,
            "rows": int(len(q)),
            "mdy_alpha_annualized_arithmetic": primary["alpha_annualized_arithmetic"],
            "mdy_beta": primary["beta"],
        })
    return {
        "regressions": regressions,
        "positive_mdy_alpha_folds": sum(f["mdy_alpha_annualized_arithmetic"] > 0 for f in folds),
        "folds": folds,
    }


raw = yf.download(
    ASSETS,
    start="2005-01-01",
    end="2026-09-03",
    auto_adjust=True,
    progress=False,
    group_by="column",
    threads=False,
)
close = raw["Close"][ASSETS] if isinstance(raw.columns, pd.MultiIndex) else raw[ASSETS]
close = close.dropna(how="any").resample("ME").last()
returns = close.pct_change().dropna(how="any")
tests = {k: evaluate_window(returns.loc[pd.Timestamp(v):]) for k, v in WINDOWS.items()}
primary = tests["2010"]["regressions"][PRIMARY]

support = (
    all(tests[k]["regressions"][PRIMARY]["alpha_annualized_arithmetic"] > 0 for k in WINDOWS)
    and tests["2010"]["positive_mdy_alpha_folds"] >= 4
    and primary["alpha_t_stat_iid"] is not None
    and primary["alpha_t_stat_iid"] >= 1.5
)
decision = "P220_BETA_ADJUSTED_ALPHA_SUPPORT" if support else "P220_BETA_ADJUSTED_ALPHA_NOT_SUPPORTED"

out = {
    "schema": "research.p220_xmmo_beta_attribution_r1",
    "parent": "P220",
    "hypothesis": "P217/P219 XMMO matched-size excess survives fixed beta attribution to MDY rather than being explained by different systematic exposure.",
    "contract": {
        "candidate": "XMMO",
        "primary_factor": PRIMARY,
        "reference_factors": REFERENCE,
        "windows": WINDOWS,
        "chronological_folds": 5,
        "external_cost_bps_entry_exit": ENTRY_EXIT_COST_BPS,
        "regression": "monthly OLS candidate_return = alpha + beta * factor_return",
        "gate": "positive MDY-adjusted annualized alpha every window, >=4/5 positive chronological MDY-alpha folds from 2010, and 2010 MDY alpha t-stat >=1.5",
        "no_window_fund_factor_or_parameter_search": True,
    },
    "source": {
        "provider": "Yahoo Finance via yfinance; research-only",
        "rows": int(len(close)),
        "first": str(close.index[0]),
        "last": str(close.index[-1]),
        "panel_sha256": hashlib.sha256(close.to_csv().encode()).hexdigest(),
    },
    "tests": tests,
    "decision": decision,
    "limitations": [
        "IID OLS t-stat is descriptive rather than HAC-robust.",
        "Zero-risk-free regression is used to isolate matched-equity beta; this is attribution evidence, not a full factor model.",
    ],
    "boundaries": {"portfolio_ranking": False, "product_runtime": False, "broker": False, "live_trading": False},
}
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/p220_xmmo_beta_attribution_r1.json").write_text(json.dumps(out, sort_keys=True, indent=2))
print(json.dumps(out, sort_keys=True))
