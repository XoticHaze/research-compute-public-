from __future__ import annotations

import json
import time
from io import StringIO
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

START = "2007-01-01"
COST_ONE_WAY = 0.001
WINDOWS = ["2010-01-01", "2015-01-01", "2020-01-01", "2022-01-01"]
FOLDS = [
    ("2010-01-01", "2013-12-31"),
    ("2014-01-01", "2017-12-31"),
    ("2018-01-01", "2021-12-31"),
    ("2022-01-01", None),
]


def _month_end(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.to_period("M").to_timestamp("M")


def _parse_fred_dgs10(raw: str) -> pd.Series:
    frame = pd.read_csv(StringIO(raw))
    if frame.empty:
        raise RuntimeError("FRED DGS10 response empty")
    date_col = "DATE" if "DATE" in frame.columns else (
        "observation_date" if "observation_date" in frame.columns else frame.columns[0]
    )
    if "DGS10" in frame.columns:
        value_col = "DGS10"
    elif "VALUE" in frame.columns:
        value_col = "VALUE"
    else:
        raise RuntimeError(f"FRED DGS10 response missing expected value column: {list(frame.columns)}")
    frame[date_col] = pd.to_datetime(frame[date_col], utc=False)
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce") / 100.0
    out = frame.dropna(subset=[value_col]).set_index(date_col)[value_col]
    out.index = pd.DatetimeIndex(out.index).tz_localize(None)
    out = out.loc[out.index >= pd.Timestamp(START)]
    out.index = _month_end(out.index)
    out = out.groupby(level=0).last().sort_index()
    if out.empty or out.index.min() > pd.Timestamp("2007-01-31"):
        raise RuntimeError("FRED DGS10 coverage does not reach frozen start window")
    return out.rename("DGS10")


def _fred_dgs10() -> tuple[pd.Series, str]:
    # Transport hardening only. Both routes are official FRED downloads of the
    # exact frozen DGS10 series. No alternate Treasury series or source is used.
    routes = [
        (
            "fred_series_download",
            "https://fred.stlouisfed.org/series/DGS10/downloaddata/DGS10.csv",
        ),
        (
            "fred_graph_csv",
            f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10&cosd={START}",
        ),
    ]
    errors: list[str] = []
    for route_name, url in routes:
        for attempt in range(2):
            req = Request(
                url,
                headers={"User-Agent": "research-compute-public causal research/1.0"},
            )
            try:
                with urlopen(req, timeout=45) as response:
                    raw = response.read().decode("utf-8")
                return _parse_fred_dgs10(raw), route_name
            except Exception as exc:  # transport/format only; bounded and fail closed
                errors.append(f"{route_name}[{attempt + 1}]={type(exc).__name__}:{exc}")
                if attempt == 0:
                    time.sleep(2)
    raise RuntimeError("FRED DGS10 official transports failed: " + " | ".join(errors))


def _spy_cash_yield() -> pd.Series:
    hist = yf.Ticker("SPY").history(start=START, auto_adjust=False, actions=True)
    if hist.empty or "Close" not in hist.columns or "Dividends" not in hist.columns:
        raise RuntimeError("SPY raw history missing Close/Dividends")
    hist = hist.copy()
    hist.index = pd.DatetimeIndex(hist.index).tz_localize(None)
    cash_ttm = hist["Dividends"].rolling("365D", min_periods=1).sum()
    cash_yield = (cash_ttm / hist["Close"]).replace([np.inf, -np.inf], np.nan)
    cash_yield.index = _month_end(cash_yield.index)
    return cash_yield.groupby(level=0).last().sort_index()


def _monthly_total_returns() -> pd.DataFrame:
    close = yf.download(
        ["SPY", "BIL"],
        start=START,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )["Close"]
    if close.empty or not {"SPY", "BIL"}.issubset(close.columns):
        raise RuntimeError("SPY/BIL adjusted-close history unavailable")
    close.index = pd.DatetimeIndex(close.index).tz_localize(None)
    month = close.resample("ME").last().dropna()
    return month.pct_change().dropna()


def _stats(r: pd.Series) -> dict[str, float | None]:
    r = r.dropna()
    if len(r) < 12:
        return {"cagr": None, "max_dd": None, "sharpe": None}
    wealth = (1.0 + r).cumprod()
    years = len(r) / 12.0
    cagr = float(wealth.iloc[-1] ** (1.0 / years) - 1.0)
    max_dd = float((wealth / wealth.cummax() - 1.0).min())
    std = float(r.std(ddof=1))
    sharpe = None if std == 0.0 else float(np.sqrt(12.0) * r.mean() / std)
    return {"cagr": cagr, "max_dd": max_dd, "sharpe": sharpe}


def main() -> int:
    monthly = _monthly_total_returns()
    spy_cash_yield = _spy_cash_yield()
    dgs10, fred_transport = _fred_dgs10()
    print("FRED_DGS10_TRANSPORT=" + fred_transport)

    common = monthly.index.intersection(spy_cash_yield.index).intersection(dgs10.index)
    monthly = monthly.loc[common].copy()
    spread = (spy_cash_yield.loc[common] - dgs10.loc[common]).rename("cash_yield_spread")

    # Frozen chronology: completed month-end cash-distribution yield and DGS10
    # decide the following month's SPY-vs-BIL holding.
    signal = (spread > 0.0).shift(1).dropna().astype(bool)
    monthly = monthly.loc[signal.index]
    spread_used = spread.shift(1).loc[signal.index]
    turnover = signal.astype(int).diff().abs().fillna(signal.astype(int))
    candidate = pd.Series(
        np.where(signal, monthly["SPY"], monthly["BIL"]) - turnover * COST_ONE_WAY,
        index=signal.index,
        name="candidate",
    )

    if candidate.index.min() >= pd.Timestamp("2010-01-01"):
        raise RuntimeError("insufficient pre-2010 warm history")
    if spread_used.isna().any():
        raise RuntimeError("signal chronology contains missing prior-month spread")

    def slice_result(start: str, end: str | None = None) -> dict:
        idx = candidate.loc[start:end].index
        c = candidate.loc[idx]
        s = signal.loc[idx]
        spy = monthly.loc[idx, "SPY"]
        bil = monthly.loc[idx, "BIL"]
        if len(c) < 12:
            raise RuntimeError(f"insufficient months for slice {start}..{end}")

        # Ex-post exposure-matched static comparator isolates whether timing adds
        # value beyond the strategy's average SPY-vs-cash capital usage.
        risk_on = float(s.mean())
        matched = risk_on * spy + (1.0 - risk_on) * bil
        sc = _stats(c)
        sm = _stats(matched)
        ss = _stats(spy)
        return {
            "start": start,
            "end": end,
            "months": int(len(c)),
            "risk_on_fraction": risk_on,
            "candidate_after_cost_cagr": sc["cagr"],
            "matched_control_cagr": sm["cagr"],
            "excess_cagr_pp": 100.0 * (float(sc["cagr"]) - float(sm["cagr"])),
            "spy_cagr": ss["cagr"],
            "vs_spy_cagr_pp": 100.0 * (float(sc["cagr"]) - float(ss["cagr"])),
            "candidate_max_drawdown": sc["max_dd"],
            "control_max_drawdown": sm["max_dd"],
            "candidate_sharpe": sc["sharpe"],
            "control_sharpe": sm["sharpe"],
        }

    windows = {start: slice_result(start) for start in WINDOWS}
    folds = [slice_result(start, end) for start, end in FOLDS]
    positive_folds = sum(float(row["excess_cagr_pp"]) > 0.0 for row in folds)

    support = (
        float(windows["2010-01-01"]["excess_cagr_pp"]) > 0.0
        and float(windows["2020-01-01"]["excess_cagr_pp"]) > 0.0
        and positive_folds >= 3
        and float(windows["2010-01-01"]["candidate_max_drawdown"])
        >= float(windows["2010-01-01"]["control_max_drawdown"]) - 0.05
    )

    out = {
        "classification": (
            "SPY_CASH_YIELD_SPREAD_SUPPORTED" if support else "SPY_CASH_YIELD_SPREAD_REJECTED"
        ),
        "mechanism": (
            "prior completed month SPY trailing-365d cash dividends / unadjusted close "
            "minus same-month-end FRED DGS10; hold SPY next month when spread > 0 else BIL"
        ),
        "scientific_role": "A_NEW_ALPHA_DISCOVERY",
        "causal_information_time": "completed month-end only; one-month application lag",
        "source_semantics": {
            "equity_cash_distribution": "SPY historical cash dividends paid/ex-date through month-end via yfinance actions",
            "equity_yield_denominator": "SPY unadjusted close at completed month-end",
            "treasury_yield": "FRED DGS10 last available observation in completed month",
            "treasury_transport_used": fred_transport,
            "return_series": "yfinance auto-adjusted SPY and BIL monthly total-return proxies",
        },
        "cost_one_way": COST_ONE_WAY,
        "signal_threshold": "cash_yield_spread > 0; fixed, no magnitude tuning",
        "matched_control": "static SPY/BIL mix matched to realized risk-on fraction within each evaluation slice",
        "strongest_non_alpha_explanation": (
            "apparent value is only lower average equity exposure or a low-rate regime proxy, "
            "not timing information in the cash-yield spread"
        ),
        "support_rule": (
            "positive after-cost matched-control excess 2010+ and 2020+; >=3/4 positive chronology folds; "
            "2010+ max drawdown no worse than matched control by >5pp"
        ),
        "windows": windows,
        "folds": folds,
        "positive_folds": positive_folds,
        "signal_diagnostics": {
            "first_return_month": str(candidate.index.min().date()),
            "last_return_month": str(candidate.index.max().date()),
            "overall_risk_on_fraction": float(signal.mean()),
            "state_changes": int((turnover > 0).sum()),
            "prior_month_spread_min": float(spread_used.min()),
            "prior_month_spread_median": float(spread_used.median()),
            "prior_month_spread_max": float(spread_used.max()),
        },
        "protected_boundary": (
            "no ticker/lookback/dividend-window/yield-series/threshold/lag/horizon/cost/control/date rescue; "
            "terminal reject rotates A"
        ),
        "authority": {
            "research_only": True,
            "allocation": False,
            "ranking": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    print("RESULT_JSON=" + json.dumps(out, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
