"""Frozen CPER/GLD -> EEM/SPY monthly discriminator, source-only consumer.

This evaluator does not authenticate Yahoo source rights, first-seen issuer, or
trusted external placement. Its numeric predicate is NOT scientific admission.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ("CPER", "GLD", "EEM", "SPY")
SOURCE_START = "2011-09"
FROZEN_END = "2026-08"
ONE_WAY_COST = 0.001
WINDOWS = ("2012-01", "2018-01", "2022-01")
FOLDS = (
    ("2012-01", "2015-12"),
    ("2016-01", "2019-12"),
    ("2020-01", "2022-12"),
    ("2023-01", "2026-08"),
)
OUT = Path("artifacts/cper_gld_em_selection_r1.json")


def _wealth_stats(wealth):
    wealth = np.asarray(wealth, dtype=float)
    if not len(wealth) or not np.isfinite(wealth).all() or (wealth <= 0).any():
        raise ValueError("INVALID_FUNDED_WEALTH_PATH")
    peaks = np.maximum.accumulate(np.r_[1.0, wealth])[1:]
    return {
        "months": int(len(wealth)),
        "absolute_after_cost_return_pct": float(100.0 * (wealth[-1] - 1.0)),
        "cagr_pct": float(100.0 * (wealth[-1] ** (12.0 / len(wealth)) - 1.0)),
        "max_drawdown_pct": float(100.0 * np.min(wealth / peaks - 1.0)),
    }


def _evaluate_slice(panel):
    """Independent frozen window/fold, not a retuned signal or benchmark."""
    if panel.empty or panel[["EEM", "SPY", "signal"]].isna().any().any():
        raise ValueError("EMPTY_OR_INCOMPLETE_MONTHLY_SLICE")
    signal = panel["signal"].astype(bool)
    if not np.isfinite(panel[["EEM", "SPY"]].to_numpy(dtype=float)).all():
        raise ValueError("NONFINITE_MONTHLY_RETURN")
    if (panel[["EEM", "SPY"]] <= -1.0).any().any():
        raise ValueError("NONPOSITIVE_BUY_HOLD_WEALTH")
    # One 10bp entry leg; each full EEM <-> SPY switch has two one-way legs.
    changed = signal.ne(signal.shift(1))
    traded_legs = changed.astype(int) * 2
    traded_legs.iloc[0] = 1
    gross = pd.Series(
        np.where(signal, panel["EEM"], panel["SPY"]),
        index=panel.index, dtype=float,
    )
    candidate_net = gross - ONE_WAY_COST * traded_legs
    candidate_wealth = (1.0 + candidate_net).cumprod().to_numpy(dtype=float)
    # Frozen static buy-and-hold EEM/SPY mixture, not monthly-rebalanced.
    # The initial weights match THIS slice's realized EEM participation.
    participation = float(signal.mean())
    eem_hold = (1.0 + panel["EEM"]).cumprod().to_numpy(dtype=float)
    spy_hold = (1.0 + panel["SPY"]).cumprod().to_numpy(dtype=float)
    control_wealth = (
        participation * eem_hold + (1.0 - participation) * spy_hold
    ) * (1.0 - ONE_WAY_COST)
    candidate = _wealth_stats(candidate_wealth)
    control = _wealth_stats(control_wealth)
    return {
        "candidate": candidate,
        "matched_static_buy_hold_control": control,
        "eem_participation": participation,
        "switches": int(changed.iloc[1:].sum()),
        "one_way_traded_legs": int(traded_legs.sum()),
        "matched_excess_cagr_pp": candidate["cagr_pct"] - control["cagr_pct"],
        "relative_terminal_wealth_bp": float(
            10000.0 * (candidate_wealth[-1] / control_wealth[-1] - 1.0)
        ),
        "absolute_terminal_nav_difference_bp": float(
            10000.0 * (candidate_wealth[-1] - control_wealth[-1])
        ),
    }


def evaluate(monthly):
    expected = pd.period_range(SOURCE_START, FROZEN_END, freq="M")
    if not isinstance(monthly.index, pd.PeriodIndex):
        raise ValueError("MONTHLY_PERIOD_INDEX_REQUIRED")
    if monthly.index.has_duplicates:
        raise ValueError("DUPLICATE_SOURCE_MONTH")
    monthly = monthly.sort_index()
    missing_symbols = sorted(set(SYMBOLS) - set(monthly.columns))
    present = monthly.index.intersection(expected)
    missing_months = expected.difference(present)
    result = {
        "schema": "research.cper_gld_em_selection_source_only.r2",
        "workload_id": "CPER_GLD_EM_SELECTION_R1",
        "frozen": {
            "signal": "prior completed-month 3m CPER/GLD relative momentum > 0",
            "candidate": "next-month EEM when positive, otherwise SPY",
            "one_way_cost_bp": 10,
            "matched_control": "static EEM/SPY buy-and-hold, slice-specific realized EEM participation",
            "windows": list(WINDOWS),
            "folds": [list(f) for f in FOLDS],
            "support": "positive matched CAGR excess in all three windows, >=3/4 positive folds, <=5pp 2012+ drawdown deterioration",
            "end_month": FROZEN_END,
            "no_post_outcome_rescue": True,
        },
        "source": {
            "feed": "Yahoo Finance auto_adjust=True (unverified)",
            "issuer_authenticated": False,
            "vintage_and_rights_authenticated": False,
            "original_source_admitted": False,
            "observed_month_count": int(len(present)),
            "required_month_count": int(len(expected)),
            "missing_months": [str(x) for x in missing_months],
            "missing_symbols": missing_symbols,
            "issuer_cper_commenced_operations": "2011-11-15",
            "issuer_cper_source": "https://www.uscfinvestments.com/cper",
            "sec_cper_source": "https://www.sec.gov/Archives/edgar/data/1479247/000114420414014586/R29.htm",
        },
        "scientific_promotion_credit": False,
    }
    if missing_symbols or len(missing_months):
        result["decision"] = "SOURCE_COVERAGE_INCOMPLETE_NOT_NEGATIVE_ALPHA"
        return result
    prices = monthly.loc[expected, list(SYMBOLS)].astype(float)
    missing_values = {
        symbol: [str(p) for p in prices.index[prices[symbol].isna()]]
        for symbol in SYMBOLS
        if prices[symbol].isna().any()
    }
    result["source"]["missing_price_months_by_symbol"] = missing_values
    if missing_values:
        # CPER's documented 2011-11-15 inception makes Sep/Oct native
        # observations impossible. Never synthesize them or choose a
        # post-outcome warmup policy for the frozen 2012+ window.
        if (set(missing_values) == {"CPER"}
                and set(missing_values["CPER"]) == {"2011-09", "2011-10"}):
            result["decision"] = "PRE_INCEPTION_WARMUP_CONTRACT_UNRESOLVED_NOT_ALPHA"
        else:
            result["decision"] = "SOURCE_VALUES_INVALID_NOT_NEGATIVE_ALPHA"
        return result
    if not np.isfinite(prices.to_numpy()).all() or (prices <= 0).any().any():
        result["decision"] = "SOURCE_VALUES_INVALID_NOT_NEGATIVE_ALPHA"
        return result
    returns = prices[["EEM", "SPY"]].pct_change(fill_method=None)
    relative = (prices["CPER"] / prices["GLD"]).pct_change(
        periods=3, fill_method=None
    )
    signal = (relative > 0).shift(1)
    panel = returns.assign(signal=signal).loc["2012-01":FROZEN_END]
    if panel.isna().any().any():
        result["decision"] = "SIGNAL_OR_RETURN_CHRONOLOGY_INVALID"
        return result
    windows = {
        start: _evaluate_slice(panel.loc[start:FROZEN_END])
        for start in WINDOWS
    }
    folds = [
        {"start": a, "end": b, **_evaluate_slice(panel.loc[a:b])}
        for a, b in FOLDS
    ]
    positive_folds = sum(f["matched_excess_cagr_pp"] > 0 for f in folds)
    control_dd = windows["2012-01"]["matched_static_buy_hold_control"]["max_drawdown_pct"]
    candidate_dd = windows["2012-01"]["candidate"]["max_drawdown_pct"]
    mechanical_support = (
        all(w["matched_excess_cagr_pp"] > 0 for w in windows.values())
        and positive_folds >= 3
        and candidate_dd >= control_dd - 5.0
    )
    result.update({
        "decision": "SOURCE_ONLY_NOT_SCIENTIFICALLY_ADMITTED",
        "mechanical_support_predicate_unadmitted": bool(mechanical_support),
        "windows": windows,
        "folds": folds,
        "positive_folds": int(positive_folds),
    })
    return result


def self_test():
    idx = pd.period_range(SOURCE_START, FROZEN_END, freq="M")
    n = len(idx)
    prices = pd.DataFrame({
        "CPER": 20.0 * np.power(1.002, np.arange(n)),
        "GLD": np.full(n, 100.0),
        "EEM": 40.0 * np.power(1.006, np.arange(n)),
        "SPY": 100.0 * np.power(1.004, np.arange(n)),
    }, index=idx)
    complete = evaluate(prices)
    assert complete["decision"] == "SOURCE_ONLY_NOT_SCIENTIFICALLY_ADMITTED"
    assert complete["source"]["missing_months"] == []
    assert complete["scientific_promotion_credit"] is False
    incomplete = evaluate(prices.drop(pd.Period("2014-06", freq="M")))
    assert incomplete["decision"] == "SOURCE_COVERAGE_INCOMPLETE_NOT_NEGATIVE_ALPHA"
    assert "2014-06" in incomplete["source"]["missing_months"]
    inception_limited = prices.copy()
    inception_limited.loc["2011-09":"2011-10", "CPER"] = np.nan
    inception_result = evaluate(inception_limited)
    assert inception_result["decision"] == "PRE_INCEPTION_WARMUP_CONTRACT_UNRESOLVED_NOT_ALPHA"
    assert inception_result["source"]["missing_price_months_by_symbol"]["CPER"] == ["2011-09", "2011-10"]
    test = pd.DataFrame({
        "signal": [True, False, False],
        "EEM": [0.10, 0.00, 0.00],
        "SPY": [0.00, 0.10, 0.10],
    }, index=pd.period_range("2024-01", periods=3, freq="M"))
    scored = _evaluate_slice(test)
    assert scored["switches"] == 1
    assert scored["one_way_traded_legs"] == 3
    candidate_expected = (1.10 - 0.001) * (1.10 - 0.002) * 1.10
    control_expected = (1.10 / 3.0 + 2.0 * 1.21 / 3.0) * 0.999
    assert math.isclose(
        scored["candidate"]["absolute_after_cost_return_pct"],
        100.0 * (candidate_expected - 1.0), abs_tol=1e-10
    )
    assert math.isclose(
        scored["matched_static_buy_hold_control"]["absolute_after_cost_return_pct"],
        100.0 * (control_expected - 1.0), abs_tol=1e-10
    )
    assert math.isclose(scored["eem_participation"], 1.0 / 3.0)
    print("CPER_GLD_EM_SOURCE_ONLY_SELF_TEST=PASS")


def main():
    if "--self-test" in sys.argv:
        self_test()
        return
    import yfinance as yf
    data = yf.download(
        list(SYMBOLS), start="2011-01-01", end="2026-09-01",
        auto_adjust=True, progress=False, threads=False
    )
    close = data["Close"] if "Close" in data else pd.DataFrame()
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame()
    monthly = close.resample("ME").last()
    monthly.index = monthly.index.to_period("M")
    result = evaluate(monthly)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
