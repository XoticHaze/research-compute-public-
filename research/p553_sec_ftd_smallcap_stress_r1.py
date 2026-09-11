from __future__ import annotations

import io
import json
import math
import time
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

START_YEAR = 2018
END_YEAR = 2026
END = "2026-09-11"
COST_BPS = 10.0
BASE = "https://www.sec.gov/files/data/fails-deliver-data/cnsfails{ym}{half}.zip"
SEC_PAGE = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"
FOLDS = [("2019-01-01", "2021-12-31"), ("2022-01-01", "2023-12-31"), ("2024-01-01", END)]
UA = {
    "User-Agent": "XoticHaze Research xotichaze@users.noreply.github.com",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Accept-Encoding": "gzip, deflate",
    "Referer": SEC_PAGE,
}
REQUEST_DELAY_SECONDS = 0.22


def cagr(r):
    if len(r) < 2:
        return None
    y = (r.index[-1] - r.index[0]).days / 365.25
    t = float((1 + r).prod())
    return None if y <= 0 or t <= 0 else t ** (1 / y) - 1


def mdd(r):
    e = (1 + r).cumprod()
    return float((e / e.cummax() - 1).min())


def stats(r):
    return {
        "cagr": cagr(r),
        "max_drawdown": mdd(r),
        "vol": float(r.std() * math.sqrt(252)),
        "days": int(len(r)),
    }


def _fetch_archive(session, url, diag):
    last_error = None
    for attempt in range(4):
        try:
            r = session.get(url, headers=UA, timeout=(15, 60))
            diag["status_counts"][str(r.status_code)] += 1
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return None
            last_error = f"HTTP {r.status_code}"
            if r.status_code in {403, 429, 500, 502, 503, 504}:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
        except Exception as exc:
            last_error = repr(exc)
            diag["exception_counts"][type(exc).__name__] += 1
            time.sleep(1.5 * (attempt + 1))
    if last_error and len(diag["error_samples"]) < 8:
        diag["error_samples"].append({"url": url, "error": last_error})
    return None


def fetch_ftd():
    rows = []
    ok = 0
    missing = 0
    diag = {
        "status_counts": Counter(),
        "exception_counts": Counter(),
        "error_samples": [],
        "sec_page_status": None,
    }
    session = requests.Session()
    try:
        page = session.get(SEC_PAGE, headers={"User-Agent": UA["User-Agent"], "Accept": "text/html,*/*"}, timeout=(15, 45))
        diag["sec_page_status"] = page.status_code
    except Exception as exc:
        diag["sec_page_status"] = f"error:{type(exc).__name__}"

    for y in range(START_YEAR, END_YEAR + 1):
        for m in range(1, 13):
            if y == 2026 and m > 8:
                continue
            ym = f"{y}{m:02d}"
            for half in ("a", "b"):
                u = BASE.format(ym=ym, half=half)
                content = _fetch_archive(session, u, diag)
                if content is None:
                    missing += 1
                    time.sleep(REQUEST_DELAY_SECONDS)
                    continue
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        name = z.namelist()[0]
                        d = pd.read_csv(z.open(name), sep="|", dtype=str, encoding_errors="ignore")
                    d.columns = [str(c).strip().upper() for c in d.columns]
                    sym = next((c for c in d.columns if c in {"SYMBOL", "SYMBOLS"}), None)
                    qty = next((c for c in d.columns if "QUANTITY" in c), None)
                    price = next((c for c in d.columns if c == "PRICE"), None)
                    date = next((c for c in d.columns if "SETTLEMENT" in c and "DATE" in c), None)
                    if not all([sym, qty, price, date]):
                        if len(diag["error_samples"]) < 8:
                            diag["error_samples"].append({"url": u, "error": f"schema:{list(d.columns)}"})
                        missing += 1
                        continue
                    x = d[d[sym].isin(["IWM", "SPY"])][[date, sym, qty, price]].copy()
                    x["date"] = pd.to_datetime(x[date], format="%Y%m%d", errors="coerce")
                    x["qty"] = pd.to_numeric(x[qty], errors="coerce")
                    x["price"] = pd.to_numeric(x[price], errors="coerce")
                    x["dollar_ftd"] = x["qty"] * x["price"]
                    rows.append(x[["date", sym, "dollar_ftd"]].rename(columns={sym: "symbol"}))
                    ok += 1
                except Exception as exc:
                    missing += 1
                    diag["exception_counts"][type(exc).__name__] += 1
                    if len(diag["error_samples"]) < 8:
                        diag["error_samples"].append({"url": u, "error": repr(exc)})
                time.sleep(REQUEST_DELAY_SECONDS)

    out_diag = {
        "archives_ok": ok,
        "archives_missing_or_failed": missing,
        "sec_page_status": diag["sec_page_status"],
        "status_counts": dict(diag["status_counts"]),
        "exception_counts": dict(diag["exception_counts"]),
        "error_samples": diag["error_samples"],
        "request_delay_seconds": REQUEST_DELAY_SECONDS,
    }
    if not rows:
        return pd.DataFrame(), out_diag
    a = pd.concat(rows, ignore_index=True).dropna()
    a["month"] = a.date.dt.to_period("M").dt.to_timestamp("M")
    p = a.groupby(["month", "symbol"]).dollar_ftd.sum().unstack("symbol").sort_index()
    out_diag["raw_symbol_days"] = int(len(a))
    return p, out_diag


