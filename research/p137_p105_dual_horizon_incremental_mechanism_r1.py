from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import p104_p111_crossasset_model_family_tournament_r1 as base

REPRESENTATIONS = {
    "base": ("VTI", "VEA", "IEF", "IAU", "GSG"),
    "proxy": ("SPY", "EFA", "TLT", "GLD", "DBC"),
    "industry": ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT"),
}


def top2(score: pd.Series, assets: tuple[str, ...]) -> pd.Series:
    w = pd.Series(0.0, index=assets)
    keep = score.dropna().sort_values(ascending=False).head(2).index
    if len(keep):
        w.loc[keep] = 1.0 / len(keep)
    return w


def folds(a: pd.Series, b: pd.Series, n: int = 3) -> int:
    return sum(base.metrics(a.iloc[idx])["cagr"] > base.metrics(b.iloc[idx])["cagr"] for idx in np.array_split(np.arange(len(a)), n) if len(idx))


def build_rep(assets: tuple[str, ...]) -> tuple[pd.DataFrame, dict]:
    all_symbols = tuple(dict.fromkeys((*assets, "BIL", "SPY", "QQQ")))
    raw = yf.download(list(all_symbols), start="2007-01-01", auto_adjust=True, progress=False, threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.loc[:, list(all_symbols)].dropna(how="all").astype(float)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    monthly = close.resample("ME").last()
    m6, m12 = monthly.pct_change(6), monthly.pct_change(12)
    prev = {"p105": pd.Series(0.0, index=assets), "m6": pd.Series(0.0, index=assets), "m12": pd.Series(0.0, index=assets)}
    rows = []
    for i, dt in enumerate(monthly.index[:-1]):
        nxt = monthly.index[i + 1]
        req = pd.DataFrame({"m6": m6.loc[dt, list(assets)], "m12": m12.loc[dt, list(assets)]})
        next_r = monthly.loc[nxt, list(all_symbols)] / monthly.loc[dt, list(all_symbols)] - 1
        if req.isna().any().any() or next_r.isna().any():
            continue
        scores = {
            "p105": req.rank(pct=True).mean(axis=1),
            "m6": req.m6.rank(pct=True),
            "m12": req.m12.rank(pct=True),
        }
        row = {"date": nxt, "equal_weight": float(next_r.loc[list(assets)].mean()), "spy": float(next_r.SPY), "qqq": float(next_r.QQQ)}
        for name, score in scores.items():
            w = top2(score, assets)
            row[f"{name}_gross"] = float((w * next_r.loc[list(assets)]).sum())
            row[f"{name}_turn"] = 0.5 * float((w - prev[name]).abs().sum())
            prev[name] = w
        rows.append(row)
    f = pd.DataFrame(rows).set_index("date")
    return f, {"source": "Yahoo Finance via yfinance 0.2.65 adjusted close", "assets": list(assets), "start": str(f.index.min().date()), "end": str(f.index.max().date())}


def evaluate(f: pd.DataFrame, start: str, bps: int) -> dict:
    g = f if start == "full" else f.loc[f.index >= pd.Timestamp(start)]
    p105 = g.p105_gross - g.p105_turn * bps / 10000
    m6 = g.m6_gross - g.m6_turn * bps / 10000
    m12 = g.m12_gross - g.m12_turn * bps / 10000
    inc = p105 - m6
    keep = inc.sort_values(ascending=False).index[min(5, len(inc)):]
    return {
        "window": {"start": str(g.index.min().date()), "end": str(g.index.max().date()), "months": len(g)},
        "p105": base.metrics(p105), "m6": base.metrics(m6), "m12": base.metrics(m12), "equal_weight": base.metrics(g.equal_weight),
        "p105_excess_vs_equal_weight": base.metrics(p105)["cagr"] - base.metrics(g.equal_weight)["cagr"],
        "p105_incremental_vs_m6": base.metrics(p105)["cagr"] - base.metrics(m6)["cagr"],
        "p105_incremental_vs_m12": base.metrics(p105)["cagr"] - base.metrics(m12)["cagr"],
        "positive_folds_vs_m6": folds(p105, m6),
        "five_strongest_p105_minus_m6_months_removed_cagr": base.metrics(p105.loc[keep])["cagr"] - base.metrics(m6.loc[keep])["cagr"],
        "p105_annual_turnover": float(g.p105_turn.mean() * 12),
        "m6_annual_turnover": float(g.m6_turn.mean() * 12),
    }


def main() -> None:
    out = {"schema": "research.p137_p105_dual_horizon_incremental_mechanism_r1", "parent_ids": ["P105", "P137"], "contract": {"question": "does fixed 6m+12m dual-horizon ranking add durable value beyond fixed 6m-only ranking", "representations": {k:list(v) for k,v in REPRESENTATIONS.items()}, "windows": ["full", "2018-01-31", "2022-01-31"], "costs_bps": [25,50], "primary_reference": "fixed 6m-only top2", "secondary_reference": "fixed 12m-only top2", "matched_control": "same-universe equal weight", "chronological_folds": 3, "concentration_test": "remove five strongest P105-minus-6m months", "no_horizon_topk_weight_or_threshold_tuning": True}, "results": {}}
    for rep, assets in REPRESENTATIONS.items():
        f, meta = build_rep(assets)
        out["results"][rep] = {"source": meta}
        for start in ("full", "2018-01-31", "2022-01-31"):
            out["results"][rep][start] = {str(bps): evaluate(f, start, bps) for bps in (25,50)}
    late = [(rep,start) for rep in REPRESENTATIONS for start in ("2018-01-31","2022-01-31")]
    positives = [out["results"][r][s][str(b)]["p105_incremental_vs_m6"] > 0 for r,s in late for b in (25,50)]
    folds_ok = [out["results"][r][s]["25"]["positive_folds_vs_m6"] >= 2 for r,s in late]
    trims = [out["results"][r][s]["25"]["five_strongest_p105_minus_m6_months_removed_cagr"] > 0 for r,s in late]
    if all(positives) and all(folds_ok) and all(trims):
        decision = "DUAL_HORIZON_INCREMENTAL_MECHANISM_BROADLY_SUPPORTED"
    elif sum(positives) >= 8 and sum(folds_ok) >= 4:
        decision = "DUAL_HORIZON_INCREMENTAL_SUPPORT_MIXED_OR_CONCENTRATED"
    else:
        decision = "DUAL_HORIZON_NOT_SEPARABLE_FROM_SIX_MONTH_MOMENTUM"
    out["decision"] = decision
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p137_p105_dual_horizon_incremental_mechanism_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {r:{s:{"25_inc_m6":out["results"][r][s]["25"]["p105_incremental_vs_m6"],"25_inc_m12":out["results"][r][s]["25"]["p105_incremental_vs_m12"],"25_folds":out["results"][r][s]["25"]["positive_folds_vs_m6"],"25_trim":out["results"][r][s]["25"]["five_strongest_p105_minus_m6_months_removed_cagr"],"50_inc_m6":out["results"][r][s]["50"]["p105_incremental_vs_m6"]} for s in ("full","2018-01-31","2022-01-31")} for r in REPRESENTATIONS}
    print(json.dumps({"decision": decision, "results": compact}, sort_keys=True))

if __name__ == "__main__":
    main()
