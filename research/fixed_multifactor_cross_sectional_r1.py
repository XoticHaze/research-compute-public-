from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

START = "2005-01-01"
COSTS_BPS = (10, 25, 50)
UNIVERSES = {
    "sector": ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"),
    "industry": ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT"),
    "crossasset": ("SPY", "QQQ", "TLT", "GLD", "DBC"),
}


def load(symbols: tuple[str, ...]) -> pd.DataFrame:
    requested = tuple(dict.fromkeys((*symbols, "SPY", "QQQ")))
    data = yf.download(list(requested), start=START, auto_adjust=True, progress=False, threads=False)
    if data.empty:
        raise RuntimeError("empty_download")
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame()
    missing = [s for s in requested if s not in close.columns]
    if missing:
        raise RuntimeError(f"missing:{missing}")
    return close.loc[:, list(requested)].dropna(how="all").astype(float)


def source_hash(close: pd.DataFrame) -> str:
    return hashlib.sha256(close.reset_index().to_csv(index=False, float_format="%.10g").encode()).hexdigest()


def features(close: pd.DataFrame, symbols: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = close.resample("ME").last()
    daily_r = close.pct_change()
    vol6 = (daily_r.rolling(126, min_periods=100).std(ddof=0) * math.sqrt(252)).resample("ME").last()
    trend200 = (close / close.rolling(200, min_periods=160).mean() - 1).resample("ME").last()
    dd6 = (close / close.rolling(126, min_periods=100).max() - 1).resample("ME").last()
    mom6 = monthly.pct_change(6)

    rows = []
    for dt in monthly.index:
        block = pd.DataFrame(index=list(symbols))
        block["mom6"] = mom6.loc[dt, list(symbols)]
        block["trend200"] = trend200.loc[dt, list(symbols)]
        block["low_vol6"] = -vol6.loc[dt, list(symbols)]
        block["drawdown6"] = dd6.loc[dt, list(symbols)]
        if block.isna().any().any():
            continue
        ranks = block.rank(axis=0, pct=True, method="average")
        score = ranks.mean(axis=1)
        for symbol in symbols:
            rows.append({"month": dt, "symbol": symbol, "score": float(score[symbol])})
    return pd.DataFrame(rows), monthly


def metrics(r: pd.Series) -> dict[str, float]:
    r = pd.Series(r, dtype=float).dropna()
    eq = (1 + r).cumprod()
    years = len(r) / 12
    cagr = float(eq.iloc[-1] ** (1 / years) - 1)
    ann = float(r.mean() * 12)
    vol = float(r.std(ddof=0) * math.sqrt(12))
    sharpe = ann / vol if vol else float("nan")
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    return {
        "cagr": cagr,
        "annualized_mean": ann,
        "annualized_vol": vol,
        "sharpe_rf0": float(sharpe),
        "max_drawdown_monthly": mdd,
        "calmar": float(cagr / abs(mdd)) if mdd < 0 else float("nan"),
        "final_equity": float(eq.iloc[-1]),
    }


def fold_count(c: pd.Series, b: pd.Series) -> tuple[int, list[dict[str, float]]]:
    out = []
    for fold, idx in enumerate(np.array_split(np.arange(len(c)), 5), 1):
        cm, bm = metrics(c.iloc[idx]), metrics(b.iloc[idx])
        out.append({"fold": fold, "candidate_cagr": cm["cagr"], "baseline_cagr": bm["cagr"], "excess_cagr": cm["cagr"] - bm["cagr"]})
    return sum(x["excess_cagr"] > 0 for x in out), out


def evaluate(universe_name: str) -> dict[str, object]:
    symbols = UNIVERSES[universe_name]
    top_k = 2 if universe_name == "crossasset" else 3
    close = load(symbols)
    panel, monthly = features(close, symbols)
    months = sorted(panel.month.unique())
    previous = {s: 0.0 for s in symbols}
    recs = []
    for month in months:
        block = panel[panel.month == month].sort_values(["score", "symbol"], ascending=[False, True])
        if len(block) != len(symbols):
            continue
        loc = monthly.index.get_loc(month)
        if not isinstance(loc, (int, np.integer)) or loc + 1 >= len(monthly):
            continue
        nxt = monthly.index[loc + 1]
        realized = monthly.loc[nxt, list(symbols)] / monthly.loc[month, list(symbols)] - 1
        if realized.isna().any():
            continue
        chosen = block.head(top_k).symbol.tolist()
        w = {s: (1 / top_k if s in chosen else 0.0) for s in symbols}
        turnover = 0.5 * sum(abs(w[s] - previous[s]) for s in symbols)
        recs.append({
            "feature_month": str(pd.Timestamp(month).date()),
            "return_month": str(pd.Timestamp(nxt).date()),
            "gross": sum(w[s] * float(realized[s]) for s in symbols),
            "ew": float(realized.mean()),
            "spy": float(monthly.at[nxt, "SPY"] / monthly.at[month, "SPY"] - 1),
            "qqq": float(monthly.at[nxt, "QQQ"] / monthly.at[month, "QQQ"] - 1),
            "turnover": turnover,
            "chosen": chosen,
        })
        previous = w
    frame = pd.DataFrame(recs)
    if len(frame) < 60:
        raise RuntimeError(f"insufficient_oos:{len(frame)}")

    result: dict[str, object] = {
        "schema": "research.fixed_multifactor_cross_sectional_r1",
        "child": f"{universe_name}_fixed_multifactor",
        "universe": universe_name,
        "symbols": list(symbols),
        "top_k": top_k,
        "source": {"provider": "Yahoo Finance via yfinance", "normalized_price_panel_sha256": source_hash(close)},
        "scientific_contract": {
            "score": "equal-weight percentile ranks of trailing 6m momentum, price/SMA200 trend, inverse 6m realized volatility, and 6m distance-from-high",
            "comparators": ["same_universe_equal_weight", "SPY", "QQQ"],
            "costs_bps": list(COSTS_BPS),
        },
        "oos_window": {"start": frame.iloc[0].return_month, "end": frame.iloc[-1].return_month, "months": int(len(frame))},
        "mean_annual_turnover": float(frame.turnover.mean() * 12),
        "costs": {},
    }
    for bps in COSTS_BPS:
        c = frame.gross - frame.turnover * (bps / 10000)
        b = frame.ew
        cm, bm, sm, qm = metrics(c), metrics(b), metrics(frame.spy), metrics(frame.qqq)
        pos, folds = fold_count(c, b)
        result["costs"][str(bps)] = {
            "candidate": cm,
            "matched_equal_weight": bm,
            "spy": sm,
            "qqq": qm,
            "excess_cagr_vs_equal_weight": cm["cagr"] - bm["cagr"],
            "excess_cagr_vs_spy": cm["cagr"] - sm["cagr"],
            "excess_cagr_vs_qqq": cm["cagr"] - qm["cagr"],
            "positive_excess_folds": int(pos),
            "folds": folds,
        }
    p, s = result["costs"]["25"], result["costs"]["50"]
    supported = p["excess_cagr_vs_equal_weight"] > 0.01 and p["positive_excess_folds"] >= 3 and p["candidate"]["sharpe_rf0"] >= p["matched_equal_weight"]["sharpe_rf0"] and s["excess_cagr_vs_equal_weight"] > 0
    result["decision"] = "SUPPORTED_SIMPLE_COMPOSITE" if supported else "NOT_SUPPORTED_ROTATE"
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", choices=sorted(UNIVERSES), required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    result = evaluate(args.universe)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"child": result["child"], "decision": result["decision"], "primary_excess_cagr": result["costs"]["25"]["excess_cagr_vs_equal_weight"], "out": str(out)}, sort_keys=True))


if __name__ == "__main__":
    main()
