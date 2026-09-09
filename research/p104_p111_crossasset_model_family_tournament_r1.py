from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ASSETS = ("VTI", "VEA", "IEF", "IAU", "GSG")
ALL = (*ASSETS, "BIL", "SPY", "QQQ")
START = "2007-01-01"
COSTS = (25, 50)


def metrics(r: pd.Series) -> dict:
    r = pd.Series(r, dtype=float).dropna()
    eq = (1 + r).cumprod()
    years = len(r) / 12
    cagr = float(eq.iloc[-1] ** (1 / years) - 1)
    mean = float(r.mean() * 12)
    vol = float(r.std(ddof=0) * math.sqrt(12))
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    return {
        "cagr": cagr,
        "annualized_mean": mean,
        "annualized_vol": vol,
        "sharpe_rf0": mean / vol if vol else None,
        "max_drawdown_monthly": mdd,
        "calmar": cagr / abs(mdd) if mdd < 0 else None,
    }


def fold_stats(a: pd.Series, b: pd.Series, n: int = 5) -> tuple[int, list[dict]]:
    rows = []
    for k, idx in enumerate(np.array_split(np.arange(len(a)), n), 1):
        if not len(idx):
            continue
        am = metrics(a.iloc[idx])
        bm = metrics(b.iloc[idx])
        rows.append({"fold": k, "excess_cagr": am["cagr"] - bm["cagr"]})
    return sum(x["excess_cagr"] > 0 for x in rows), rows


def weights_topk(score: pd.Series, k: int = 2) -> pd.Series:
    w = pd.Series(0.0, index=ASSETS)
    s = score.dropna().sort_values(ascending=False).head(k)
    if len(s):
        w.loc[s.index] = 1.0 / len(s)
    return w


def normalize_positive(x: pd.Series) -> pd.Series:
    x = x.clip(lower=0).fillna(0.0)
    s = float(x.sum())
    return x / s if s > 0 else pd.Series(0.0, index=x.index)


def turnover(w: pd.Series, prev: pd.Series) -> float:
    return 0.5 * float((w - prev).abs().sum())


def source_hash(close: pd.DataFrame) -> str:
    payload = close.round(10).to_csv(index=True, date_format="%Y-%m-%dT%H:%M:%S").encode()
    return hashlib.sha256(payload).hexdigest()


