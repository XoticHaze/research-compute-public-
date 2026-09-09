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
if ASSET not in {"SMH", "SOXX", "XSD"}:
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
