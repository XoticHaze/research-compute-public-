from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

RISKY = ("SPY", "EFA", "EEM", "TLT", "GLD", "DBC", "VNQ")
ALL = (*RISKY, "BIL", "QQQ")
START = "2007-01-01"


def load() -> pd.DataFrame:
    data = yf.download(list(ALL), start=START, auto_adjust=True, progress=False, threads=False)
    if data.empty:
        raise RuntimeError("empty_download")
    close = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame()
    missing = [s for s in ALL if s not in close.columns]
    if missing:
        raise RuntimeError(f"missing:{missing}")
    close = close.loc[:, list(ALL)].dropna(how="all").astype(float)
    last = pd.Timestamp(close.index.max())
    if last.tzinfo is not None:
        last = last.tz_localize(None)
    monthly = close.resample("ME").last()
    return monthly.loc[monthly.index <= last.normalize()].copy()


def metrics(r: pd.Series) -> dict[str, float]:
    r = pd.Series(r, dtype=float).dropna()
    eq = (1 + r).cumprod()
    years = len(r) / 12
    cagr = float(eq.iloc[-1] ** (1 / years) - 1)
    ann = float(r.mean() * 12)
    vol = float(r.std(ddof=0) * math.sqrt(12))
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    return {"cagr": cagr, "annualized_mean": ann, "annualized_vol": vol, "sharpe_rf0": ann / vol if vol else float("nan"), "max_drawdown_monthly": mdd, "calmar": cagr / abs(mdd) if mdd < 0 else float("nan")}


def fold_count(c: pd.Series, b: pd.Series) -> tuple[int, list[dict[str, float]]]:
    folds = []
    for n, idx in enumerate(np.array_split(np.arange(len(c)), 5), 1):
        cm, bm = metrics(c.iloc[idx]), metrics(b.iloc[idx])
        folds.append({"fold": n, "candidate_cagr": cm["cagr"], "baseline_cagr": bm["cagr"], "excess_cagr": cm["cagr"] - bm["cagr"]})
    return sum(x["excess_cagr"] > 0 for x in folds), folds


def build(monthly: pd.DataFrame) -> pd.DataFrame:
    mom12 = monthly.pct_change(12)
    prev = {s: 0.0 for s in (*RISKY, "BIL")}
    rows = []
    for month in monthly.index:
        if month not in mom12.index or mom12.loc[month, list((*RISKY, "BIL"))].isna().any():
            continue
        loc = monthly.index.get_loc(month)
        if not isinstance(loc, (int, np.integer)) or loc + 1 >= len(monthly):
            continue
        nxt = monthly.index[loc + 1]
        realized = monthly.loc[nxt] / monthly.loc[month] - 1
        if realized.loc[list(ALL)].isna().any():
            continue
        hurdle = float(mom12.at[month, "BIL"])
        ranked = sorted(RISKY, key=lambda s: (float(mom12.at[month, s]), s), reverse=True)
        eligible = [s for s in ranked if float(mom12.at[month, s]) > hurdle][:3]
        w = {s: 0.0 for s in (*RISKY, "BIL")}
        for s in eligible:
            w[s] += 1.0 / 3.0
        w["BIL"] += (3 - len(eligible)) / 3.0
        turnover = 0.5 * sum(abs(w[s] - prev[s]) for s in w)
        gross = sum(w[s] * float(realized[s]) for s in w)
        risky_ew = float(realized.loc[list(RISKY)].mean())
        universe_ew = float(realized.loc[list((*RISKY, "BIL"))].mean())
        sixty_forty = 0.6 * float(realized["SPY"]) + 0.4 * float(realized["TLT"])
        rows.append({"date": nxt, "gross": gross, "turnover": turnover, "risky_ew": risky_ew, "universe_ew": universe_ew, "sixty_forty": sixty_forty, "spy": float(realized["SPY"]), "qqq": float(realized["QQQ"]), "bil": float(realized["BIL"]), "eligible_count": len(eligible)})
        prev = w
    return pd.DataFrame(rows).set_index("date")


