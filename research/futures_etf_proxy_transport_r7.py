#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
import math
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

START = int(dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc).timestamp())
END = int(dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc).timestamp())
UA = "Mozilla/5.0 research-only futures-etf-proxy-transport-r7"
COSTS = (2.5, 5.0, 10.0)
PROXIES = {
    "ES_SPY": {"symbol": "SPY", "family": "sp500", "claim": "broad S&P-500 equity exposure proxy"},
    "ES_IVV": {"symbol": "IVV", "family": "sp500", "claim": "independent S&P-500 equity exposure proxy"},
    "NQ_QQQ": {"symbol": "QQQ", "family": "nasdaq100", "claim": "Nasdaq-100 equity exposure proxy"},
    "RTY_IWM": {"symbol": "IWM", "family": "russell2000", "claim": "Russell-2000 equity exposure proxy"},
    "GC_GLD": {"symbol": "GLD", "family": "gold", "claim": "gold spot/ETF exposure proxy"},
    "ZN_IEF": {"symbol": "IEF", "family": "ust_10y", "claim": "7-10y Treasury ETF proxy; duration/carry differ from futures"},
}


def fetch(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?period1={START}&period2={END}&interval=1d&events=history&includeAdjustedClose=true"
    last = None
    for attempt in range(1, 6):
        try:
            raw = urlopen(Request(url, headers={"User-Agent": UA, "Accept": "application/json"}), timeout=30).read()
            r = json.loads(raw)["chart"]["result"][0]
            ts = r["timestamp"]
            adj = (r.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
            if adj is None:
                adj = r["indicators"]["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime(ts, unit="s", utc=True).tz_convert(None), dtype="float64").dropna().sort_index()
            s = s[~s.index.duplicated(keep="last")]
            if len(s) < 700:
                raise RuntimeError(f"insufficient rows={len(s)}")
            return s, {
                "url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "rows": len(s),
                "start": s.index[0].date().isoformat(),
                "end": s.index[-1].date().isoformat(),
                "attempt": attempt,
            }
        except Exception as exc:
            last = exc
            if attempt < 5:
                time.sleep(2 * attempt)
    raise RuntimeError(f"{symbol}: {type(last).__name__}: {last}")


def metrics(r):
    r = pd.Series(r, dtype=float).dropna()
    if len(r) < 2:
        return {"months": len(r), "cagr": None, "sharpe_rf0": None, "max_dd": None}
    eq = (1 + r).cumprod()
    years = len(r) / 12.0
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else None
    vol = float(r.std(ddof=1) * math.sqrt(12))
    sharpe = float(r.mean() * 12 / vol) if vol > 0 else None
    dd = eq / eq.cummax() - 1
    return {"months": len(r), "cagr": cagr, "sharpe_rf0": sharpe, "max_dd": float(dd.min())}


def cagr(r):
    return metrics(r)["cagr"]


def fold_summary(candidate, baseline, folds=5):
    z = pd.concat([candidate.rename("candidate"), baseline.rename("baseline")], axis=1).dropna()
    out = []
    for i, ids in enumerate(np.array_split(np.arange(len(z)), folds), 1):
        q = z.iloc[ids]
        if len(q) < 2:
            continue
        out.append({
            "fold": i,
            "start": q.index.min().date().isoformat(),
            "end": q.index.max().date().isoformat(),
            "excess_cagr": cagr(q.candidate) - cagr(q.baseline),
        })
    return out


def evaluate(close, cost_bps, start=None):
    daily_mom = close / close.shift(252) - 1.0
    month_close = close.resample("ME").last().dropna()
    mret = month_close.pct_change()
    month_signal = daily_mom.resample("ME").last().reindex(month_close.index)
    weight = (month_signal.shift(1) > 0).astype(float)
    turnover = weight.diff().abs().fillna(weight.abs())
    candidate = weight * mret - turnover * cost_bps / 10000.0
    baseline = float(weight.mean()) * mret
    z = pd.concat([candidate.rename("candidate"), baseline.rename("baseline"), weight.rename("weight")], axis=1).dropna()
    if start is not None:
        z = z.loc[z.index >= pd.Timestamp(start)]
    folds = fold_summary(z.candidate, z.baseline)
    cm = metrics(z.candidate)
    bm = metrics(z.baseline)
    excess = cm["cagr"] - bm["cagr"] if cm["cagr"] is not None and bm["cagr"] is not None else None
    return {
        "start": z.index.min().date().isoformat(),
        "end": z.index.max().date().isoformat(),
        "candidate": cm,
        "matched_static": bm,
        "excess_cagr": excess,
        "mean_exposure": float(z.weight.mean()),
        "positive_folds": sum(x["excess_cagr"] > 0 for x in folds),
        "folds": folds,
    }


def main():
    out = {
        "schema": "research.futures_etf_proxy_transport_r7",
        "classification": "INDEPENDENT_ECONOMIC_REPRESENTATION_ONLY_NOT_CANONICAL_FUTURES_EVIDENCE",
        "parent": "futures_micro_trend252",
        "scientific_contract": {
            "mechanism": "unchanged prior-252-session return sign sampled monthly; next month long or cash",
            "costs_bps": list(COSTS),
            "matched_control": "static exposure to same proxy at candidate mean exposure over identical months",
            "windows": ["full available", "2019-05-forward", "2022-forward"],
            "support_gate": "at 5 bps: positive matched excess and >=3/5 positive folds in 2019-forward; for S&P family both SPY and IVV must satisfy; recent window reported but not required to reject other families",
            "no_parameter_search": True,
            "no_canonical_roll_claim": True,
            "not_applicable_rule": "proxy mismatch (for example IEF duration/carry) cannot scientifically reject the corresponding futures market",
        },
        "proxies": {},
    }
    for lane, meta in PROXIES.items():
        close, prov = fetch(meta["symbol"])
        tests = {}
        for bp in COSTS:
            tests[str(bp)] = {
                "full": evaluate(close, bp),
                "2019_forward": evaluate(close, bp, "2019-05-01"),
                "2022_forward": evaluate(close, bp, "2022-01-01"),
            }
        primary = tests["5.0"]["2019_forward"]
        out["proxies"][lane] = {
            **meta,
            "source": prov,
            "tests": tests,
            "screen_supported": bool(primary["excess_cagr"] > 0 and primary["positive_folds"] >= 3 and primary["candidate"]["sharpe_rf0"] >= primary["matched_static"]["sharpe_rf0"]),
        }
    sp = out["proxies"]
    sp_supported = sp["ES_SPY"]["screen_supported"] and sp["ES_IVV"]["screen_supported"]
    out["summary"] = {
        "supported_lanes": [k for k, v in sp.items() if v["screen_supported"]],
        "sp500_dual_proxy_supported": sp_supported,
        "decision": "SP500_TREND_INDEPENDENT_REPRESENTATION_SUPPORTED" if sp_supported else "SP500_TREND_INDEPENDENT_REPRESENTATION_WEAK",
        "next_step": "If dual S&P proxy support holds, prioritize dated-contract/roll-authoritative ES/MES confirmation. Other family screens only guide mechanism allocation and do not reject markets when proxy economics differ.",
    }
    Path("futures_etf_proxy_transport_r7.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(out["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