def evaluate(d, a, b):
    z = d.loc[a:b]
    return {
        "strategy": stats(z.strategy),
        "control": stats(z.control),
        "IWM": stats(z.IWM),
        "SPY": stats(z.SPY),
        "matched_excess_cagr": cagr(z.strategy) - cagr(z.control),
        "spy_excess_cagr": cagr(z.strategy) - cagr(z.SPY),
        "switches": int(z.switch.sum()),
        "iwm_weight_mean": float(z.iwm_w.mean()),
    }


def main():
    ftd, diag = fetch_ftd()
    if len(ftd) < 24 or not {"IWM", "SPY"}.issubset(ftd.columns):
        out = {
            "schema": "research.p553_sec_ftd_smallcap_stress_r1",
            "parent": "P553",
            "decision": "P553_SOURCE_COVERAGE_NOT_READY",
            "source_diagnostics": diag,
            "months": int(len(ftd)),
        }
    else:
        med = ftd[["IWM", "SPY"]].expanding(min_periods=12).median()
        norm = (ftd[["IWM", "SPY"]] / med).replace([float("inf")], pd.NA)
        # Frozen scientific rule: higher relative IWM settlement stress prefers SPY.
        signal = (norm.IWM <= norm.SPY).astype(float).shift(2).dropna().rename("iwm_w")
        raw = yf.download(
            ["IWM", "SPY"],
            start="2018-01-01",
            end="2026-09-12",
            auto_adjust=True,
            progress=False,
            group_by="column",
        )
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        r = close[["IWM", "SPY"]].dropna().pct_change().dropna()
        d = r.join(signal.reindex(r.index, method="ffill")).dropna()
        d["spy_w"] = 1 - d.iwm_w
        d["switch"] = d.iwm_w.diff().abs().fillna(0)
        d["strategy"] = d.iwm_w * d.IWM + d.spy_w * d.SPY - d.switch * (COST_BPS / 10000)
        d["control"] = 0.5 * d.IWM + 0.5 * d.SPY
        overall = evaluate(d, "2019-01-01", END)
        folds = [evaluate(d, *f) for f in FOLDS]
        positive = sum(f["matched_excess_cagr"] > 0 for f in folds)
        decision = "P553_SUPPORTED" if overall["matched_excess_cagr"] > 0 and positive >= 2 else "P553_NOT_SUPPORTED_NO_RESCUE"
        out = {
            "schema": "research.p553_sec_ftd_smallcap_stress_r1",
            "parent": "P553",
            "claim": "Relative SEC fails-to-deliver settlement stress can causally select IWM versus SPY with durable after-cost excess over a static IWM/SPY mix.",
            "frozen_contract": {
                "source": "SEC Fails-to-Deliver half-month archives",
                "feature": "monthly sum of daily outstanding dollar FTD for IWM and SPY, each normalized by its expanding median after 12 months",
                "signal": "IWM when normalized IWM FTD stress <= normalized SPY stress; otherwise SPY",
                "availability_guard": "two full month-end lag after the settlement month",
                "control": "static 50/50 IWM/SPY",
                "cost_bps_per_full_switch": COST_BPS,
                "folds": FOLDS,
                "no_parameter_rescue": True,
            },
            "overall": overall,
            "folds": folds,
            "positive_fold_count": positive,
            "decision": decision,
            "source_diagnostics": {
                **diag,
                "months": int(len(ftd)),
                "first_month": str(ftd.index.min().date()),
                "last_month": str(ftd.index.max().date()),
            },
            "boundaries": {
                "portfolio_ranking": False,
                "allocation_authority": False,
                "runtime": False,
                "broker": False,
                "live_trading": False,
            },
        }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p553_sec_ftd_smallcap_stress_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
