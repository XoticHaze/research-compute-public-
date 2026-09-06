from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

UNIVERSE = ["NVDA", "AMD", "AVGO", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "MU", "ADI"]
BENCHMARKS = ["SMH", "QQQ"]
START = "2018-01-01"
END = "2026-09-05"
LOOKBACK = 126
TOP_N = 3
COSTS_BPS = [10.0, 25.0, 50.0]
MIN_SELECTIONS = 48
MIN_OBS = 100


@dataclass
class Period:
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    residual_names: list[str]
    raw_names: list[str]
    residual_gross: float
    raw_gross: float
    equal_weight_gross: float
    smh_gross: float
    qqq_gross: float
    residual_adv10: float
    ordering_changed: bool


def download() -> tuple[pd.DataFrame, pd.DataFrame]:
    tickers = UNIVERSE + BENCHMARKS
    raw = yf.download(tickers, start=START, end=END, auto_adjust=True, progress=False, group_by="column", threads=True)
    if raw.empty or not isinstance(raw.columns, pd.MultiIndex):
        raise SystemExit("market download unavailable or unexpected")
    close = raw["Close"].copy().sort_index().dropna(how="all")
    volume = raw["Volume"].copy().sort_index().reindex(close.index)
    missing = [t for t in tickers if t not in close.columns]
    if missing:
        raise SystemExit(f"missing tickers: {missing}")
    return close, volume


def month_end_indices(index: pd.DatetimeIndex) -> list[int]:
    s = pd.Series(np.arange(len(index)), index=index)
    return s.groupby(index.to_period("M")).last().astype(int).tolist()


def asset_return(close: pd.DataFrame, name: str, entry: int, exit_: int) -> float:
    a, b = close.iloc[entry][name], close.iloc[exit_][name]
    if not np.isfinite(a) or not np.isfinite(b) or a <= 0:
        return np.nan
    return float(b / a - 1.0)


def basket_return(close: pd.DataFrame, names: list[str], entry: int, exit_: int) -> float:
    vals = [asset_return(close, n, entry, exit_) for n in names]
    vals = [v for v in vals if np.isfinite(v)]
    return float(np.mean(vals)) if vals else np.nan


def stock_specific_residual_score(close: pd.DataFrame, name: str, sig: int) -> float:
    px = close[[name, "SMH"]].iloc[sig - LOOKBACK : sig + 1].dropna()
    if len(px) < MIN_OBS + 1:
        return np.nan
    rets = px.pct_change().dropna()
    if len(rets) < MIN_OBS:
        return np.nan
    x = rets["SMH"].to_numpy(dtype=float)
    y = rets[name].to_numpy(dtype=float)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or float(np.var(x)) <= 0:
        return np.nan
    beta = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))
    alpha = float(np.mean(y) - beta * np.mean(x))
    residuals = y - (alpha + beta * x)
    return float(np.sum(residuals))


def build_periods(close: pd.DataFrame, volume: pd.DataFrame) -> list[Period]:
    out: list[Period] = []
    positions = month_end_indices(close.index)
    for j in range(len(positions) - 1):
        sig, nxt = positions[j], positions[j + 1]
        entry, exit_ = sig + 1, nxt + 1
        if sig < LOOKBACK or entry >= len(close) or exit_ >= len(close):
            continue
        if close.index[entry] < pd.Timestamp("2019-01-01"):
            continue
        residual, raw = {}, {}
        for name in UNIVERSE:
            now, then = close.iloc[sig][name], close.iloc[sig - LOOKBACK][name]
            if np.isfinite(now) and np.isfinite(then) and then > 0:
                raw[name] = float(now / then - 1.0)
            score = stock_specific_residual_score(close, name, sig)
            if np.isfinite(score):
                residual[name] = score
        common = set(raw).intersection(residual)
        if len(common) < 8:
            continue
        residual_names = sorted(common, key=lambda n: residual[n], reverse=True)[:TOP_N]
        raw_names = sorted(common, key=lambda n: raw[n], reverse=True)[:TOP_N]
        vals = [
            basket_return(close, residual_names, entry, exit_),
            basket_return(close, raw_names, entry, exit_),
            basket_return(close, sorted(common), entry, exit_),
            asset_return(close, "SMH", entry, exit_),
            asset_return(close, "QQQ", entry, exit_),
        ]
        if not all(np.isfinite(v) for v in vals):
            continue
        lo = max(0, sig - 60)
        advs = []
        for name in residual_names:
            dollars = close[name].iloc[lo : sig + 1] * volume[name].iloc[lo : sig + 1]
            med = float(dollars.replace([np.inf, -np.inf], np.nan).dropna().median())
            if np.isfinite(med):
                advs.append(med)
        out.append(Period(
            signal_date=close.index[sig], entry_date=close.index[entry], exit_date=close.index[exit_],
            residual_names=residual_names, raw_names=raw_names,
            residual_gross=vals[0], raw_gross=vals[1], equal_weight_gross=vals[2], smh_gross=vals[3], qqq_gross=vals[4],
            residual_adv10=float(min(advs)) if advs else np.nan,
            ordering_changed=residual_names != raw_names,
        ))
    return out


