#!/usr/bin/env python3
import hashlib
import json
import math
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START = "2000-01-01"
END = "2026-09-08"
COSTS = (10, 25, 50)
ASSET = os.environ["P36_ASSET"].strip().upper()
CHILD = os.environ["P36_CHILD"].strip().upper()
if ASSET not in {"SOXX", "XSD"}:
    raise SystemExit(f"unsupported P36_ASSET={ASSET}")
if CHILD not in {"C2", "C3"}:
    raise SystemExit(f"unsupported P36_CHILD={CHILD}")


def get(url, attempts=5):
    last = None
    for i in range(attempts):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 research-compute"})
            with urlopen(req, timeout=30) as response:
                raw = response.read()
            if len(raw) < 200:
                raise RuntimeError(f"short_response={len(raw)}")
            return raw, i + 1
        except Exception as exc:
            last = exc
            time.sleep(min(2**i, 8))
    raise RuntimeError(f"source_fetch_failed:{last}")


def yahoo(symbol):
    p1 = int(pd.Timestamp(START, tz="UTC").timestamp())
    p2 = int(pd.Timestamp(END, tz="UTC").timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true"
    )
    raw, attempt = get(url)
    payload = json.loads(raw)["chart"]["result"][0]
    idx = pd.to_datetime(payload["timestamp"], unit="s", utc=True).tz_convert(None)
    vals = (
        payload.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
        or payload["indicators"]["quote"][0]["close"]
    )
    series = pd.Series(vals, index=idx, dtype=float).dropna().sort_index()
    if len(series) < 500:
        raise RuntimeError(f"{symbol}_insufficient_rows={len(series)}")
    return series, {
        "url": url,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": int(len(series)),
        "attempt": attempt,
        "first_observation": str(series.index.min().date()),
        "last_observation": str(series.index.max().date()),
        "source_class": "YAHOO_CHART_V8_EXTERNAL_RESEARCH_NOT_MM_CANONICAL",
    }


def cagr(returns):
    returns = pd.Series(returns).dropna()
    total = float((1 + returns).prod())
    return total ** (12 / len(returns)) - 1 if len(returns) and total > 0 else -1.0


def max_drawdown(returns):
    equity = (1 + pd.Series(returns).fillna(0)).cumprod()
    return float((equity / equity.cummax() - 1).min())


def ann_vol(returns):
    return float(pd.Series(returns).std(ddof=1) * math.sqrt(12))


def folds(frame, strategy_col, control_col):
    out = []
    for n, idx in enumerate(np.array_split(np.arange(len(frame)), 5), 1):
        part = frame.iloc[idx]
        strategy = cagr(part[strategy_col])
        control = cagr(part[control_col])
        out.append(
            {
                "fold": n,
                "start": str(part.index.min().date()),
                "end": str(part.index.max().date()),
                "strategy_cagr": strategy,
                "control_cagr": control,
                "excess_cagr": strategy - control,
            }
        )
    return out


def yearly(frame, strategy_col, control_col):
    out = []
    for year, part in frame.groupby(frame.index.year):
        if len(part) < 6:
            continue
        sr = float((1 + part[strategy_col]).prod() - 1)
        cr = float((1 + part[control_col]).prod() - 1)
        out.append({"year": int(year), "strategy_return": sr, "control_return": cr, "excess": sr - cr})
    return out


