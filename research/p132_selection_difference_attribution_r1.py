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


def top2(s: pd.Series) -> tuple[str, ...]:
    return tuple(sorted(s.dropna().sort_values(ascending=False).head(2).index))


def ann_mean(x: pd.Series) -> float:
    return float(pd.Series(x, dtype=float).dropna().mean() * 12)


def build(assets: tuple[str, ...]) -> pd.DataFrame:
    raw = yf.download(list(assets), start=START, auto_adjust=True, progress=False, threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.loc[:, list(assets)].dropna(how="all").astype(float)
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    last = pd.Timestamp(close.index.max()).normalize()
    monthly = close.resample("ME").last().loc[lambda x: x.index <= last]
    mom6 = monthly.pct_change(6)
    rows = []
    for i, dt in enumerate(monthly.index[:-1]):
        if i < 7:
            continue
        nxt = monthly.index[i + 1]
        m = mom6.loc[dt, list(assets)]
        if m.isna().any():
            continue
        hist = monthly.loc[:dt, list(assets)].pct_change(fill_method=None).tail(6)
        corr_pen = hist.corr().abs().replace(1.0, np.nan).mean(axis=1).fillna(1.0)
        z_mom = (m - m.mean()) / (m.std(ddof=0) or 1.0)
        sel_corr = top2(z_mom - corr_pen)
        mom12 = monthly.loc[dt, list(assets)] / monthly.shift(12).loc[dt, list(assets)] - 1
        dual_score = pd.DataFrame({"mom6": m, "mom12": mom12}).rank(pct=True).mean(axis=1)
        if dual_score.isna().any():
            continue
        sel_dual = top2(dual_score)
        nxt_r = monthly.loc[nxt, list(assets)] / monthly.loc[dt, list(assets)] - 1
        rc = float(nxt_r.loc[list(sel_corr)].mean())
        rd = float(nxt_r.loc[list(sel_dual)].mean())
        rows.append({
            "date": nxt,
            "corr_selection": list(sel_corr),
            "dual_selection": list(sel_dual),
            "selection_changed": sel_corr != sel_dual,
            "jaccard": len(set(sel_corr) & set(sel_dual)) / len(set(sel_corr) | set(sel_dual)),
            "corr_return": rc,
            "dual_return": rd,
            "incremental": rc - rd,
        })
    return pd.DataFrame(rows).set_index("date")


def summarize(f: pd.DataFrame, start: str) -> dict:
    g = f.loc[f.index >= pd.Timestamp(start)].copy()
    changed = g.loc[g.selection_changed]
    same = g.loc[~g.selection_changed]
    inc = g.incremental
    top5 = inc.sort_values(ascending=False).head(min(5, len(inc))).index
    trimmed = g.drop(index=top5)
    # Negative-control: align this month's penalty-conditioned selection outcome to next month's dual benchmark is the actual test;
    # no lagged/future information enters selection construction.
    return {
        "window": {"start": str(g.index.min().date()), "end": str(g.index.max().date()), "months": len(g)},
        "selection_changed_fraction": float(g.selection_changed.mean()),
        "mean_jaccard": float(g.jaccard.mean()),
        "annualized_incremental_mean_all_months": ann_mean(g.incremental),
        "annualized_incremental_mean_changed_months": ann_mean(changed.incremental) if len(changed) else None,
        "annualized_incremental_mean_same_months": ann_mean(same.incremental) if len(same) else None,
        "changed_month_count": int(len(changed)),
        "same_month_count": int(len(same)),
        "positive_incremental_changed_month_fraction": float((changed.incremental > 0).mean()) if len(changed) else None,
        "five_strongest_incremental_months_removed_annualized_mean": ann_mean(trimmed.incremental),
        "top5_incremental_share_of_total_positive_increment": float(g.loc[top5, "incremental"].clip(lower=0).sum() / max(g.incremental.clip(lower=0).sum(), 1e-12)),
    }


def main() -> None:
    out = {
        "schema": "research.p132_selection_difference_attribution_r1",
        "parent_ids": ["P109", "P105", "P131", "P132"],
        "contract": {
            "purpose": "causal attribution of whether the fixed correlation penalty changes top-2 choices versus fixed dual-horizon momentum and whether changed choices explain incremental return",
            "representations": {k: list(v) for k, v in REPRESENTATIONS.items()},
            "holdouts": ["2018-01-31", "2022-01-31"],
            "no_parameter_horizon_topk_or_weight_tuning": True,
            "important": "This is attribution, not promotion authority; no live or portfolio action follows automatically."
        },
        "results": {},
    }
    for name, assets in REPRESENTATIONS.items():
        f = build(assets)
        out["results"][name] = {start: summarize(f, start) for start in ("2018-01-31", "2022-01-31")}
    cells = [out["results"][rep][start] for rep in REPRESENTATIONS for start in ("2018-01-31", "2022-01-31")]
    changed_enough = sum(c["selection_changed_fraction"] >= 0.20 for c in cells)
    changed_positive = sum((c["annualized_incremental_mean_changed_months"] or 0) > 0 for c in cells)
    trimmed_positive = sum(c["five_strongest_incremental_months_removed_annualized_mean"] > 0 for c in cells)
    if changed_enough >= 5 and changed_positive >= 5 and trimmed_positive >= 4:
        decision = "CORRELATION_PENALTY_SELECTION_EFFECT_SUPPORTED"
    elif changed_enough >= 4 and changed_positive >= 4:
        decision = "CORRELATION_PENALTY_SELECTION_EFFECT_MIXED_OR_CONCENTRATED"
    else:
        decision = "CORRELATION_PENALTY_SELECTION_EFFECT_WEAK_OR_NOT_SEPARABLE"
    out["decision"] = decision
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p132_selection_difference_attribution_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"decision": decision, "cells": {rep: {start: out["results"][rep][start] for start in out["results"][rep]} for rep in out["results"]}}, sort_keys=True))


if __name__ == "__main__":
    main()
