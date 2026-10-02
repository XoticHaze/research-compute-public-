"""Independent-vendor UUP signal replication of the frozen UUP->SPY/EFA regime.

Frozen mechanism: prior completed calendar-month UUP return >= +2% => SPY next
month, otherwise EFA. UUP signal history is sourced from Stooq CSV directly.
SPY/EFA outcome returns remain Yahoo adjusted-close so the only changed axis is
UUP signal-vendor provenance. No parameter/date/control rescue is permitted.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import pandas as pd
import requests

END = "2026-10-01"
COST = 0.001


def stooq_uup() -> pd.Series:
    response = requests.get(
        "https://stooq.com/q/d/l/",
        params={"s": "uup.us", "d1": "20110101", "d2": "20261001", "i": "d"},
        headers={"User-Agent": "Mozilla/5.0 alpha-research/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    body = response.text.strip()
    if not body or body == "N/D" or "Date,Open,High,Low,Close" not in body:
        raise RuntimeError("stooq_uup_csv_unavailable_or_key_required")
    frame = pd.read_csv(io.StringIO(body))
    if not {"Date", "Close"}.issubset(frame.columns):
        raise RuntimeError("stooq_uup_csv_schema_rejected")
    idx = pd.to_datetime(frame["Date"], errors="coerce")
    close = pd.to_numeric(frame["Close"], errors="coerce")
    series = pd.Series(close.to_numpy(), index=idx, dtype="float64").dropna().sort_index()
    series = series[~series.index.duplicated(keep="last")].rename("UUP_STOOQ")
    if series.empty or series.index.min() > pd.Timestamp("2012-01-03") or series.index.max() < pd.Timestamp("2026-08-01"):
        raise RuntimeError("stooq_uup_coverage_insufficient")
    return series


def yahoo_adjusted(ticker: str) -> pd.Series:
    p1 = int(dt.datetime(2011, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime(2026, 10, 2, tzinfo=dt.timezone.utc).timestamp())
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        params={"period1": p1, "period2": p2, "interval": "1d", "events": "history", "includeAdjustedClose": "true"},
        headers={"User-Agent": "Mozilla/5.0 alpha-research/1.0"},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()["chart"]["result"][0]
    idx = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(None).normalize()
    values = result["indicators"]["adjclose"][0]["adjclose"]
    series = pd.Series(values, index=idx, dtype="float64").dropna().rename(ticker)
    if series.empty:
        raise RuntimeError(f"yahoo_adjusted_empty:{ticker}")
    return series


def stats(ret: pd.Series) -> dict[str, float | int]:
    ret = ret.dropna()
    years = len(ret) / 12.0
    eq = (1.0 + ret).cumprod()
    return {
        "cagr": float(eq.iloc[-1] ** (1.0 / years) - 1.0),
        "max_drawdown": float((eq / eq.cummax() - 1.0).min()),
        "months": int(len(ret)),
    }


def main() -> None:
    uup = stooq_uup()
    spy = yahoo_adjusted("SPY")
    efa = yahoo_adjusted("EFA")

    uup_month = uup.resample("ME").last()
    outcomes = pd.concat([spy, efa], axis=1).dropna().resample("ME").last().pct_change()
    common = outcomes.index.intersection(uup_month.index)
    outcomes = outcomes.loc[common]
    uup_month = uup_month.loc[common]
    uup_ret = uup_month.pct_change()
    signal = (uup_ret.shift(1) >= 0.02).astype(float)
    gross = signal * outcomes["SPY"] + (1.0 - signal) * outcomes["EFA"]
    turnover = signal.diff().abs().fillna(signal.iloc[0])
    net = gross - turnover * COST

    def evaluate(start: str, end: str) -> dict[str, object]:
        rr = net.loc[start:end]
        ss = signal.loc[start:end]
        raw = outcomes.loc[start:end]
        p = float(ss.mean())
        matched = p * raw["SPY"] + (1.0 - p) * raw["EFA"]
        cs, ms = stats(rr), stats(matched)
        return {
            "candidate": cs,
            "matched": ms,
            "spy_participation": p,
            "excess_cagr_pp": 100.0 * (float(cs["cagr"]) - float(ms["cagr"])),
        }

    windows = {
        "2012_plus": evaluate("2012-01-01", END),
        "2018_plus": evaluate("2018-01-01", END),
        "2022_plus": evaluate("2022-01-01", END),
    }
    blocks = {
        "2012_2015": evaluate("2012-01-01", "2015-12-31"),
        "2016_2019": evaluate("2016-01-01", "2019-12-31"),
        "2020_2022": evaluate("2020-01-01", "2022-12-31"),
        "2023_plus": evaluate("2023-01-01", END),
    }
    positive = sum(float(v["excess_cagr_pp"]) > 0.0 for v in blocks.values())
    long = windows["2012_plus"]
    support = (
        all(float(v["excess_cagr_pp"]) > 0.0 for v in windows.values())
        and positive >= 3
        and float(long["candidate"]["max_drawdown"]) >= float(long["matched"]["max_drawdown"]) - 0.05
    )
    output = {
        "schema": "research.uup_efa_dollar_regime_stooq_signal_replication_r4.v1",
        "frozen_mechanism": "prior completed calendar-month UUP return >= +2% => SPY next month; otherwise EFA",
        "signal_vendor": "Stooq direct CSV UUP.US",
        "outcome_vendor": "Yahoo chart adjusted-close SPY/EFA (held fixed from prior replication)",
        "independence_scope": "UUP signal vendor only; outcome/benchmark return source deliberately held fixed",
        "cost_one_way": COST,
        "matched_control": "static SPY/EFA mixture matched to realized SPY participation",
        "signal_coverage": {
            "first": uup.index.min().date().isoformat(),
            "last": uup.index.max().date().isoformat(),
            "daily_rows": int(len(uup)),
        },
        "windows": windows,
        "blocks": blocks,
        "positive_blocks": positive,
        "decision": "UUP_EFA_DOLLAR_REGIME_INDEPENDENT_SIGNAL_VENDOR_SUPPORTED" if support else "UUP_EFA_DOLLAR_REGIME_INDEPENDENT_SIGNAL_VENDOR_REJECTED",
        "protected_boundary": "no UUP threshold/proxy/regional ETF/horizon/cost/date/control/block rescue",
        "scientific_consequence": "If supported, vendor dependence of the UUP signal is materially reduced; if rejected, release this confirmation path without retuning.",
    }
    print("RESULT_JSON=" + json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