def build_frame() -> tuple[pd.DataFrame, dict]:
    raw = yf.download(list(ALL), start=START, auto_adjust=True, progress=False, threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.loc[:, list(ALL)].dropna(how="all").astype(float)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    last = pd.Timestamp(close.index.max()).normalize()
    monthly = close.resample("ME").last()
    monthly = monthly.loc[monthly.index <= last]
    dret = close.pct_change(fill_method=None)
    vol126 = (dret.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)).resample("ME").last()
    sma200 = close.rolling(200, min_periods=160).mean().resample("ME").last()
    trend200 = monthly / sma200 - 1
    dd126 = (close / close.rolling(126, min_periods=100).max() - 1).resample("ME").last()
    mom1 = monthly.pct_change(1)
    mom3 = monthly.pct_change(3)
    mom6 = monthly.pct_change(6)
    mom12 = monthly.pct_change(12)
    mom12_1 = monthly.shift(1) / monthly.shift(12) - 1

    learned_rows = []
    for i, dt in enumerate(monthly.index[:-1]):
        nxt = monthly.index[i + 1]
        for asset in ASSETS:
            learned_rows.append(
                {
                    "date": dt,
                    "asset": asset,
                    "mom1": mom1.at[dt, asset],
                    "mom3": mom3.at[dt, asset],
                    "mom6": mom6.at[dt, asset],
                    "mom12": mom12.at[dt, asset],
                    "trend200": trend200.at[dt, asset],
                    "vol126": vol126.at[dt, asset],
                    "dd126": dd126.at[dt, asset],
                    "target": monthly.at[nxt, asset] / monthly.at[dt, asset] - 1,
                }
            )
    learned = pd.DataFrame(learned_rows)
    features = ["mom1", "mom3", "mom6", "mom12", "trend200", "vol126", "dd126"]

    ridge = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    hgb = HistGradientBoostingRegressor(max_iter=60, max_depth=3, learning_rate=0.05, l2_regularization=1.0, random_state=17)
    prev = {name: pd.Series(0.0, index=ASSETS) for name in ["p87", "p104", "p105", "p106", "p107", "p108", "p109", "p110", "p111"]}
    out = []

    for i, dt in enumerate(monthly.index[:-1]):
        nxt = monthly.index[i + 1]
        req = pd.DataFrame(
            {
                "mom1": mom1.loc[dt, list(ASSETS)],
                "mom3": mom3.loc[dt, list(ASSETS)],
                "mom6": mom6.loc[dt, list(ASSETS)],
                "mom12": mom12.loc[dt, list(ASSETS)],
                "mom12_1": mom12_1.loc[dt, list(ASSETS)],
                "trend200": trend200.loc[dt, list(ASSETS)],
                "vol126": vol126.loc[dt, list(ASSETS)],
                "dd126": dd126.loc[dt, list(ASSETS)],
            }
        )
        if req.isna().any().any():
            continue
        next_r = monthly.loc[nxt, list(ALL)] / monthly.loc[dt, list(ALL)] - 1
        if next_r.isna().any():
            continue

        # Frozen P87 comparator: three-factor rank composite, top 2.
        p87_score = pd.DataFrame({"mom6": req.mom6, "trend200": req.trend200, "drawdown6": req.dd126}).rank(pct=True).mean(axis=1)
        w87 = weights_topk(p87_score)

        # P104: classic 12-1 cross-sectional momentum.
        w104 = weights_topk(req.mom12_1)
        # P105: dual-horizon 6m/12m rank momentum.
        w105 = weights_topk(pd.DataFrame({"mom6": req.mom6, "mom12": req.mom12}).rank(pct=True).mean(axis=1))
        # P106: absolute time-series momentum, equal weight only positive 12m assets; otherwise BIL.
        sig106 = (req.mom12 > 0).astype(float)
        w106 = normalize_positive(sig106)
        # P107: inverse-volatility allocation across all assets.
        w107 = normalize_positive(1.0 / req.vol126.replace(0, np.nan))
        # P108: trend-filtered inverse-volatility; otherwise BIL.
        w108 = normalize_positive((req.trend200 > 0).astype(float) / req.vol126.replace(0, np.nan))
        # P109: momentum penalized by recent average correlation to peers.
        if i >= 7:
            hist = monthly.loc[:dt, list(ASSETS)].pct_change(fill_method=None).tail(6)
            corr_pen = hist.corr().abs().replace(1.0, np.nan).mean(axis=1).fillna(1.0)
        else:
            corr_pen = pd.Series(1.0, index=ASSETS)
        z_mom = (req.mom6 - req.mom6.mean()) / (req.mom6.std(ddof=0) or 1.0)
        w109 = weights_topk(z_mom - corr_pen)

        # P110/P111: expanding-window learned cross-sectional forecasts, trained only on prior months.
        train = learned.loc[learned.date < dt].dropna(subset=features + ["target"])
        now = req.loc[:, features]
        if train.date.nunique() >= 60:
            ridge.fit(train[features], train.target)
            hgb.fit(train[features], train.target)
            w110 = weights_topk(pd.Series(ridge.predict(now), index=ASSETS))
            w111 = weights_topk(pd.Series(hgb.predict(now), index=ASSETS))
        else:
            continue

        weights = {"p87": w87, "p104": w104, "p105": w105, "p106": w106, "p107": w107, "p108": w108, "p109": w109, "p110": w110, "p111": w111}
        row = {"date": nxt, "equal_weight": float(next_r.loc[list(ASSETS)].mean()), "spy": float(next_r.SPY), "qqq": float(next_r.QQQ), "bil": float(next_r.BIL)}
        for name, w in weights.items():
            cash = max(0.0, 1.0 - float(w.sum()))
            row[f"{name}_gross"] = float((w * next_r.loc[list(ASSETS)]).sum() + cash * next_r.BIL)
            row[f"{name}_turn"] = turnover(w, prev[name])
            row[f"{name}_invested"] = float(w.sum())
            prev[name] = w
        out.append(row)

    frame = pd.DataFrame(out).set_index("date")
    meta = {
        "source": "Yahoo Finance via yfinance 0.2.65 adjusted close",
        "source_sha256": source_hash(close),
        "download_last_daily_date": str(last.date()),
        "assets": list(ASSETS),
        "comparators": ["equal_weight", "P87", "SPY", "QQQ"],
    }
    return frame, meta


