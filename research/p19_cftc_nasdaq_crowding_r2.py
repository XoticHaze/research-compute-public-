#!/usr/bin/env python3
"""P19 CFTC Nasdaq crowding, mechanism-change retry.

Scientific contract is unchanged from p19_cftc_nasdaq_crowding.py. The only
change is price transport: Yahoo chart JSON replaces Stooq CSV after the first
attempt proved Stooq no longer returned its historical CSV schema.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

CFTC_DATASET = "gpe5-46if"
CFTC_CODE = "209742"
CFTC_URL = f"https://publicreporting.cftc.gov/resource/{CFTC_DATASET}.csv"
PRIMARY_COST_BPS = 25.0
COST_GRID_BPS = (10.0, 25.0, 50.0)
Z_WINDOW = 52
Z_MIN = 26
CROWDING_THRESHOLD = 1.0
PRICE_START = "2009-01-01"
PRICE_END_EXCLUSIVE = "2026-09-08"


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 research-compute-p19/1.0", "Accept": "*/*"})
    with urlopen(req, timeout=90) as response:
        return response.read()


def pick(columns: list[str], *aliases: str) -> str:
    by_lower = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        if alias in by_lower:
            return by_lower[alias]
    for c in columns:
        if any(alias in c.lower().strip() for alias in aliases):
            return c
    raise KeyError(f"required aliases={aliases} absent columns={columns}")


def load_cftc() -> tuple[pd.DataFrame, dict]:
    params = {"$limit": "5000", "$order": "report_date_as_yyyy_mm_dd ASC", "$where": f"cftc_contract_market_code='{CFTC_CODE}'"}
    url = CFTC_URL + "?" + urlencode(params)
    raw = fetch_bytes(url)
    src = pd.read_csv(io.BytesIO(raw))
    cols = list(src.columns)
    d = pick(cols, "report_date_as_yyyy_mm_dd", "report_date")
    oi = pick(cols, "open_interest_all", "open_interest")
    lng = pick(cols, "lev_money_positions_long_all", "lev_money_positions_long")
    sht = pick(cols, "lev_money_positions_short_all", "lev_money_positions_short")
    code = pick(cols, "cftc_contract_market_code")
    f = pd.DataFrame({
        "report_date": pd.to_datetime(src[d], utc=True, errors="coerce").dt.tz_localize(None),
        "oi": pd.to_numeric(src[oi], errors="coerce"),
        "long": pd.to_numeric(src[lng], errors="coerce"),
        "short": pd.to_numeric(src[sht], errors="coerce"),
        "code": src[code].astype(str).str.strip(),
    }).dropna()
    f = f[f.oi > 0].sort_values("report_date").drop_duplicates("report_date", keep="last")
    f["net_share"] = (f.long - f.short) / f.oi
    roll = f.net_share.rolling(Z_WINDOW, min_periods=Z_MIN)
    f["z"] = (f.net_share - roll.mean()) / roll.std(ddof=1).replace(0, np.nan)
    f = f.dropna(subset=["z"]).reset_index(drop=True)
    if len(f) < 100:
        raise RuntimeError(f"insufficient CFTC observations {len(f)}")
    return f, {
        "dataset": CFTC_DATASET,
        "contract_code": CFTC_CODE,
        "url": url,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows_raw": int(len(src)),
        "rows_usable": int(len(f)),
        "first_report": f.report_date.min().date().isoformat(),
        "last_report": f.report_date.max().date().isoformat(),
    }


def unix(date_string: str) -> int:
    return int(datetime.fromisoformat(date_string).replace(tzinfo=timezone.utc).timestamp())


def yahoo_url(symbol: str) -> str:
    q = urlencode({
        "period1": str(unix(PRICE_START)),
        "period2": str(unix(PRICE_END_EXCLUSIVE)),
        "interval": "1d",
        "events": "history",
        "includeAdjustedClose": "true",
    })
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}"


def load_yahoo(symbol: str) -> tuple[pd.Series, dict]:
    url = yahoo_url(symbol)
    raw = fetch_bytes(url)
    payload = json.loads(raw.decode("utf-8"))
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo chart missing result for {symbol}: {(payload.get('chart') or {}).get('error')}")
    ts = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    adj_rows = indicators.get("adjclose") or []
    close_rows = indicators.get("quote") or []
    values = (adj_rows[0].get("adjclose") if adj_rows else None) or (close_rows[0].get("close") if close_rows else None) or []
    if len(ts) != len(values) or len(ts) < 1000:
        raise RuntimeError(f"Yahoo chart malformed for {symbol}: timestamps={len(ts)} values={len(values)}")
    idx = pd.to_datetime(pd.Series(ts), unit="s", utc=True, errors="coerce").dt.tz_localize(None)
    s = pd.Series(pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(), index=pd.DatetimeIndex(idx), name=symbol).dropna().sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s, {
        "transport": "yahoo_chart_json",
        "url": url,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": int(len(s)),
        "first": s.index.min().date().isoformat(),
        "last": s.index.max().date().isoformat(),
    }


def load_prices() -> tuple[pd.DataFrame, dict]:
    qqq, qp = load_yahoo("QQQ")
    spy, sp = load_yahoo("SPY")
    return pd.concat([qqq, spy], axis=1, join="inner").dropna().sort_index(), {"QQQ": qp, "SPY": sp}


def effective_date(report: pd.Timestamp, sessions: pd.DatetimeIndex) -> pd.Timestamp | None:
    boundary = report.normalize() + pd.Timedelta(days=3)
    i = sessions.searchsorted(boundary, side="right")
    return None if i >= len(sessions) else sessions[i]


def intervals(cftc: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    sig = []
    for r in cftc.itertuples(index=False):
        d = effective_date(r.report_date, prices.index)
        if d is not None:
            sig.append({"report_date": r.report_date, "effective": d, "z": float(r.z)})
    sig = pd.DataFrame(sig).drop_duplicates("effective", keep="last").sort_values("effective")
    rows = []
    recs = sig.to_dict("records")
    for a, b in zip(recs[:-1], recs[1:]):
        d0, d1 = a["effective"], b["effective"]
        if d1 <= d0:
            continue
        qr = float(prices.at[d1, "QQQ"] / prices.at[d0, "QQQ"] - 1)
        sr = float(prices.at[d1, "SPY"] / prices.at[d0, "SPY"] - 1)
        asset = "SPY" if a["z"] > CROWDING_THRESHOLD else "QQQ"
        rows.append({"report_date": a["report_date"], "start": d0, "end": d1, "z": a["z"], "asset": asset,
                     "qqq": qr, "spy": sr, "half": .5 * qr + .5 * sr, "gross": sr if asset == "SPY" else qr})
    out = pd.DataFrame(rows)
    if len(out) < 100:
        raise RuntimeError(f"insufficient matched intervals {len(out)}")
    return out


def strategy_returns(f: pd.DataFrame, bps: float) -> pd.Series:
    c = bps / 10000.0
    out, prev = [], None
    for a, gross in zip(f.asset, f.gross):
        sides = 1 if prev is None else (2 if a != prev else 0)
        out.append((1 + float(gross)) * (1 - c * sides) - 1)
        prev = a
    return pd.Series(out, index=f.index)


def static_returns(f: pd.DataFrame, col: str, bps: float, initial_sides: int = 1) -> pd.Series:
    r = f[col].astype(float).copy()
    r.iloc[0] = (1 + r.iloc[0]) * (1 - bps / 10000.0 * initial_sides) - 1
    return r


def stats(r: pd.Series, f: pd.DataFrame) -> dict:
    wealth = (1 + r.reset_index(drop=True)).cumprod()
    years = max(1, (pd.Timestamp(f.end.iloc[-1]) - pd.Timestamp(f.start.iloc[0])).days) / 365.2425
    dd = wealth / wealth.cummax() - 1
    return {"intervals": int(len(r)), "total_return": float(wealth.iloc[-1] - 1), "cagr": float(wealth.iloc[-1] ** (1 / years) - 1),
            "max_drawdown": float(dd.min()), "annualized_weekly_vol": float(r.std(ddof=1) * math.sqrt(52))}


def full_years(f: pd.DataFrame, s: pd.Series, q: pd.Series) -> dict:
    x = pd.DataFrame({"end": pd.to_datetime(f.end), "s": s, "q": q}); x["year"] = x.end.dt.year
    rows = []
    for y, g in x.groupby("year"):
        if len(g) < 40:
            continue
        sr, qr = float((1 + g.s).prod() - 1), float((1 + g.q).prod() - 1)
        rows.append({"year": int(y), "strategy": sr, "qqq": qr, "excess": sr - qr, "beat": sr > qr})
    return {"rows": rows, "beat_count": sum(int(r["beat"]) for r in rows), "year_count": len(rows)}


def five_folds(f: pd.DataFrame, s: pd.Series, q: pd.Series) -> list[dict]:
    out = []
    for n, idx in enumerate(np.array_split(np.arange(len(f)), 5), 1):
        sr, qr = float((1 + s.iloc[idx]).prod() - 1), float((1 + q.iloc[idx]).prod() - 1)
        out.append({"fold": n, "start": pd.Timestamp(f.iloc[idx[0]].start).date().isoformat(), "end": pd.Timestamp(f.iloc[idx[-1]].end).date().isoformat(),
                    "strategy_return": sr, "qqq_return": qr, "excess": sr - qr, "positive_excess": sr > qr})
    return out


def run() -> dict:
    cftc, cp = load_cftc(); prices, pp = load_prices(); f = intervals(cftc, prices)
    results = {}
    for bps in COST_GRID_BPS:
        s = strategy_returns(f, bps); q = static_returns(f, "qqq", bps); p = static_returns(f, "spy", bps); h = static_returns(f, "half", bps, 2)
        sm, qm, pm, hm = stats(s, f), stats(q, f), stats(p, f), stats(h, f)
        results[str(int(bps))] = {"strategy": sm, "qqq": qm, "spy": pm, "half": hm,
                                  "cagr_excess_vs_qqq": sm["cagr"] - qm["cagr"], "cagr_excess_vs_spy": sm["cagr"] - pm["cagr"],
                                  "cagr_excess_vs_half": sm["cagr"] - hm["cagr"]}
    s25 = strategy_returns(f, PRIMARY_COST_BPS); q25 = static_returns(f, "qqq", PRIMARY_COST_BPS)
    ys = full_years(f, s25, q25); folds = five_folds(f, s25, q25); pos = sum(int(r["positive_excess"]) for r in folds)
    excess = results["25"]["cagr_excess_vs_qqq"]; yf = ys["beat_count"] / ys["year_count"] if ys["year_count"] else 0
    supported = excess > 0 and pos >= 3 and yf >= .5
    return {
        "schema": "research.p19_cftc_nasdaq_crowding.v1", "status": "PASS",
        "decision": "P19_CFTC_NASDAQ_CROWDING_SUPPORTED" if supported else "P19_CFTC_NASDAQ_CROWDING_NOT_SUPPORTED",
        "frozen_contract": {"contract_code": CFTC_CODE, "dataset": CFTC_DATASET, "position_measure": "(leveraged_money_long-leveraged_money_short)/open_interest",
                            "z_window_reports": Z_WINDOW, "z_min_reports": Z_MIN, "crowding_threshold_z": CROWDING_THRESHOLD,
                            "allocation": "QQQ if z<=1.0 else SPY", "publication_boundary": "first market session strictly after report_date+3 calendar days",
                            "primary_cost_bps_per_side": PRIMARY_COST_BPS, "cost_grid_bps_per_side": list(COST_GRID_BPS),
                            "support_gate": "primary CAGR excess vs QQQ >0 AND >=3/5 positive chronological folds AND >=50% full years beat QQQ"},
        "matched_window": {"start": pd.Timestamp(f.start.iloc[0]).date().isoformat(), "end": pd.Timestamp(f.end.iloc[-1]).date().isoformat(),
                           "intervals": int(len(f)), "spy_state_fraction": float((f.asset == "SPY").mean()),
                           "switch_count": int((f.asset != f.asset.shift()).sum() - 1)},
        "cost_results": results, "yearly_vs_qqq": ys, "chronological_folds_vs_qqq": folds, "positive_fold_count_vs_qqq": pos,
        "source_provenance": {"cftc": cp, "prices": pp},
        "mechanism_change_from_attempt_1": "price transport only: Stooq CSV -> Yahoo chart JSON; scientific contract unchanged",
        "safety": {"public_data_only": True, "strategy_spec_mutation": False, "runtime_authority_change": False, "broker_submission": False,
                   "allocation_authority_change": False, "live_trading_change": False}}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--output", required=True); args = ap.parse_args()
    receipt = run(); text = json.dumps(receipt, indent=2, sort_keys=True); Path(args.output).write_text(text + "\n"); print(text); return 0


if __name__ == "__main__":
    raise SystemExit(main())
