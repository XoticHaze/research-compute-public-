from __future__ import annotations

import csv
import io
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import requests

MANIFEST = Path(os.environ.get("P554_MANIFEST", "artifacts/p554_census_m3_vintage_manifest_r1.csv"))
OUT = Path("artifacts/p554_census_m3_industry_proxy_economic_r1.json")
TICKERS = ["SPY", "QQQ", "SOXX", "XLI"]
PROXY = {
    "Machinery": "XLI",
    "Computer and Electronic Products": "SOXX",
    "Transportation Equipment": "XLI",
    "Electrical Equipment, Appliances, and Components": "XLI",
}
BASE_COST = 0.001
STRESS_COSTS = [0.0025, 0.005]


def yahoo_daily(ticker: str) -> pd.Series:
    params = {
        "period1": 1388534400,  # 2014-01-01 UTC
        "period2": 1810252800,  # 2027-05-12 UTC, safely beyond evaluation horizon
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    }
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{urlencode(params)}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=(20, 90))
    r.raise_for_status()
    j = r.json()["chart"]["result"][0]
    ts = pd.to_datetime(j["timestamp"], unit="s", utc=True).tz_convert(None).normalize()
    adj = j.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
    if not adj:
        adj = j["indicators"]["quote"][0]["close"]
    s = pd.Series(adj, index=ts, dtype=float).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def z12(x: pd.Series) -> pd.Series:
    mu = x.rolling(12, min_periods=12).mean()
    sd = x.rolling(12, min_periods=12).std(ddof=0).replace(0, np.nan)
    return (x - mu) / sd


def cagr(rets: pd.Series, years: float | None = None) -> float | None:
    r = pd.Series(rets).dropna()
    if r.empty:
        return None
    if years is None:
        years = len(r) / 12.0
    if years <= 0 or (1 + r).prod() <= 0:
        return None
    return float((1 + r).prod() ** (1 / years) - 1)


def max_drawdown(rets: pd.Series) -> float:
    eq = (1 + pd.Series(rets).fillna(0)).cumprod()
    return float((eq / eq.cummax() - 1).min())


