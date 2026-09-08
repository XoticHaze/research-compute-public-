from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

START = "2005-01-01"
END = None
COSTS_BPS = (10, 25, 50)
MIN_TRAIN_MONTHS = 60
FEATURES = (
    "mom1",
    "mom3",
    "mom6",
    "mom12",
    "vol3",
    "vol6",
    "drawdown6",
    "trend200",
    "rel6_spy",
)

UNIVERSES = {
    "sector": ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"),
    "industry": ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT"),
    "crossasset": ("SPY", "QQQ", "TLT", "GLD", "DBC"),
}

CHILDREN = {
    "sector_ridge": ("sector", "ridge"),
    "sector_hgb": ("sector", "hgb"),
    "sector_rf": ("sector", "rf"),
    "industry_ridge": ("industry", "ridge"),
    "industry_hgb": ("industry", "hgb"),
    "industry_rf": ("industry", "rf"),
    "crossasset_ridge": ("crossasset", "ridge"),
    "crossasset_hgb": ("crossasset", "hgb"),
}


@dataclass(frozen=True)
class ChildSpec:
    child: str
    universe_name: str
    model_name: str
    symbols: tuple[str, ...]
    top_k: int


def _spec(child: str) -> ChildSpec:
    universe_name, model_name = CHILDREN[child]
    symbols = UNIVERSES[universe_name]
    top_k = 2 if universe_name == "crossasset" else 3
    return ChildSpec(child, universe_name, model_name, symbols, top_k)


def _load(symbols: tuple[str, ...]) -> pd.DataFrame:
    requested = tuple(dict.fromkeys((*symbols, "SPY", "QQQ")))
    data = yf.download(
        list(requested),
        start=START,
        end=END,
        auto_adjust=True,
        progress=False,
        threads=False,
        group_by="column",
    )
    if data.empty:
        raise RuntimeError("empty_yfinance_download")
    if isinstance(data.columns, pd.MultiIndex):
        if "Close" not in data.columns.get_level_values(0):
            raise RuntimeError("close_field_missing")
        close = data["Close"].copy()
    else:
        close = data[["Close"]].copy()
        close.columns = [requested[0]]
    missing = [s for s in requested if s not in close.columns]
    if missing:
        raise RuntimeError(f"missing_symbols:{missing}")
    close = close.loc[:, list(requested)].sort_index().astype(float)
    close = close.dropna(how="all")
    if len(close) < 1000:
        raise RuntimeError(f"insufficient_daily_rows:{len(close)}")
    return close


def _normalized_source_hash(close: pd.DataFrame) -> str:
    normalized = close.reset_index().to_csv(index=False, float_format="%.10g").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _feature_panel(close: pd.DataFrame, symbols: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = close.resample("ME").last()
    monthly_returns = monthly.pct_change()

    daily_returns = close.pct_change()
    vol3 = daily_returns.rolling(63, min_periods=50).std(ddof=0) * math.sqrt(252)
    vol6 = daily_returns.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)
    rolling_high = close.rolling(126, min_periods=100).max()
    drawdown6 = close / rolling_high - 1.0
    trend200 = close / close.rolling(200, min_periods=160).mean() - 1.0

    vol3_m = vol3.resample("ME").last()
    vol6_m = vol6.resample("ME").last()
    dd6_m = drawdown6.resample("ME").last()
    trend200_m = trend200.resample("ME").last()

    rows: list[dict[str, object]] = []
    for symbol in symbols:
        if symbol not in monthly.columns:
            continue
        for dt in monthly.index:
            row = {
                "month": dt,
                "symbol": symbol,
                "mom1": monthly[symbol].pct_change(1).get(dt, np.nan),
                "mom3": monthly[symbol].pct_change(3).get(dt, np.nan),
                "mom6": monthly[symbol].pct_change(6).get(dt, np.nan),
                "mom12": monthly[symbol].pct_change(12).get(dt, np.nan),
                "vol3": vol3_m[symbol].get(dt, np.nan),
                "vol6": vol6_m[symbol].get(dt, np.nan),
                "drawdown6": dd6_m[symbol].get(dt, np.nan),
                "trend200": trend200_m[symbol].get(dt, np.nan),
                "rel6_spy": monthly[symbol].pct_change(6).get(dt, np.nan)
                - monthly["SPY"].pct_change(6).get(dt, np.nan),
            }
            rows.append(row)
    panel = pd.DataFrame(rows)
    if panel.empty:
        raise RuntimeError("empty_feature_panel")

    next_returns = monthly_returns.shift(-1)
    universe_next_mean = next_returns.loc[:, list(symbols)].mean(axis=1)
    panel["target"] = [
        next_returns.at[row.month, row.symbol] - universe_next_mean.at[row.month]
        if row.month in next_returns.index and row.symbol in next_returns.columns
        else np.nan
        for row in panel.itertuples()
    ]
    panel = panel.replace([np.inf, -np.inf], np.nan)

    # Cross-sectional z-scores at each rebalance date keep the task focused on ranking,
    # while fitting scalers/models only on already-observed target rows below.
    for feature in FEATURES:
        grouped = panel.groupby("month")[feature]
        mean = grouped.transform("mean")
        std = grouped.transform(lambda x: x.std(ddof=0)).replace(0.0, np.nan)
        panel[feature] = (panel[feature] - mean) / std

    return panel, monthly


