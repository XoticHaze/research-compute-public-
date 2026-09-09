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
    vol = float(r.std(ddof=0) * np.sqrt(12))
    dd = eq / eq.cummax() - 1
    return {"cagr": cagr, "vol": vol, "max_drawdown": float(dd.min())}


def top2(score: pd.Series) -> pd.Series:
    w = pd.Series(0.0, index=score.index)
    winners = score.sort_values(ascending=False).head(2).index
    w.loc[winners] = 0.5
    return w


def fold_wins(a: pd.Series, b: pd.Series, n: int = 3) -> int:
    wins = 0
    for idx in np.array_split(np.arange(len(a)), n):
        if len(idx) and metrics(a.iloc[idx])["cagr"] > metrics(b.iloc[idx])["cagr"]:
            wins += 1
    return wins


def build(assets: tuple[str, ...]) -> pd.DataFrame:
    raw = yf.download(list(assets), start=START, auto_adjust=True, progress=False, threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.loc[:, list(assets)].dropna(how="all").astype(float)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    last = pd.Timestamp(close.index.max()).normalize()
    m = close.resample("ME").last().loc[lambda x: x.index <= last]
    mom6 = m.pct_change(6)
    prev_true = pd.Series(0.0, index=assets)
    prev_placebo = pd.Series(0.0, index=assets)
    rows = []
    for i, dt in enumerate(m.index[:-1]):
        if i < 7:
            continue
        nxt = m.index[i + 1]
        mom = mom6.loc[dt, list(assets)]
        if mom.isna().any():
            continue
        hist = m.loc[:dt, list(assets)].pct_change(fill_method=None).tail(6)
        penalty = hist.corr().abs().replace(1.0, np.nan).mean(axis=1).fillna(1.0)
        z = (mom - mom.mean()) / (mom.std(ddof=0) or 1.0)
        w_true = top2(z - penalty)
        # Negative control: same penalty values, deterministically assigned to the next asset label.
        placebo_values = np.roll(penalty.to_numpy(), 1)
        placebo_penalty = pd.Series(placebo_values, index=penalty.index)
        w_placebo = top2(z - placebo_penalty)
        nr = m.loc[nxt, list(assets)] / m.loc[dt, list(assets)] - 1
        rows.append({
            "date": nxt,
            "true_gross": float((w_true * nr).sum()),
            "placebo_gross": float((w_placebo * nr).sum()),
            "true_turn": 0.5 * float((w_true - prev_true).abs().sum()),
            "placebo_turn": 0.5 * float((w_placebo - prev_placebo).abs().sum()),
            "equal_weight": float(nr.mean()),
            "selection_same": tuple(w_true[w_true > 0].index) == tuple(w_placebo[w_placebo > 0].index),
        })
        prev_true, prev_placebo = w_true, w_placebo
    return pd.DataFrame(rows).set_index("date")


def eval_cell(f: pd.DataFrame, start: str, bps: int) -> dict:
    g = f.loc[f.index >= pd.Timestamp(start)].copy()
    t = g.true_gross - g.true_turn * bps / 10000
    p = g.placebo_gross - g.placebo_turn * bps / 10000
    ew = g.equal_weight
    tm, pm, em = metrics(t), metrics(p), metrics(ew)
    inc = t - p
    drop = inc.sort_values(ascending=False).head(min(5, len(inc))).index
    keep = g.index.difference(drop)
    t2 = t.loc[keep]
    p2 = p.loc[keep]
    return {
        "window": {"start": str(g.index.min().date()), "end": str(g.index.max().date()), "months": len(g)},
        "true": tm,
        "label_placebo": pm,
        "equal_weight": em,
        "true_excess_vs_equal_weight": tm["cagr"] - em["cagr"],
        "incremental_cagr_true_vs_placebo": tm["cagr"] - pm["cagr"],
        "positive_chronological_folds_true_vs_placebo": fold_wins(t, p),
        "selection_difference_fraction": float((~g.selection_same).mean()),
        "five_strongest_true_minus_placebo_months_removed_incremental_cagr": metrics(t2)["cagr"] - metrics(p2)["cagr"],
        "true_annual_turnover": float(g.true_turn.mean() * 12),
        "placebo_annual_turnover": float(g.placebo_turn.mean() * 12),
    }


def main() -> None:
    out = {
        "schema": "research.p134_correlation_penalty_label_placebo_r1",
        "parent_ids": ["P109", "P117", "P125", "P130", "P132", "P134"],
        "contract": {
            "hypothesis": "P109's low-peer-correlation penalty contains asset-specific information beyond generic score perturbation",
            "negative_control": "cyclically rotate the exact contemporaneous penalty vector by one asset label; preserve momentum, top2, cadence and costs",
            "representations": {k: list(v) for k, v in REPRESENTATIONS.items()},
            "holdouts": ["2018-01-31", "2022-01-31"],
            "costs_bps": list(COSTS),
            "chronological_folds": 3,
            "concentration_test": "remove five strongest true-minus-placebo months",
            "no_parameter_horizon_topk_weight_or_penalty_magnitude_tuning": True,
        },
        "results": {},
    }
    for rep, assets in REPRESENTATIONS.items():
        f = build(assets)
        out["results"][rep] = {start: {str(bps): eval_cell(f, start, bps) for bps in COSTS} for start in ("2018-01-31", "2022-01-31")}
    cells = [out["results"][rep][start][str(bps)]["incremental_cagr_true_vs_placebo"] for rep in REPRESENTATIONS for start in ("2018-01-31", "2022-01-31") for bps in COSTS]
    folds = [out["results"][rep][start]["25"]["positive_chronological_folds_true_vs_placebo"] for rep in REPRESENTATIONS for start in ("2018-01-31", "2022-01-31")]
    trims = [out["results"][rep][start]["25"]["five_strongest_true_minus_placebo_months_removed_incremental_cagr"] for rep in REPRESENTATIONS for start in ("2018-01-31", "2022-01-31")]
    if all(x > 0 for x in cells) and sum(x >= 2 for x in folds) >= 5 and sum(x > 0 for x in trims) >= 4:
        decision = "ASSET_SPECIFIC_CORRELATION_PENALTY_CAUSAL_SIGNAL_SUPPORTED"
    elif sum(x > 0 for x in cells) >= 8 and sum(x >= 2 for x in folds) >= 4:
        decision = "ASSET_SPECIFIC_CORRELATION_PENALTY_EFFECT_MIXED_OR_CONCENTRATED"
    else:
        decision = "ASSET_SPECIFIC_CORRELATION_PENALTY_NOT_DISTINGUISHED_FROM_LABEL_PLACEBO"
    out["decision"] = decision
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p134_correlation_penalty_label_placebo_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    compact = {rep: {start: {"25_inc": out["results"][rep][start]["25"]["incremental_cagr_true_vs_placebo"], "25_folds": out["results"][rep][start]["25"]["positive_chronological_folds_true_vs_placebo"], "25_trim": out["results"][rep][start]["25"]["five_strongest_true_minus_placebo_months_removed_incremental_cagr"], "50_inc": out["results"][rep][start]["50"]["incremental_cagr_true_vs_placebo"]} for start in ("2018-01-31", "2022-01-31")} for rep in REPRESENTATIONS}
    print(json.dumps({"decision": decision, "results": compact}, sort_keys=True))


if __name__ == "__main__":
    main()
