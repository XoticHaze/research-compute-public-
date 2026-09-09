#!/usr/bin/env python3
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

START = "2010-01-01"
END = None
COST_BPS = [1.0, 2.5, 5.0]
MIN_ROWS = 1500
MARKETS = {
    "NQ": "NQ=F",
    "ES": "ES=F",
    "RTY": "RTY=F",
    "CL": "CL=F",
    "GC": "GC=F",
    "ZN": "ZN=F",
}


def flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def load_market(ticker):
    df = yf.download(ticker, start=START, end=END, auto_adjust=False, progress=False, threads=False)
    df = flatten_columns(df)
    need = ["Open", "Close"]
    if any(c not in df.columns for c in need):
        raise RuntimeError(f"{ticker}: missing columns {need}")
    out = df[[c for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in df.columns]].copy()
    out = out.dropna(subset=["Open", "Close"])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    if len(out) < MIN_ROWS:
        raise RuntimeError(f"{ticker}: only {len(out)} usable rows")
    if not out.index.is_monotonic_increasing or not out.index.is_unique:
        raise RuntimeError(f"{ticker}: index integrity failed")
    if (out[["Open", "Close"]] <= 0).any().any():
        raise RuntimeError(f"{ticker}: nonpositive price")
    payload = out.to_csv(date_format="%Y-%m-%d").encode()
    return out, hashlib.sha256(payload).hexdigest()