def _model(name: str):
    if name == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    if name == "hgb":
        return HistGradientBoostingRegressor(
            loss="squared_error",
            learning_rate=0.05,
            max_iter=150,
            max_leaf_nodes=15,
            l2_regularization=1.0,
            random_state=7,
        )
    if name == "rf":
        return RandomForestRegressor(
            n_estimators=250,
            max_depth=5,
            min_samples_leaf=12,
            max_features=0.7,
            n_jobs=1,
            random_state=7,
        )
    raise ValueError(name)


def _walk_forward(panel: pd.DataFrame, monthly: pd.DataFrame, spec: ChildSpec) -> pd.DataFrame:
    complete = panel.dropna(subset=[*FEATURES]).copy()
    months = sorted(complete["month"].unique())
    if len(months) < MIN_TRAIN_MONTHS + 24:
        raise RuntimeError(f"insufficient_complete_months:{len(months)}")

    records: list[dict[str, object]] = []
    previous_weights = {s: 0.0 for s in spec.symbols}
    first_eval_index = MIN_TRAIN_MONTHS

    for i, month in enumerate(months[first_eval_index:], start=first_eval_index):
        train_months = set(months[:i])
        train = complete[complete["month"].isin(train_months)].dropna(subset=["target"])
        current = complete[complete["month"] == month].copy()
        if len(train) < 250 or len(current) != len(spec.symbols):
            continue

        # Target for a feature month m is m->m+1. Restricting training feature months
        # to strictly before the current month means every training target is observable
        # by the current rebalance close.
        estimator = _model(spec.model_name)
        estimator.fit(train.loc[:, FEATURES].to_numpy(float), train["target"].to_numpy(float))
        current["score"] = estimator.predict(current.loc[:, FEATURES].to_numpy(float))
        chosen = current.sort_values(["score", "symbol"], ascending=[False, True]).head(spec.top_k)["symbol"].tolist()

        if month not in monthly.index:
            continue
        loc = monthly.index.get_loc(month)
        if not isinstance(loc, (int, np.integer)) or loc + 1 >= len(monthly.index):
            continue
        next_month = monthly.index[loc + 1]
        realized = monthly.loc[next_month, list(spec.symbols)] / monthly.loc[month, list(spec.symbols)] - 1.0
        if realized.isna().any():
            continue

        weights = {s: (1.0 / spec.top_k if s in chosen else 0.0) for s in spec.symbols}
        turnover = 0.5 * sum(abs(weights[s] - previous_weights[s]) for s in spec.symbols)
        candidate_gross = sum(weights[s] * float(realized[s]) for s in spec.symbols)
        baseline_return = float(realized.mean())
        spy_return = float(monthly.at[next_month, "SPY"] / monthly.at[month, "SPY"] - 1.0)
        qqq_return = float(monthly.at[next_month, "QQQ"] / monthly.at[month, "QQQ"] - 1.0)

        records.append(
            {
                "feature_month": str(pd.Timestamp(month).date()),
                "return_month": str(pd.Timestamp(next_month).date()),
                "candidate_gross": candidate_gross,
                "baseline_ew": baseline_return,
                "spy": spy_return,
                "qqq": qqq_return,
                "turnover": turnover,
                "chosen": chosen,
            }
        )
        previous_weights = weights

    frame = pd.DataFrame(records)
    if len(frame) < 60:
        raise RuntimeError(f"insufficient_oos_months:{len(frame)}")
    return frame


def _metrics(r: pd.Series) -> dict[str, float]:
    r = pd.Series(r, dtype=float).dropna()
    if r.empty:
        raise RuntimeError("empty_returns")
    eq = (1.0 + r).cumprod()
    years = len(r) / 12.0
    cagr = float(eq.iloc[-1] ** (1.0 / years) - 1.0)
    vol = float(r.std(ddof=0) * math.sqrt(12.0))
    ann = float(r.mean() * 12.0)
    sharpe = ann / vol if vol > 0 else float("nan")
    dd = eq / eq.cummax() - 1.0
    mdd = float(dd.min())
    calmar = cagr / abs(mdd) if mdd < 0 else float("nan")
    return {
        "cagr": cagr,
        "annualized_mean": ann,
        "annualized_vol": vol,
        "sharpe_rf0": float(sharpe),
        "max_drawdown_monthly": mdd,
        "calmar": float(calmar),
        "final_equity": float(eq.iloc[-1]),
    }


def _folds(candidate: pd.Series, baseline: pd.Series, n: int = 5) -> list[dict[str, object]]:
    chunks = np.array_split(np.arange(len(candidate)), n)
    out: list[dict[str, object]] = []
    for fold, idx in enumerate(chunks, start=1):
        cr = candidate.iloc[idx]
        br = baseline.iloc[idx]
        cm = _metrics(cr)
        bm = _metrics(br)
        out.append(
            {
                "fold": fold,
                "months": int(len(idx)),
                "candidate_cagr": cm["cagr"],
                "baseline_cagr": bm["cagr"],
                "excess_cagr": cm["cagr"] - bm["cagr"],
            }
        )
    return out