def evaluate(frame: pd.DataFrame) -> dict:
    specs = {
        "P104": "12-1 cross-sectional momentum top2",
        "P105": "dual-horizon 6m/12m cross-sectional momentum top2",
        "P106": "12m absolute time-series momentum equal-weight positive assets with BIL residual",
        "P107": "126d inverse-volatility allocation",
        "P108": "200d trend-filtered inverse-volatility with BIL residual",
        "P109": "6m momentum minus recent peer-correlation penalty top2",
        "P110": "expanding pooled Ridge next-month return forecast top2",
        "P111": "expanding pooled histogram-gradient-boost next-month return forecast top2",
    }
    result = {}
    for pid, desc in specs.items():
        key = pid.lower()
        rec = {"hypothesis": desc, "window": {"start": str(frame.index.min().date()), "end": str(frame.index.max().date()), "months": len(frame)}}
        for bps in COSTS:
            r = frame[f"{key}_gross"] - frame[f"{key}_turn"] * bps / 10000
            p87 = frame.p87_gross - frame.p87_turn * bps / 10000
            ew = frame.equal_weight
            rm, em, pm = metrics(r), metrics(ew), metrics(p87)
            pf, folds = fold_stats(r, ew)
            pfp, folds_p87 = fold_stats(r, p87)
            rec[str(bps)] = {
                "strategy": rm,
                "equal_weight": em,
                "p87": pm,
                "spy": metrics(frame.spy),
                "qqq": metrics(frame.qqq),
                "excess_cagr_vs_equal_weight": rm["cagr"] - em["cagr"],
                "incremental_cagr_vs_p87": rm["cagr"] - pm["cagr"],
                "positive_folds_vs_equal_weight": pf,
                "folds_vs_equal_weight": folds,
                "positive_folds_vs_p87": pfp,
                "folds_vs_p87": folds_p87,
                "annual_turnover": float(frame[f"{key}_turn"].mean() * 12),
                "mean_invested_fraction": float(frame[f"{key}_invested"].mean()),
            }
        gate = rec["25"]["excess_cagr_vs_equal_weight"] > 0 and rec["50"]["excess_cagr_vs_equal_weight"] > 0 and rec["25"]["positive_folds_vs_equal_weight"] >= 3
        rec["decision"] = "SURVIVES_MATCHED_ALPHA_GATE" if gate else "REJECT_OR_ROTATE_EXACT_MODEL"
        result[pid] = rec
    return result


def main() -> None:
    frame, meta = build_frame()
    results = evaluate(frame)
    survivors = [k for k, v in results.items() if v["decision"] == "SURVIVES_MATCHED_ALPHA_GATE"]
    ranked = sorted(results, key=lambda k: results[k]["25"]["excess_cagr_vs_equal_weight"], reverse=True)
    out = {
        "schema": "research.p104_p111_crossasset_model_family_tournament_r1",
        "parent_ids": list(results),
        "contract": {
            "matched_window": "exact common post-feature/training window",
            "universe": list(ASSETS),
            "costs_bps": list(COSTS),
            "matched_control": "same-universe monthly equal weight",
            "opportunity_cost_comparators": ["frozen P87", "SPY", "QQQ"],
            "chronological_folds": 5,
            "learned_models": "expanding-window only; target is next-month asset return; no future rows in training",
            "selection_rule": "no post-result parameter rescue in this run",
        },
        "source": meta,
        "results": results,
        "ranked_by_25bps_matched_excess": ranked,
        "survivors": survivors,
        "next_rule": "Only survivors may receive a higher-information independent temporal/representation/ablation child. Rejected exact models rotate without nearby tuning.",
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p104_p111_crossasset_model_family_tournament_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {k: {"25_excess": results[k]["25"]["excess_cagr_vs_equal_weight"], "50_excess": results[k]["50"]["excess_cagr_vs_equal_weight"], "folds": results[k]["25"]["positive_folds_vs_equal_weight"], "vs_p87": results[k]["25"]["incremental_cagr_vs_p87"], "decision": results[k]["decision"]} for k in ranked}
    print(json.dumps({"survivors": survivors, "ranked": compact, "source_sha256": meta["source_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