def compounded(values: pd.Series) -> float:
    return float(np.prod(1.0 + values.to_numpy(dtype=float)) - 1.0)


def summarize(periods: list[Period]) -> dict:
    if len(periods) < MIN_SELECTIONS:
        raise SystemExit(f"insufficient periods: {len(periods)}")
    frame = pd.DataFrame([p.__dict__ for p in periods])
    frame["year"] = pd.to_datetime(frame.entry_date).dt.year
    gross = {
        "stock_specific_residual_top3": compounded(frame.residual_gross),
        "raw_momentum_top3": compounded(frame.raw_gross),
        "equal_weight_universe": compounded(frame.equal_weight_gross),
        "smh": compounded(frame.smh_gross),
        "qqq": compounded(frame.qqq_gross),
    }
    costs = {}
    for c in COSTS_BPS:
        drag = c / 10000.0
        rr, raw, ew = compounded(frame.residual_gross - drag), compounded(frame.raw_gross - drag), compounded(frame.equal_weight_gross - drag)
        costs[str(int(c))] = {
            "residual_net": rr,
            "raw_net": raw,
            "equal_weight_net": ew,
            "residual_minus_raw_pp": 100.0 * (rr - raw),
            "residual_minus_equal_weight_pp": 100.0 * (rr - ew),
            "residual_minus_smh_pp": 100.0 * (rr - gross["smh"]),
            "residual_minus_qqq_pp": 100.0 * (rr - gross["qqq"]),
        }
    yearly = []
    for year, g in frame.groupby("year"):
        rr = compounded(g.residual_gross - 0.0025)
        raw = compounded(g.raw_gross - 0.0025)
        smh = compounded(g.smh_gross)
        yearly.append({"year": int(year), "n": int(len(g)), "residual_net_25bps": rr, "raw_net_25bps": raw, "smh": smh,
                       "residual_minus_raw_pp": 100.0 * (rr - raw), "residual_minus_smh_pp": 100.0 * (rr - smh)})
    full_years = [x for x in yearly if x["year"] <= 2025 and x["n"] >= 10]
    positive_smh = sum(x["residual_minus_smh_pp"] > 0 for x in full_years)
    positive_raw = sum(x["residual_minus_raw_pp"] > 0 for x in full_years)
    c25, c50 = costs["25"], costs["50"]
    changed_fraction = float(frame.ordering_changed.mean())
    promising = (
        changed_fraction >= 0.25
        and c25["residual_minus_raw_pp"] > 0
        and c25["residual_minus_smh_pp"] > 0
        and c25["residual_minus_equal_weight_pp"] > 0
        and c50["residual_minus_smh_pp"] > 0
        and len(full_years) >= 6
        and positive_smh >= int(np.ceil(0.60 * len(full_years)))
        and positive_raw >= int(np.ceil(0.60 * len(full_years)))
    )
    return {
        "schema": "p13-semiconductor-stock-specific-residual-v1",
        "question": "Does prior-only stock-specific beta residual momentum change semiconductor ordering and improve scarce-capital top-3 economics?",
        "window": {"first_entry": pd.Timestamp(frame.entry_date.min()).date().isoformat(), "last_exit": pd.Timestamp(frame.exit_date.max()).date().isoformat(), "periods": int(len(frame))},
        "signal": {"lookback_sessions": LOOKBACK, "top_n": TOP_N, "residual_model": "daily stock return = alpha + beta * SMH return using only prior 126 sessions; score=sum prior-window residuals"},
        "ordering_changed_period_fraction": changed_fraction,
        "gross_compounded": gross,
        "cost_scenarios_bps": costs,
        "yearly_25bps": yearly,
        "full_years": len(full_years),
        "positive_smh_excess_full_years": positive_smh,
        "positive_raw_excess_full_years": positive_raw,
        "liquidity": {"min_selected_name_median_60d_dollar_volume_usd_p10": float(frame.residual_adv10.quantile(0.10)), "min_selected_name_median_60d_dollar_volume_usd_median": float(frame.residual_adv10.median())},
        "robustness_gaps": ["static current-name universe creates survivorship/constituent-history risk and blocks promotion", "no taxes/market-impact model", "single frozen 126-session specification; no parameter search"],
        "decision": "STOCK_SPECIFIC_RESIDUAL_PROMISING_BUT_NOT_PROMOTABLE" if promising else "STOCK_SPECIFIC_RESIDUAL_NOT_SUPPORTED",
    }


def main() -> None:
    close, volume = download()
    print("P13_STOCK_SPECIFIC_RESIDUAL_RECEIPT=" + json.dumps(summarize(build_periods(close, volume)), sort_keys=True))


if __name__ == "__main__":
    main()