def _year_persistence(frame: pd.DataFrame, candidate: pd.Series, baseline: pd.Series) -> dict[str, object]:
    years = pd.to_datetime(frame["return_month"]).dt.year
    rows = []
    for year in sorted(years.unique()):
        mask = years == year
        c = float((1.0 + candidate[mask].reset_index(drop=True)).prod() - 1.0)
        b = float((1.0 + baseline[mask].reset_index(drop=True)).prod() - 1.0)
        rows.append({"year": int(year), "candidate_return": c, "baseline_return": b, "excess_return": c - b})
    return {
        "positive_excess_years": int(sum(row["excess_return"] > 0 for row in rows)),
        "years": int(len(rows)),
        "detail": rows,
    }


def _evaluate(frame: pd.DataFrame, spec: ChildSpec, source_hash: str) -> dict[str, object]:
    output: dict[str, object] = {
        "schema": "research.combined_cross_sectional_ml_full_pass_r1",
        "child": spec.child,
        "universe": spec.universe_name,
        "symbols": list(spec.symbols),
        "model": spec.model_name,
        "top_k": spec.top_k,
        "source": {
            "provider": "Yahoo Finance via yfinance",
            "data": "auto-adjusted daily close",
            "normalized_price_panel_sha256": source_hash,
        },
        "scientific_contract": {
            "target": "next_month_asset_return_minus_same_universe_equal_weight_return",
            "features": list(FEATURES),
            "training": "expanding pooled cross-sectional walk-forward; current month excluded from fit; no realized current-month target used",
            "selection": "monthly equal-weight top-k predicted cross-sectional excess",
            "primary_cost_bps_per_one_way_turnover": 25,
            "stress_cost_bps": 50,
            "comparators": ["same_universe_equal_weight", "SPY", "QQQ"],
            "frozen_support_gate": ">1pp CAGR excess vs same-universe EW at 25bps, >=3/5 positive folds, Sharpe >= EW, and positive 50bps excess",
        },
        "oos_window": {
            "start": frame.iloc[0]["return_month"],
            "end": frame.iloc[-1]["return_month"],
            "months": int(len(frame)),
        },
        "mean_annual_turnover": float(frame["turnover"].mean() * 12.0),
        "costs": {},
    }

    for bps in COSTS_BPS:
        candidate = frame["candidate_gross"] - frame["turnover"] * (bps / 10000.0)
        baseline = frame["baseline_ew"]
        spy = frame["spy"]
        qqq = frame["qqq"]
        cm = _metrics(candidate)
        bm = _metrics(baseline)
        sm = _metrics(spy)
        qm = _metrics(qqq)
        folds = _folds(candidate, baseline)
        output["costs"][str(bps)] = {
            "candidate": cm,
            "matched_equal_weight": bm,
            "spy": sm,
            "qqq": qm,
            "excess_cagr_vs_equal_weight": cm["cagr"] - bm["cagr"],
            "excess_cagr_vs_spy": cm["cagr"] - sm["cagr"],
            "excess_cagr_vs_qqq": cm["cagr"] - qm["cagr"],
            "positive_excess_folds": int(sum(f["excess_cagr"] > 0 for f in folds)),
            "folds": folds,
            "year_persistence": _year_persistence(frame, candidate, baseline),
        }

    primary = output["costs"]["25"]
    stress = output["costs"]["50"]
    supported = (
        primary["excess_cagr_vs_equal_weight"] > 0.01
        and primary["positive_excess_folds"] >= 3
        and primary["candidate"]["sharpe_rf0"] >= primary["matched_equal_weight"]["sharpe_rf0"]
        and stress["excess_cagr_vs_equal_weight"] > 0.0
    )
    output["decision"] = "SUPPORTED_REQUIRES_INDEPENDENT_CONFIRMATION" if supported else "NOT_SUPPORTED_ROTATE"
    output["broad_market_opportunity_cost"] = {
        "beats_spy_25bps": bool(primary["excess_cagr_vs_spy"] > 0),
        "beats_qqq_25bps": bool(primary["excess_cagr_vs_qqq"] > 0),
    }
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", required=True, choices=sorted(CHILDREN))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    spec = _spec(args.child)
    close = _load(spec.symbols)
    source_hash = _normalized_source_hash(close.loc[:, list(dict.fromkeys((*spec.symbols, "SPY", "QQQ")))])
    panel, monthly = _feature_panel(close, spec.symbols)
    frame = _walk_forward(panel, monthly, spec)
    result = _evaluate(frame, spec, source_hash)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(
        json.dumps(
            {
                "child": spec.child,
                "decision": result["decision"],
                "oos_window": result["oos_window"],
                "primary_excess_cagr": result["costs"]["25"]["excess_cagr_vs_equal_weight"],
                "primary_positive_folds": result["costs"]["25"]["positive_excess_folds"],
                "artifact": str(out),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