def evaluate(frame: pd.DataFrame, bps: int) -> dict:
    c = frame.gross - frame.turnover * (bps / 10000)
    baseline = frame.risky_ew
    cm, bm = metrics(c), metrics(baseline)
    pos, folds = fold_count(c, baseline)
    return {
        "candidate": cm,
        "matched_risky_equal_weight": bm,
        "all_assets_including_bil_equal_weight": metrics(frame.universe_ew),
        "static_60_40_spy_tlt": metrics(frame.sixty_forty),
        "spy": metrics(frame.spy),
        "qqq": metrics(frame.qqq),
        "bil": metrics(frame.bil),
        "excess_cagr_vs_matched_risky_equal_weight": cm["cagr"] - bm["cagr"],
        "excess_cagr_vs_all_assets_equal_weight": cm["cagr"] - metrics(frame.universe_ew)["cagr"],
        "excess_cagr_vs_60_40": cm["cagr"] - metrics(frame.sixty_forty)["cagr"],
        "excess_cagr_vs_spy": cm["cagr"] - metrics(frame.spy)["cagr"],
        "excess_cagr_vs_qqq": cm["cagr"] - metrics(frame.qqq)["cagr"],
        "positive_folds_vs_matched": pos,
        "folds_vs_matched": folds,
    }


def main() -> None:
    monthly = load()
    frame = build(monthly)
    p25, p50 = evaluate(frame, 25), evaluate(frame, 50)
    source_hash = hashlib.sha256(monthly.reset_index().to_csv(index=False, float_format="%.10g").encode()).hexdigest()
    supported = p25["excess_cagr_vs_matched_risky_equal_weight"] > 0.01 and p25["positive_folds_vs_matched"] >= 3 and p25["candidate"]["sharpe_rf0"] >= p25["matched_risky_equal_weight"]["sharpe_rf0"] and p50["excess_cagr_vs_matched_risky_equal_weight"] > 0
    out = {
        "schema": "research.p82_crossasset_dual_momentum_bil_r1",
        "parent_ids": ["P82"],
        "scientific_contract": {
            "mechanism": "Rank seven liquid cross-asset ETFs by trailing 12-month total return; hold up to top three only when each beats BIL trailing 12-month return; unused thirds allocate to BIL.",
            "costs_bps": [25, 50],
            "matched_comparator": "same seven risky assets equal weight over exact monthly window",
            "opportunity_cost_controls": ["equal weight including BIL", "static 60/40 SPY/TLT", "SPY", "QQQ", "BIL"],
            "no_parameter_tuning": True,
            "complete_months_only": True,
        },
        "source": {"provider": "Yahoo Finance via yfinance", "normalized_monthly_panel_sha256": source_hash},
        "window": {"start": str(frame.index.min().date()), "end": str(frame.index.max().date()), "months": int(len(frame))},
        "mean_annual_turnover": float(frame.turnover.mean() * 12),
        "mean_eligible_count": float(frame.eligible_count.mean()),
        "costs": {"25": p25, "50": p50},
        "decision": "SUPPORTED_DUAL_MOMENTUM_REQUIRES_INDEPENDENT_VALIDATION" if supported else "NOT_SUPPORTED_DUAL_MOMENTUM_ROTATE",
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p82_crossasset_dual_momentum_bil_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"decision": out["decision"], "window": out["window"], "25": {"excess_vs_matched": p25["excess_cagr_vs_matched_risky_equal_weight"], "excess_vs_60_40": p25["excess_cagr_vs_60_40"], "excess_vs_spy": p25["excess_cagr_vs_spy"], "excess_vs_qqq": p25["excess_cagr_vs_qqq"], "folds": p25["positive_folds_vs_matched"], "candidate": p25["candidate"]}, "50": {"excess_vs_matched": p50["excess_cagr_vs_matched_risky_equal_weight"]}, "turnover": out["mean_annual_turnover"]}, sort_keys=True))


if __name__ == "__main__":
    main()
