from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

START = "2005-01-01"
ASSETS = ("SPY", "QQQ", "TLT", "GLD", "DBC", "SOXX", "XBI", "XHB", "KRE", "ITA", "IGV", "IYT", "XRT", "XOP", "IHI")
FEATURES = ("mom6", "trend200", "low_vol6", "drawdown6")
TOP_K = 3
RIDGE_LAMBDA = 1.0
MIN_TRAIN_MONTHS = 60
COSTS_BPS = (25, 50)


def source_hash(close: pd.DataFrame) -> str:
    return hashlib.sha256(close.reset_index().to_csv(index=False, float_format="%.10g").encode()).hexdigest()


def load() -> pd.DataFrame:
    data = yf.download(list(ASSETS), start=START, auto_adjust=True, progress=False, threads=False)
    if data.empty:
        raise RuntimeError("empty_download")
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame()
    missing = [s for s in ASSETS if s not in close.columns]
    if missing:
        raise RuntimeError(f"missing:{missing}")
    return close.loc[:, list(ASSETS)].astype(float)


def build_months(close: pd.DataFrame):
    monthly = close.resample("ME").last()
    daily_r = close.pct_change(fill_method=None)
    vol6 = (daily_r.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)).resample("ME").last()
    trend200 = (close / close.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    dd6 = (close / close.rolling(126, min_periods=100).max() - 1).resample("ME").last()
    mom6 = monthly.pct_change(6)
    feature_map = {}
    target_map = {}
    for i, dt in enumerate(monthly.index[:-1]):
        nxt = monthly.index[i + 1]
        raw = pd.DataFrame(index=ASSETS)
        raw["mom6"] = mom6.loc[dt, list(ASSETS)]
        raw["trend200"] = trend200.loc[dt, list(ASSETS)]
        raw["low_vol6"] = -vol6.loc[dt, list(ASSETS)]
        raw["drawdown6"] = dd6.loc[dt, list(ASSETS)]
        nxt_ret = monthly.loc[nxt, list(ASSETS)] / monthly.loc[dt, list(ASSETS)] - 1
        if raw.isna().any().any() or nxt_ret.isna().any():
            continue
        ranks = raw.rank(axis=0, pct=True, method="average")
        feature_map[dt] = ranks.astype(float)
        target_map[dt] = nxt_ret.astype(float)
    return monthly, feature_map, target_map


def ridge_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x1 = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(x1.shape[1]) * RIDGE_LAMBDA
    penalty[0, 0] = 0.0
    return np.linalg.solve(x1.T @ x1 + penalty, x1.T @ y)


def metric(r: pd.Series) -> dict[str, float]:
    r = pd.Series(r, dtype=float).dropna()
    eq = (1 + r).cumprod()
    years = len(r) / 12
    cagr = float(eq.iloc[-1] ** (1 / years) - 1)
    ann_mean = float(r.mean() * 12)
    vol = float(r.std(ddof=0) * math.sqrt(12))
    sharpe = ann_mean / vol if vol else float("nan")
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    return {"cagr": cagr, "annualized_vol": vol, "sharpe_rf0": sharpe, "max_drawdown_monthly": mdd, "calmar": cagr / abs(mdd) if mdd < 0 else float("nan")}


def fold_count(c: pd.Series, b: pd.Series):
    folds = []
    for fold, idx in enumerate(np.array_split(np.arange(len(c)), 5), 1):
        cm, bm = metric(c.iloc[idx]), metric(b.iloc[idx])
        folds.append({"fold": fold, "candidate_cagr": cm["cagr"], "baseline_cagr": bm["cagr"], "excess_cagr": cm["cagr"] - bm["cagr"]})
    return sum(x["excess_cagr"] > 0 for x in folds), folds


def main():
    close = load()
    monthly, fmap, tmap = build_months(close)
    months = sorted(fmap)
    if len(months) <= MIN_TRAIN_MONTHS + 24:
        raise RuntimeError(f"insufficient_months:{len(months)}")

    previous_learned = {s: 0.0 for s in ASSETS}
    previous_fixed = {s: 0.0 for s in ASSETS}
    recs = []
    coef_history = []

    for j in range(MIN_TRAIN_MONTHS, len(months)):
        dt = months[j]
        train_months = months[:j]
        xs, ys = [], []
        for tm in train_months:
            xblock = fmap[tm].loc[:, list(FEATURES)].to_numpy()
            yblock = tmap[tm].to_numpy()
            yblock = yblock - yblock.mean()
            xs.append(xblock)
            ys.append(yblock)
        beta = ridge_fit(np.vstack(xs), np.concatenate(ys))
        xcur = fmap[dt].loc[:, list(FEATURES)].to_numpy()
        pred = beta[0] + xcur @ beta[1:]
        learned_order = [ASSETS[i] for i in np.argsort(-pred)[:TOP_K]]
        fixed_score = fmap[dt].loc[:, list(FEATURES)].mean(axis=1)
        fixed_order = fixed_score.sort_values(ascending=False, kind="stable").head(TOP_K).index.tolist()
        realized = tmap[dt]

        wl = {s: (1 / TOP_K if s in learned_order else 0.0) for s in ASSETS}
        wf = {s: (1 / TOP_K if s in fixed_order else 0.0) for s in ASSETS}
        turn_l = 0.5 * sum(abs(wl[s] - previous_learned[s]) for s in ASSETS)
        turn_f = 0.5 * sum(abs(wf[s] - previous_fixed[s]) for s in ASSETS)
        ret_l = sum(wl[s] * float(realized[s]) for s in ASSETS)
        ret_f = sum(wf[s] * float(realized[s]) for s in ASSETS)
        ew = float(realized.mean())
        qqq = float(realized["QQQ"])
        spy = float(realized["SPY"])
        recs.append({"feature_month": str(pd.Timestamp(dt).date()), "gross": ret_l, "fixed_gross": ret_f, "ew": ew, "qqq": qqq, "spy": spy, "turnover": turn_l, "fixed_turnover": turn_f, "learned": learned_order, "fixed": fixed_order})
        coef_history.append({"month": str(pd.Timestamp(dt).date()), "intercept": float(beta[0]), **{f: float(beta[i + 1]) for i, f in enumerate(FEATURES)}})
        previous_learned, previous_fixed = wl, wf

    fr = pd.DataFrame(recs)
    result = {
        "schema": "research.p70_expanding_ridge_cross_universe_r1",
        "hypothesis": "A strictly expanding, prior-only ridge model can learn cross-sectional factor weights that improve after-cost fund selection over the same-universe fixed equal-factor composite and equal weight.",
        "scientific_contract": {
            "assets": list(ASSETS), "features": list(FEATURES), "top_k": TOP_K,
            "ridge_lambda": RIDGE_LAMBDA, "minimum_training_months": MIN_TRAIN_MONTHS,
            "training": "expanding pooled cross-section; each target is next-month asset return demeaned by that month's universe mean; only target months known before each prediction are used",
            "costs_bps": list(COSTS_BPS), "no_hyperparameter_search": True,
            "comparators": ["same_universe_fixed_equal_factor_top3", "same_universe_equal_weight", "QQQ", "SPY"]
        },
        "source": {"provider": "Yahoo Finance via yfinance", "normalized_price_panel_sha256": source_hash(close)},
        "oos_window": {"start": fr.iloc[0].feature_month, "end": fr.iloc[-1].feature_month, "months": int(len(fr))},
        "mean_annual_turnover": float(fr.turnover.mean() * 12),
        "fixed_mean_annual_turnover": float(fr.fixed_turnover.mean() * 12),
        "final_coefficients": coef_history[-1],
        "costs": {}
    }
    for bp in COSTS_BPS:
        c = fr.gross - fr.turnover * bp / 10000
        fixed = fr.fixed_gross - fr.fixed_turnover * bp / 10000
        ew, qqq, spy = fr.ew, fr.qqq, fr.spy
        cm, fm, em, qm, sm = map(metric, (c, fixed, ew, qqq, spy))
        pos_fixed, folds_fixed = fold_count(c, fixed)
        pos_ew, folds_ew = fold_count(c, ew)
        result["costs"][str(bp)] = {
            "candidate": cm, "fixed_composite": fm, "equal_weight": em, "qqq": qm, "spy": sm,
            "excess_cagr_vs_fixed": cm["cagr"] - fm["cagr"],
            "excess_cagr_vs_equal_weight": cm["cagr"] - em["cagr"],
            "excess_cagr_vs_qqq": cm["cagr"] - qm["cagr"],
            "excess_cagr_vs_spy": cm["cagr"] - sm["cagr"],
            "positive_folds_vs_fixed": int(pos_fixed), "folds_vs_fixed": folds_fixed,
            "positive_folds_vs_equal_weight": int(pos_ew), "folds_vs_equal_weight": folds_ew
        }
    p, s = result["costs"]["25"], result["costs"]["50"]
    supported = p["excess_cagr_vs_fixed"] > 0 and p["positive_folds_vs_fixed"] >= 3 and p["excess_cagr_vs_equal_weight"] > 0.01 and p["positive_folds_vs_equal_weight"] >= 3 and s["excess_cagr_vs_equal_weight"] > 0
    result["decision"] = "SUPPORTED_LEARNED_COMBINATION_CANDIDATE" if supported else "NOT_SUPPORTED_LEARNED_COMBINATION_ROTATE"
    Path("artifacts").mkdir(exist_ok=True)
    out = Path("artifacts/p70_expanding_ridge_cross_universe_r1.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"decision": result["decision"], "oos": result["oos_window"], "25": {k: p[k] for k in ("excess_cagr_vs_fixed", "excess_cagr_vs_equal_weight", "excess_cagr_vs_qqq", "excess_cagr_vs_spy", "positive_folds_vs_fixed", "positive_folds_vs_equal_weight")}, "50": {k: s[k] for k in ("excess_cagr_vs_fixed", "excess_cagr_vs_equal_weight", "excess_cagr_vs_qqq", "excess_cagr_vs_spy")}, "final_coefficients": result["final_coefficients"]}, sort_keys=True))


if __name__ == "__main__":
    main()