def main():
    symbols = [ASSET, "QQQ", "SPY", "SMH"]
    prices = {}
    sources = {}
    for symbol in symbols:
        prices[symbol], sources[symbol] = yahoo(symbol)

    common_last = min(series.index.max() for series in prices.values())
    current_month_end = common_last.normalize() + pd.offsets.MonthEnd(0)
    monthly = pd.concat({k: v.resample("ME").last() for k, v in prices.items()}, axis=1).dropna()
    if common_last.normalize() < current_month_end.normalize():
        monthly = monthly.loc[monthly.index < current_month_end]

    returns = monthly.pct_change()
    relative = (monthly[ASSET].pct_change(6) - monthly["QQQ"].pct_change(6)).shift(1)
    frame = pd.DataFrame(index=monthly.index)
    frame["asset"] = returns[ASSET]
    frame["qqq"] = returns["QQQ"]
    frame["spy"] = returns["SPY"]
    frame["smh"] = returns["SMH"]
    frame["signal"] = (relative > 0).astype(float)
    frame = frame.dropna()
    frame["gross"] = np.where(frame["signal"] > 0, frame["asset"], frame["qqq"])
    frame["static"] = 0.5 * frame["asset"] + 0.5 * frame["qqq"]
    switches = frame["signal"].diff().abs().fillna(1)

    result = {
        "schema": "research.p36_independent_proxy_validation.v1",
        "parent": "P36",
        "child": f"P36-{CHILD}",
        "asset": ASSET,
        "hypothesis": f"Preserve the P36 six-month relative-momentum rule on independent semiconductor representation {ASSET}: prior 6-month {ASSET}-minus-QQQ return above zero selects {ASSET} next month; otherwise QQQ.",
        "frozen_contract": {
            "lookback_months": 6,
            "threshold": 0.0,
            "rebalance": "month_end_next_month",
            "cost_bps_per_switch": list(COSTS),
            "support_gate": "25bps excess_vs_static>0 AND >=3/5 positive folds AND 50bps excess_vs_static>0",
            "parameter_search": False,
        },
        "window": {"start": str(frame.index.min().date()), "end": str(frame.index.max().date()), "months": int(len(frame))},
        "sources": sources,
        "switches": int(switches.sum()),
        "controls": {},
        "cost_cases": {},
        "evaluation_integrity": {
            "common_last_daily_observation": str(common_last.date()),
            "incomplete_terminal_month_excluded": True,
            "matched_window_for_all_controls": True,
        },
    }

    for name, col in ((ASSET, "asset"), ("QQQ", "qqq"), ("SPY", "spy"), ("SMH", "smh"), (f"STATIC_50_50_{ASSET}_QQQ", "static")):
        result["controls"][name] = {
            "cagr": cagr(frame[col]),
            "max_drawdown": max_drawdown(frame[col]),
            "ann_vol": ann_vol(frame[col]),
        }

    for bps in COSTS:
        col = f"net_{bps}"
        frame[col] = frame["gross"] - switches * (bps / 10000)
        fold_rows = folds(frame, col, "static")
        year_rows = yearly(frame, col, "static")
        result["cost_cases"][str(bps)] = {
            "cagr": cagr(frame[col]),
            "max_drawdown": max_drawdown(frame[col]),
            "ann_vol": ann_vol(frame[col]),
            "excess_vs_static_50_50": cagr(frame[col]) - cagr(frame["static"]),
            "positive_folds_vs_static": sum(x["excess_cagr"] > 0 for x in fold_rows),
            "positive_years_vs_static": sum(x["excess"] > 0 for x in year_rows),
            "represented_years": len(year_rows),
            "folds": fold_rows,
            "years": year_rows,
        }

    primary = result["cost_cases"]["25"]
    stress = result["cost_cases"]["50"]
    result["decision"] = (
        "SUPPORTED_REPRESENTATION_VALIDATION"
        if primary["excess_vs_static_50_50"] > 0
        and primary["positive_folds_vs_static"] >= 3
        and stress["excess_vs_static_50_50"] > 0
        else "NOT_SUPPORTED_REPRESENTATION_VALIDATION"
    )
    result["protected_boundaries"] = {
        "mm_canonical_claim": False,
        "strategy_spec_mutation": False,
        "runtime_authority_change": False,
        "broker_submission": False,
        "live_trading_change": False,
    }

    Path("artifacts").mkdir(exist_ok=True)
    out = Path(f"artifacts/p36_{CHILD.lower()}_{ASSET.lower()}_validation.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("P36_VALIDATION_RESULT=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
