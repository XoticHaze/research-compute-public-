from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

REPRESENTATIONS = {
    "base": ("VTI", "VEA", "IEF", "IAU", "GSG"),
    "proxy": ("SPY", "EFA", "TLT", "GLD", "DBC"),
    "industry": ("SMH", "XBI", "ITB", "KRE", "ITA", "IGV", "IWM", "XRT"),
}
START = "2007-01-01"
COSTS = (25, 50)


def metrics(r: pd.Series) -> dict:
    r = pd.Series(r, dtype=float).dropna()
    eq = (1 + r).cumprod()
    years = len(r) / 12
    cagr = float(eq.iloc[-1] ** (1 / years) - 1)
    mean = float(r.mean() * 12)
    vol = float(r.std(ddof=0) * np.sqrt(12))
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    return {"cagr": cagr, "annualized_mean": mean, "annualized_vol": vol, "sharpe_rf0": mean / vol if vol else None, "max_drawdown": mdd, "calmar": cagr / abs(mdd) if mdd < 0 else None}


def top2(score: pd.Series) -> pd.Series:
    w = pd.Series(0.0, index=score.index)
    w.loc[score.sort_values(ascending=False).head(2).index] = 0.5
    return w


def build(assets: tuple[str, ...]) -> pd.DataFrame:
    raw = yf.download(list(assets), start=START, auto_adjust=True, progress=False, threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.loc[:, list(assets)].dropna(how="all").astype(float)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    last = pd.Timestamp(close.index.max()).normalize()
    m = close.resample("ME").last().loc[lambda x: x.index <= last]
    mom6, mom12 = m.pct_change(6), m.pct_change(12)
    prev = {"p105": pd.Series(0.0, index=assets), "p109": pd.Series(0.0, index=assets), "blend": pd.Series(0.0, index=assets)}
    rows = []
    for i, dt in enumerate(m.index[:-1]):
        if i < 12:
            continue
        nxt = m.index[i+1]
        m6, m12 = mom6.loc[dt, list(assets)], mom12.loc[dt, list(assets)]
        if m6.isna().any() or m12.isna().any():
            continue
        dual = pd.DataFrame({"mom6": m6, "mom12": m12}).rank(pct=True).mean(axis=1)
        w105 = top2(dual)
        hist = m.loc[:dt, list(assets)].pct_change(fill_method=None).tail(6)
        corr_pen = hist.corr().abs().replace(1.0, np.nan).mean(axis=1).fillna(1.0)
        z = (m6 - m6.mean()) / (m6.std(ddof=0) or 1.0)
        w109 = top2(z - corr_pen)
        wblend = 0.5 * w105 + 0.5 * w109
        nr = m.loc[nxt, list(assets)] / m.loc[dt, list(assets)] - 1
        row = {"date": nxt, "equal_weight": float(nr.mean())}
        for name, w in (("p105", w105), ("p109", w109), ("blend", wblend)):
            row[f"{name}_gross"] = float((w * nr).sum())
            row[f"{name}_turn"] = 0.5 * float((w - prev[name]).abs().sum())
            prev[name] = w
        rows.append(row)
    return pd.DataFrame(rows).set_index("date")


def folds(a: pd.Series, b: pd.Series, n: int = 3) -> int:
    wins = 0
    for idx in np.array_split(np.arange(len(a)), n):
        if len(idx) and metrics(a.iloc[idx])["cagr"] > metrics(b.iloc[idx])["cagr"]:
            wins += 1
    return wins


def eval_window(f: pd.DataFrame, start: str, bps: int) -> dict:
    g = f.loc[f.index >= pd.Timestamp(start)].copy()
    blend = g.blend_gross - g.blend_turn * bps / 10000
    p105 = g.p105_gross - g.p105_turn * bps / 10000
    p109 = g.p109_gross - g.p109_turn * bps / 10000
    ew = g.equal_weight
    bm, a, c, e = metrics(blend), metrics(p105), metrics(p109), metrics(ew)
    rel = blend - ew
    drop = rel.sort_values(ascending=False).head(min(5, len(rel))).index
    keep = g.index.difference(drop)
    return {
        "window": {"start": str(g.index.min().date()), "end": str(g.index.max().date()), "months": len(g)},
        "blend": bm,
        "p105": a,
        "p109": c,
        "equal_weight": e,
        "blend_excess_vs_equal_weight": bm["cagr"] - e["cagr"],
        "blend_incremental_vs_p105": bm["cagr"] - a["cagr"],
        "blend_incremental_vs_p109": bm["cagr"] - c["cagr"],
        "positive_folds_vs_equal_weight": folds(blend, ew),
        "five_strongest_blend_minus_equal_weight_months_removed_excess_cagr": metrics(blend.loc[keep])["cagr"] - metrics(ew.loc[keep])["cagr"],
        "blend_annual_turnover": float(g.blend_turn.mean() * 12),
        "p105_annual_turnover": float(g.p105_turn.mean() * 12),
        "p109_annual_turnover": float(g.p109_turn.mean() * 12),
    }


def main() -> None:
    out = {
        "schema": "research.p136_p105_p109_equal_blend_r1",
        "parent_ids": ["P105", "P109", "P136"],
        "contract": {
            "hypothesis": "a fixed 50/50 allocation blend of P105 and P109 preserves broad momentum alpha while reducing single-model concentration",
            "representations": {k: list(v) for k, v in REPRESENTATIONS.items()},
            "windows": ["full", "2018-01-31", "2022-01-31"],
            "costs_bps": list(COSTS),
            "matched_control": "same-universe equal weight",
            "opportunity_cost": ["standalone P105", "standalone P109"],
            "concentration_test": "remove five strongest blend-minus-equal-weight months",
            "no_weight_search": "50/50 fixed ex ante; no alternative blend ratios tested",
        },
        "results": {},
    }
    for rep, assets in REPRESENTATIONS.items():
        f = build(assets)
        out["results"][rep] = {}
        for start in (str(f.index.min().date()), "2018-01-31", "2022-01-31"):
            key = "full" if start == str(f.index.min().date()) else start
            out["results"][rep][key] = {str(bps): eval_window(f, start, bps) for bps in COSTS}
    cells = [out["results"][rep][w][str(bps)]["blend_excess_vs_equal_weight"] for rep in REPRESENTATIONS for w in ("full", "2018-01-31", "2022-01-31") for bps in COSTS]
    trims = [out["results"][rep][w]["25"]["five_strongest_blend_minus_equal_weight_months_removed_excess_cagr"] for rep in REPRESENTATIONS for w in ("2018-01-31", "2022-01-31")]
    if all(x > 0 for x in cells) and sum(x > 0 for x in trims) >= 4:
        decision = "FIXED_P105_P109_BLEND_BROADLY_SUPPORTED"
    elif sum(x > 0 for x in cells) >= 14:
        decision = "FIXED_P105_P109_BLEND_SUPPORTED_BUT_CONCENTRATED_OR_REPRESENTATION_MIXED"
    else:
        decision = "FIXED_P105_P109_BLEND_NOT_BROADLY_SUPPORTED"
    out["decision"] = decision
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p136_p105_p109_equal_blend_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {rep: {w: {"25_excess": out["results"][rep][w]["25"]["blend_excess_vs_equal_weight"], "50_excess": out["results"][rep][w]["50"]["blend_excess_vs_equal_weight"], "25_vs_p105": out["results"][rep][w]["25"]["blend_incremental_vs_p105"], "25_vs_p109": out["results"][rep][w]["25"]["blend_incremental_vs_p109"], "25_trim": out["results"][rep][w]["25"]["five_strongest_blend_minus_equal_weight_months_removed_excess_cagr"], "turn": out["results"][rep][w]["25"]["blend_annual_turnover"]} for w in ("full", "2018-01-31", "2022-01-31")} for rep in REPRESENTATIONS}
    print(json.dumps({"decision": decision, "results": compact}, sort_keys=True))


if __name__ == "__main__":
    main()