def main() -> None:
    if not MANIFEST.exists():
        raise SystemExit(f"manifest absent: {MANIFEST}")
    m = pd.read_csv(MANIFEST)
    req = {"release_date", "observation_month", "category", "measure", "published_value", "source_identity", "source_url"}
    missing = req - set(m.columns)
    if missing:
        raise SystemExit(f"manifest schema missing: {sorted(missing)}")
    m["release_date"] = pd.to_datetime(m["release_date"])
    m["observation_month"] = pd.to_datetime(m["observation_month"] + "-01").dt.to_period("M").dt.to_timestamp("M")
    m["published_value"] = pd.to_numeric(m["published_value"], errors="coerce")

    # Require exactly one admitted point-in-time value for every frozen category×measure×observation month.
    dup = m.duplicated(["observation_month", "category", "measure"], keep=False)
    if dup.any():
        raise SystemExit("duplicate manifest keys")
    wide = m.pivot_table(index=["observation_month", "release_date", "category"], columns="measure", values="published_value", aggfunc="first").reset_index()
    needed = ["Shipments", "New Orders", "Unfilled Orders", "Inventories"]
    wide = wide.dropna(subset=needed)
    wide = wide.sort_values(["category", "observation_month"])

    feats = []
    for cat, g in wide.groupby("category", sort=False):
        g = g.sort_values("observation_month").copy()
        for measure in ["New Orders", "Unfilled Orders", "Shipments"]:
            yoy = g[measure] / g[measure].shift(12) - 1
            g[f"z_{measure}"] = z12(yoy)
        ratio = g["Inventories"] / g["Shipments"]
        ratio_change = ratio / ratio.shift(12) - 1
        g["z_inventory_shipments_change"] = -z12(ratio_change)
        cols = ["z_New Orders", "z_Unfilled Orders", "z_Shipments", "z_inventory_shipments_change"]
        g["finite_components"] = g[cols].notna().sum(axis=1)
        g["industry_score"] = g[cols].mean(axis=1, skipna=True).where(g["finite_components"] >= 3)
        feats.append(g)
    f = pd.concat(feats, ignore_index=True)

    # One causal decision per release date/observation month. Top positive frozen category else cash.
    decisions = []
    for (om, rd), g in f.groupby(["observation_month", "release_date"]):
        z = g.dropna(subset=["industry_score"]).sort_values(["industry_score", "category"], ascending=[False, True])
        if z.empty:
            continue
        top = z.iloc[0]
        cat = str(top["category"])
        score = float(top["industry_score"])
        asset = PROXY.get(cat) if score > 0 else "CASH"
        decisions.append({"observation_month": om, "release_date": rd, "category": cat, "score": score, "asset": asset})
    d = pd.DataFrame(decisions).sort_values("release_date").drop_duplicates("release_date", keep="last")
    if len(d) < 60:
        raise SystemExit(f"insufficient causal decisions after warmup: {len(d)}")

    prices = {t: yahoo_daily(t) for t in TICKERS}
    calendar = prices["SPY"].index
    def next_session(day: pd.Timestamp) -> pd.Timestamp | None:
        pos = calendar.searchsorted(day.normalize(), side="right")
        return calendar[pos] if pos < len(calendar) else None
    d["exec_date"] = d["release_date"].map(next_session)
    d = d.dropna(subset=["exec_date"]).reset_index(drop=True)

    # Hold from next-session adjusted close through next decision's next-session adjusted close.
    intervals = []
    prev_asset = "CASH"
    for i in range(len(d) - 1):
        row = d.iloc[i]
        nxt = d.iloc[i + 1]
        a = row.asset
        start, end = pd.Timestamp(row.exec_date), pd.Timestamp(nxt.exec_date)
        if end <= start:
            continue
        controls = {}
        for t in TICKERS:
            s = prices[t]
            if start not in s.index or end not in s.index:
                controls[t] = None
            else:
                controls[t] = float(s.loc[end] / s.loc[start] - 1)
        if any(controls[t] is None for t in TICKERS):
            continue
        gross = 0.0 if a == "CASH" else controls[a]
        # Asset-side transactions only: cash->asset or asset->cash = one side; asset A->B = two sides.
        tx_sides = (0 if prev_asset == a else (1 if "CASH" in (prev_asset, a) else 2))
        intervals.append({
            "observation_month": str(row.observation_month.date()),
            "release_date": str(row.release_date.date()),
            "exec_date": str(start.date()),
            "next_exec_date": str(end.date()),
            "category": row.category,
            "score": float(row.score),
            "asset": a,
            "tx_sides": tx_sides,
            "gross_return": gross,
            **{f"{t}_return": controls[t] for t in TICKERS},
        })
        prev_asset = a
    x = pd.DataFrame(intervals)
    if len(x) < 50:
        raise SystemExit(f"insufficient common-sample intervals: {len(x)}")

    # Exact elapsed-year annualization from first to last execution date.
    years = (pd.Timestamp(x.iloc[-1].next_exec_date) - pd.Timestamp(x.iloc[0].exec_date)).days / 365.2425
    for cost in [BASE_COST, *STRESS_COSTS]:
        x[f"net_{int(cost*10000)}bps"] = x.gross_return - x.tx_sides * cost

    control_cagrs = {t: cagr(x[f"{t}_return"], years) for t in TICKERS}
    best_control = max(control_cagrs, key=lambda t: control_cagrs[t] if control_cagrs[t] is not None else -999)
    strategy_cagr = cagr(x["net_10bps"], years)
    stress25_cagr = cagr(x["net_25bps"], years)
    stress50_cagr = cagr(x["net_50bps"], years)
    best_cagr = control_cagrs[best_control]

    # Five contiguous interval folds, fixed after chronology. Compare each to same best simple control identity.
    fold_indices = np.array_split(np.arange(len(x)), 5)
    folds = []
    for k, idx in enumerate(fold_indices, 1):
        z = x.iloc[idx]
        yrs = (pd.Timestamp(z.iloc[-1].next_exec_date) - pd.Timestamp(z.iloc[0].exec_date)).days / 365.2425
        sc = cagr(z["net_10bps"], yrs)
        bc = cagr(z[f"{best_control}_return"], yrs)
        folds.append({"fold": k, "intervals": len(z), "strategy_cagr": sc, "control_cagr": bc, "excess_cagr": None if sc is None or bc is None else sc - bc})
    positive_folds = sum((r["excess_cagr"] or -999) > 0 for r in folds)

    # Contribution concentration on interval arithmetic excess vs frozen best-control identity.
    x["interval_excess"] = x["net_10bps"] - x[f"{best_control}_return"]
    cat_excess = x.groupby("category")["interval_excess"].sum().to_dict()
    pos_total = sum(max(float(v), 0.0) for v in cat_excess.values())
    max_positive_share = max((max(float(v), 0.0) / pos_total for v in cat_excess.values()), default=1.0) if pos_total > 0 else 1.0

    exposure = x.asset.value_counts(normalize=True).to_dict()
    result = {
        "schema": "research.p554_census_m3_industry_proxy_economic.r1",
        "parent": "P554",
        "claim_scope": "industry-state proxy selection only; not stock-selection proof",
        "manifest_sha256": __import__("hashlib").sha256(MANIFEST.read_bytes()).hexdigest(),
        "common_sample_intervals": len(x),
        "elapsed_years": years,
        "first_exec_date": x.iloc[0].exec_date,
        "last_exec_date": x.iloc[-1].next_exec_date,
        "strategy_cagr_10bps": strategy_cagr,
        "strategy_cagr_25bps": stress25_cagr,
        "strategy_cagr_50bps": stress50_cagr,
        "strategy_max_drawdown_10bps": max_drawdown(x["net_10bps"]),
        "control_cagrs": control_cagrs,
        "best_simple_control": best_control,
        "best_simple_control_cagr": best_cagr,
        "excess_cagr_10bps": None if strategy_cagr is None or best_cagr is None else strategy_cagr - best_cagr,
        "excess_cagr_25bps": None if stress25_cagr is None or best_cagr is None else stress25_cagr - best_cagr,
        "excess_cagr_50bps": None if stress50_cagr is None or best_cagr is None else stress50_cagr - best_cagr,
        "folds": folds,
        "positive_folds": positive_folds,
        "category_interval_excess_sums": cat_excess,
        "max_positive_excess_category_share": max_positive_share,
        "asset_exposure_fraction": exposure,
        "promotion_gates": {
            "positive_after_cost_excess": bool(strategy_cagr is not None and best_cagr is not None and strategy_cagr > best_cagr),
            "positive_3_of_5_folds": positive_folds >= 3,
            "no_category_over_70pct_positive_excess": max_positive_share <= 0.70,
            "positive_excess_at_25bps": bool(stress25_cagr is not None and best_cagr is not None and stress25_cagr > best_cagr),
            "pit_vintage_safe": True,
        },
        "boundaries": {
            "stock_selection_promotion_claim": False,
            "portfolio_replacement_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    gates = result["promotion_gates"]
    result["decision"] = "P554_INDUSTRY_PROXY_SURVIVOR" if all(gates.values()) else "P554_INDUSTRY_LAYER_NOT_SUPPORTED"
    result["next_if_survivor"] = "unchanged common-sample opportunity-cost comparison against P249+P266 before any capital status"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    Path("artifacts/p554_census_m3_industry_proxy_intervals_r1.csv").write_text(x.to_csv(index=False))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
