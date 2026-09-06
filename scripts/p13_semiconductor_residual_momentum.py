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


def download() -> tuple[pd.DataFrame, pd.DataFrame]:
    tickers = UNIVERSE + BENCHMARKS
    raw = yf.download(
        tickers,
        start=START,
        end=END,
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if raw.empty:
        raise SystemExit("market download empty")
    if not isinstance(raw.columns, pd.MultiIndex):
        raise SystemExit("unexpected yfinance column shape")
    close = raw["Close"].copy().sort_index()
    volume = raw["Volume"].copy().sort_index()
    close = close.dropna(how="all")
    volume = volume.reindex(close.index)
    missing = [t for t in tickers if t not in close.columns]
    if missing:
        raise SystemExit(f"missing tickers: {missing}")
    return close, volume


def month_end_indices(index: pd.DatetimeIndex) -> list[int]:
    s = pd.Series(np.arange(len(index)), index=index)
    positions = s.groupby(index.to_period("M")).last().astype(int).tolist()
    return positions


def asset_return(close: pd.DataFrame, name: str, entry: int, exit_: int) -> float:
    a = close.iloc[entry][name]
    b = close.iloc[exit_][name]
    if not np.isfinite(a) or not np.isfinite(b) or a <= 0:
        return np.nan
    return float(b / a - 1.0)


def basket_return(close: pd.DataFrame, names: list[str], entry: int, exit_: int) -> float:
    vals = [asset_return(close, n, entry, exit_) for n in names]
    vals = [v for v in vals if np.isfinite(v)]
    return float(np.mean(vals)) if vals else np.nan


def build_periods(close: pd.DataFrame, volume: pd.DataFrame) -> list[Period]:
    positions = month_end_indices(close.index)
    out: list[Period] = []
    for j in range(len(positions) - 1):
        sig = positions[j]
        nxt = positions[j + 1]
        entry = sig + 1
        exit_ = nxt + 1
        if sig < LOOKBACK or entry >= len(close) or exit_ >= len(close):
            continue
        if close.index[entry] < pd.Timestamp("2019-01-01"):
            continue
        smh_now = close.iloc[sig]["SMH"]
        smh_then = close.iloc[sig - LOOKBACK]["SMH"]
        if not np.isfinite(smh_now) or not np.isfinite(smh_then) or smh_then <= 0:
            continue
        smh_mom = float(smh_now / smh_then - 1.0)
        raw_mom: dict[str, float] = {}
        residual: dict[str, float] = {}
        for name in UNIVERSE:
            now = close.iloc[sig][name]
            then = close.iloc[sig - LOOKBACK][name]
            if np.isfinite(now) and np.isfinite(then) and then > 0:
                m = float(now / then - 1.0)
                raw_mom[name] = m
                residual[name] = m - smh_mom
        if len(residual) < 8:
            continue
        residual_names = sorted(residual, key=residual.get, reverse=True)[:TOP_N]
        raw_names = sorted(raw_mom, key=raw_mom.get, reverse=True)[:TOP_N]
        r = basket_return(close, residual_names, entry, exit_)
        rm = basket_return(close, raw_names, entry, exit_)
        ew = basket_return(close, UNIVERSE, entry, exit_)
        smh = asset_return(close, "SMH", entry, exit_)
        qqq = asset_return(close, "QQQ", entry, exit_)
        if not all(np.isfinite(x) for x in (r, rm, ew, smh, qqq)):
            continue
        advs = []
        lo = max(0, sig - 60)
        for name in residual_names:
            dollars = close[name].iloc[lo : sig + 1] * volume[name].iloc[lo : sig + 1]
            med = float(dollars.replace([np.inf, -np.inf], np.nan).dropna().median())
            if np.isfinite(med):
                advs.append(med)
        adv10 = float(min(advs)) if advs else np.nan
        out.append(
            Period(
                signal_date=close.index[sig],
                entry_date=close.index[entry],
                exit_date=close.index[exit_],
                residual_names=residual_names,
                raw_names=raw_names,
                residual_gross=r,
                raw_gross=rm,
                equal_weight_gross=ew,
                smh_gross=smh,
                qqq_gross=qqq,
                residual_adv10=adv10,
            )
        )
    return out


def compounded(values: pd.Series) -> float:
    return float(np.prod(1.0 + values.to_numpy(dtype=float)) - 1.0)


def summarize(periods: list[Period]) -> dict:
    if len(periods) < MIN_SELECTIONS:
        raise SystemExit(f"insufficient periods: {len(periods)}")
    frame = pd.DataFrame([p.__dict__ for p in periods])
    frame["year"] = pd.to_datetime(frame["entry_date"]).dt.year
    first = pd.Timestamp(frame.entry_date.min()).date().isoformat()
    last = pd.Timestamp(frame.exit_date.max()).date().isoformat()
    gross = {
        "residual_top3": compounded(frame.residual_gross),
        "raw_momentum_top3": compounded(frame.raw_gross),
        "equal_weight_universe": compounded(frame.equal_weight_gross),
        "smh": compounded(frame.smh_gross),
        "qqq": compounded(frame.qqq_gross),
    }
    costs: dict[str, dict] = {}
    for c in COSTS_BPS:
        drag = c / 10000.0
        residual_net = frame.residual_gross - drag
        raw_net = frame.raw_gross - drag
        ew_net = frame.equal_weight_gross - drag
        costs[str(int(c))] = {
            "residual_top3_net": compounded(residual_net),
            "raw_momentum_top3_net": compounded(raw_net),
            "equal_weight_universe_net": compounded(ew_net),
            "residual_minus_raw_pp": 100.0 * (compounded(residual_net) - compounded(raw_net)),
            "residual_minus_equal_weight_pp": 100.0 * (compounded(residual_net) - compounded(ew_net)),
            "residual_minus_smh_pp": 100.0 * (compounded(residual_net) - gross["smh"]),
            "residual_minus_qqq_pp": 100.0 * (compounded(residual_net) - gross["qqq"]),
        }
    yearly = []
    for year, g in frame.groupby("year"):
        r25 = compounded(g.residual_gross - 0.0025)
        raw25 = compounded(g.raw_gross - 0.0025)
        ew25 = compounded(g.equal_weight_gross - 0.0025)
        smh = compounded(g.smh_gross)
        qqq = compounded(g.qqq_gross)
        yearly.append(
            {
                "year": int(year),
                "n": int(len(g)),
                "residual_net_25bps": r25,
                "raw_net_25bps": raw25,
                "equal_weight_net_25bps": ew25,
                "smh": smh,
                "qqq": qqq,
                "residual_minus_smh_pp": 100.0 * (r25 - smh),
                "residual_minus_equal_weight_pp": 100.0 * (r25 - ew25),
                "residual_minus_raw_pp": 100.0 * (r25 - raw25),
            }
        )
    full_years = [x for x in yearly if x["year"] <= 2025 and x["n"] >= 10]
    positive_smh_years = sum(x["residual_minus_smh_pp"] > 0 for x in full_years)
    c25 = costs["25"]
    c50 = costs["50"]
    promising = (
        c25["residual_minus_smh_pp"] > 0
        and c25["residual_minus_equal_weight_pp"] > 0
        and c25["residual_minus_raw_pp"] > 0
        and c50["residual_minus_smh_pp"] > 0
        and len(full_years) >= 6
        and positive_smh_years >= int(np.ceil(0.60 * len(full_years)))
    )
    decision = "SEMICONDUCTOR_RESIDUAL_MOMENTUM_PROMISING" if promising else "SEMICONDUCTOR_RESIDUAL_MOMENTUM_NOT_SUPPORTED"
    return {
        "schema": "p13-semiconductor-residual-momentum-v1",
        "question": "Does fixed 126-session stock-minus-SMH residual momentum improve scarce-capital top-3 semiconductor selection?",
        "window": {"first_entry": first, "last_exit": last, "periods": int(len(frame))},
        "universe": UNIVERSE,
        "signal": {"lookback_sessions": LOOKBACK, "top_n": TOP_N, "rebalance": "monthly, signal at month-end close, execute next trading-day close"},
        "gross_compounded": gross,
        "cost_assumption": "conservative full round-trip drag charged every monthly rebalance to active/equal-weight portfolios; SMH/QQQ shown gross as passive matched-window baselines",
        "cost_scenarios_bps": costs,
        "yearly_25bps": yearly,
        "full_years": len(full_years),
        "positive_smh_excess_full_years": positive_smh_years,
        "liquidity": {
            "min_selected_name_median_60d_dollar_volume_usd_p10": float(frame.residual_adv10.quantile(0.10)),
            "min_selected_name_median_60d_dollar_volume_usd_median": float(frame.residual_adv10.median()),
            "note": "liquidity context only; no market-impact model or historical constituent reconstruction",
        },
        "robustness_gaps": [
            "static current-name universe creates survivorship/constituent-history risk",
            "no taxes/borrow/market-impact model",
            "single frozen 126-session specification; no parameter search performed",
        ],
        "decision": decision,
    }


def main() -> None:
    close, volume = download()
    receipt = summarize(build_periods(close, volume))
    print("P13_SEMICONDUCTOR_RESIDUAL_MOMENTUM_RECEIPT=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