def ann_metrics(r, periods):
    r = pd.Series(r).dropna()
    if len(r) < 2:
        return {"cagr": None, "sharpe": None, "max_dd": None, "final_equity": None}
    eq = (1.0 + r).cumprod()
    years = len(r) / periods
    cagr = float(eq.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and eq.iloc[-1] > 0 else None
    vol = float(r.std(ddof=1) * math.sqrt(periods))
    sharpe = float(r.mean() * periods / vol) if vol > 0 else None
    dd = eq / eq.cummax() - 1.0
    return {
        "cagr": cagr,
        "sharpe": sharpe,
        "max_dd": float(dd.min()),
        "final_equity": float(eq.iloc[-1]),
    }


def fold_excess(candidate, baseline, folds=5):
    z = pd.concat([candidate.rename("c"), baseline.rename("b")], axis=1).dropna()
    if len(z) < folds * 5:
        return []
    chunks = np.array_split(np.arange(len(z)), folds)
    out = []
    for i, idx in enumerate(chunks, 1):
        c = z.iloc[idx, 0]
        b = z.iloc[idx, 1]
        ce = float((1 + c).prod() - 1)
        be = float((1 + b).prod() - 1)
        out.append({"fold": i, "candidate_terminal_return": ce, "baseline_terminal_return": be, "excess": ce - be})
    return out


def monthly_trend(df, cost_bps):
    close = df["Close"].astype(float)
    mclose = close.resample("ME").last().dropna()
    mret = mclose.pct_change()
    daily_mom = close / close.shift(252) - 1.0
    msig = daily_mom.resample("ME").last().reindex(mclose.index)
    w = (msig.shift(1) > 0).astype(float)
    turnover = w.diff().abs().fillna(w.abs())
    candidate = w * mret - turnover * (cost_bps * 1e-4)
    baseline = float(w.mean()) * mret
    z = pd.concat([candidate.rename("candidate"), baseline.rename("baseline"), w.rename("weight")], axis=1).dropna()
    folds = fold_excess(z.candidate, z.baseline)
    cm = ann_metrics(z.candidate, 12)
    bm = ann_metrics(z.baseline, 12)
    positive_folds = sum(x["excess"] > 0 for x in folds)
    supported = (
        cm["cagr"] is not None and bm["cagr"] is not None and
        cm["cagr"] > bm["cagr"] and positive_folds >= 3 and
        cm["sharpe"] is not None and bm["sharpe"] is not None and cm["sharpe"] >= bm["sharpe"]
    )
    return {
        "candidate": cm,
        "exposure_matched_static": bm,
        "mean_exposure": float(z.weight.mean()),
        "annual_turnover": float(turnover.reindex(z.index).mean() * 12),
        "folds": folds,
        "positive_excess_folds": positive_folds,
        "screen_supported": bool(supported),
    }


def overnight_intraday(df, cost_bps):
    op = df["Open"].astype(float)
    cl = df["Close"].astype(float)
    overnight = np.log(op / cl.shift(1))
    intraday = np.log(cl / op)
    score = overnight.rolling(20, min_periods=20).sum() - intraday.rolling(20, min_periods=20).sum()
    w = (score.shift(1) > 0).astype(float)
    gross = cl / op - 1.0
    # Screening cost is charged as a complete open-to-close round trip on each active session.
    candidate = w * gross - w * (2.0 * cost_bps * 1e-4)
    baseline = float(w.mean()) * gross
    z = pd.concat([candidate.rename("candidate"), baseline.rename("baseline"), w.rename("weight")], axis=1).dropna()
    folds = fold_excess(z.candidate, z.baseline)
    cm = ann_metrics(z.candidate, 252)
    bm = ann_metrics(z.baseline, 252)
    positive_folds = sum(x["excess"] > 0 for x in folds)
    supported = (
        cm["cagr"] is not None and bm["cagr"] is not None and
        cm["cagr"] > bm["cagr"] and positive_folds >= 3 and
        cm["sharpe"] is not None and bm["sharpe"] is not None and cm["sharpe"] >= bm["sharpe"]
    )
    return {
        "candidate": cm,
        "exposure_matched_static_intraday": bm,
        "mean_exposure": float(z.weight.mean()),
        "active_sessions": int(z.weight.sum()),
        "folds": folds,
        "positive_excess_folds": positive_folds,
        "screen_supported": bool(supported),
    }


def main():
    result = {
        "schema": "research.futures_crossmarket_screen_r1",
        "classification": "EXTERNAL_PROXY_SCREEN_ONLY_NOT_CANONICAL_FUTURES_EVIDENCE",
        "scientific_contract": {
            "purpose": "select markets/mechanisms worth canonical futures follow-up without claiming vendor continuous symbols are roll-authoritative",
            "markets": MARKETS,
            "mechanisms": {
                "TSMOM_252_MONTHLY": "prior 252-session return sign; next month long or cash",
                "OVERNIGHT_VS_INTRADAY_20": "prior 20-session cumulative overnight minus intraday log-return state; next session open-to-close long or cash",
            },
            "cost_bps_per_side_or_turnover_unit": COST_BPS,
            "primary_cost_bps": 2.5,
            "matched_control": "static exposure to the same proxy over the identical return window, with exposure equal to candidate mean exposure",
            "support_gate": "candidate CAGR > exposure-matched static, >=3/5 positive excess folds, and candidate Sharpe >= matched Sharpe at 2.5 bps",
            "no_parameter_search": True,
            "no_canonical_roll_claim": True,
            "no_promotion_authority": True,
        },
        "markets": {},
    }
    primary = 2.5
    for name, ticker in MARKETS.items():
        try:
            df, sha = load_market(ticker)
            lane = {
                "ticker": ticker,
                "rows": int(len(df)),
                "first": str(df.index.min().date()),
                "last": str(df.index.max().date()),
                "normalized_ohlcv_sha256": sha,
                "tests": {},
            }
            for cb in COST_BPS:
                lane["tests"][f"trend_{cb:g}bps"] = monthly_trend(df, cb)
                lane["tests"][f"overnight_intraday_{cb:g}bps"] = overnight_intraday(df, cb)
            lane["primary_screen"] = {
                "trend_supported": lane["tests"][f"trend_{primary:g}bps"]["screen_supported"],
                "overnight_intraday_supported": lane["tests"][f"overnight_intraday_{primary:g}bps"]["screen_supported"],
            }
            result["markets"][name] = lane
        except Exception as exc:
            result["markets"][name] = {"ticker": ticker, "state": "DATA_OR_PROXY_BLOCKED", "error": str(exc)}

    evaluated = [v for v in result["markets"].values() if "primary_screen" in v]
    result["summary"] = {
        "evaluated_markets": len(evaluated),
        "trend_supported_markets": [k for k, v in result["markets"].items() if v.get("primary_screen", {}).get("trend_supported")],
        "overnight_intraday_supported_markets": [k for k, v in result["markets"].items() if v.get("primary_screen", {}).get("overnight_intraday_supported")],
        "next_step": "Only supported screens earn a canonical/provenance-safe roll-aware futures evaluation. Unsupported screens are not a rejection of all futures models; they reject only this frozen proxy-screen mechanism on this representation.",
    }
    Path("futures_crossmarket_screen_r1.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
