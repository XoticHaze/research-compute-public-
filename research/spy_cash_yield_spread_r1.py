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
BOARD_H15_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15"
    "&series=bf17364827e38702b42a58cf8eaa3f78&lastobs=&from=&to="
    "&filetype=csv&label=include&layout=seriescolumn&type=package"
)
# Frozen source-equivalence anchors captured before this transport repair from
# the daily FRED DGS10 surface. They are identity checks only, never model inputs.
DGS10_PARITY_ANCHORS = {
    "2026-09-08": 0.0480,
    "2026-09-09": 0.0483,
    "2026-09-10": 0.0495,
    "2026-09-11": 0.0496,
    "2026-09-14": 0.0497,
}


def _month_end(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.to_period("M").to_timestamp("M")


def _board_h15_dgs10() -> tuple[pd.Series, dict[str, float]]:
    """Load the Board's underlying H.15 daily 10Y constant-maturity series.

    This is a source-transport repair after both official FRED download routes
    timed out on hosted public compute. The economic series remains the exact
    daily 10-year H.15 constant-maturity yield represented by FRED as DGS10.
    A pre-frozen recent-observation parity gate must pass before any economics.
    """
    raw = None
    errors: list[str] = []
    for attempt in range(3):
        req = Request(
            BOARD_H15_URL,
            headers={"User-Agent": "research-compute-public causal research/1.0"},
        )
        try:
            with urlopen(req, timeout=60) as response:
                raw = response.read().decode("utf-8-sig")
            break
        except Exception as exc:
            errors.append(f"board_h15[{attempt + 1}]={type(exc).__name__}:{exc}")
            if attempt < 2:
                time.sleep(2 ** attempt)
    if raw is None:
        raise RuntimeError("Board H15 DGS10 transport failed: " + " | ".join(errors))

    # Board H.15 package has five metadata rows, then the series-column header.
    frame = pd.read_csv(StringIO(raw), header=5, na_values=["ND"])
    if frame.empty or "RIFLGFCY10_N.B" not in frame.columns:
        raise RuntimeError(f"Board H15 package missing RIFLGFCY10_N.B: {list(frame.columns)}")
    date_col = frame.columns[0]
    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
    frame["RIFLGFCY10_N.B"] = pd.to_numeric(frame["RIFLGFCY10_N.B"], errors="coerce") / 100.0
    daily = frame.dropna(subset=[date_col, "RIFLGFCY10_N.B"]).set_index(date_col)["RIFLGFCY10_N.B"]
    daily.index = pd.DatetimeIndex(daily.index).tz_localize(None)
    daily = daily.sort_index()

    observed_anchors: dict[str, float] = {}
    for date_text, expected in DGS10_PARITY_ANCHORS.items():
        ts = pd.Timestamp(date_text)
        if ts not in daily.index:
            raise RuntimeError(f"Board H15 parity anchor missing: {date_text}")
        actual = float(daily.loc[ts])
        observed_anchors[date_text] = actual
        if not np.isclose(actual, expected, atol=1e-12, rtol=0.0):
            raise RuntimeError(
                f"Board H15/FRED DGS10 parity mismatch {date_text}: expected={expected} actual={actual}"
            )

    out = daily.loc[daily.index >= pd.Timestamp(START)].copy()
    if out.empty or out.index.min() > pd.Timestamp("2007-01-03"):
        raise RuntimeError("Board H15 DGS10 coverage does not reach frozen start window")
    out.index = _month_end(out.index)
    out = out.groupby(level=0).last().sort_index().rename("DGS10")
    return out, observed_anchors


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
    dgs10, parity_observed = _board_h15_dgs10()
    print("DGS10_SOURCE_PARITY=PASS")
    print("DGS10_TRANSPORT=board_h15_RIFLGFCY10_N.B")

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
            "minus same-month-end 10Y H15 constant-maturity yield; hold SPY next month when spread > 0 else BIL"
        ),
        "scientific_role": "A_NEW_ALPHA_DISCOVERY",
        "causal_information_time": "completed month-end only; one-month application lag",
        "source_semantics": {
            "equity_cash_distribution": "SPY historical cash dividends paid/ex-date through month-end via yfinance actions",
            "equity_yield_denominator": "SPY unadjusted close at completed month-end",
            "treasury_series": "Board H15 RIFLGFCY10_N.B, source-equivalent to FRED DGS10",
            "treasury_transport_used": "Board H15 Data Download Program",
            "source_parity_gate": {
                "status": "PASS",
                "frozen_fred_dgs10_anchors": DGS10_PARITY_ANCHORS,
                "board_h15_observed": parity_observed,
            },
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
