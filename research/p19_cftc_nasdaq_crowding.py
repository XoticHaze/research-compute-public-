#!/usr/bin/env python3
"""P19: prospectively frozen CFTC Nasdaq leveraged-money crowding discriminator.

Scientific question
-------------------
Does publication-authoritative CFTC Traders in Financial Futures positioning add
usable Nasdaq allocation information beyond simply owning QQQ?

Frozen rule
-----------
* CFTC contract market code: 209742 (NASDAQ-100 Stock Index (Mini)).
* Position state: (Leveraged Money long - short) / open interest.
* Context: trailing 52-report z-score, min 26 observations, using only reports
  available at that report date.
* Causality: report date is Tuesday; state becomes tradable at the first market
  session strictly after report_date + 3 calendar days (the Friday publication
  boundary). No same-report-date trading is allowed.
* Allocation: QQQ when z <= +1.0, SPY when z > +1.0. The hypothesis is that an
  unusually crowded leveraged-money long Nasdaq position forecasts relative
  QQQ weakness vs the broad market.
* Controls: static QQQ (primary underlying), static SPY (broad market), static
  50/50 QQQ-SPY.
* Costs: 10/25/50 bps per traded side. Primary = 25 bps/side. A QQQ<->SPY switch
  is two traded sides; initialization is one side.
* Decision gate: support requires positive after-cost CAGR excess vs QQQ at the
  primary cost, >=3/5 positive chronological-fold excess vs QQQ, and >=50% of
  full calendar years beating QQQ. Otherwise reject/park this exact mechanism.

This workload uses only public CFTC and Stooq data. It has no runtime, broker,
StrategySpec, allocation-authority, promotion-authority, or live-trading side effects.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

CFTC_DATASET = "gpe5-46if"  # TFF Futures Only
CFTC_CODE = "209742"
CFTC_URL = f"https://publicreporting.cftc.gov/resource/{CFTC_DATASET}.csv"
PRICE_URLS = {
    "QQQ": "https://stooq.com/q/d/l/?s=qqq.us&i=d&d1=20090101&d2=20260907",
    "SPY": "https://stooq.com/q/d/l/?s=spy.us&i=d&d1=20090101&d2=20260907",
}
PRIMARY_COST_BPS = 25.0
COST_GRID_BPS = (10.0, 25.0, 50.0)
Z_WINDOW = 52
Z_MIN = 26
CROWDING_THRESHOLD = 1.0


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "research-compute-p19/1.0"})
    with urlopen(req, timeout=90) as response:
        return response.read()


def _pick_column(columns: list[str], aliases: tuple[str, ...]) -> str:
    norm = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        if alias in norm:
            return norm[alias]
    for c in columns:
        low = c.lower().strip()
        if any(alias in low for alias in aliases):
            return c
    raise KeyError(f"missing required column aliases={aliases}; columns={columns}")


def load_cftc() -> tuple[pd.DataFrame, dict]:
    params = {
        "$limit": "5000",
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$where": f"cftc_contract_market_code='{CFTC_CODE}'",
    }
    url = CFTC_URL + "?" + urlencode(params)
    raw = fetch_bytes(url)
    frame = pd.read_csv(io.BytesIO(raw))
    if frame.empty:
        raise RuntimeError("CFTC query returned zero rows")
    cols = list(frame.columns)
    date_col = _pick_column(cols, ("report_date_as_yyyy_mm_dd", "report_date"))
    oi_col = _pick_column(cols, ("open_interest_all", "open_interest"))
    long_col = _pick_column(cols, ("lev_money_positions_long_all", "lev_money_positions_long"))
    short_col = _pick_column(cols, ("lev_money_positions_short_all", "lev_money_positions_short"))
    code_col = _pick_column(cols, ("cftc_contract_market_code",))
    out = pd.DataFrame({
        "report_date": pd.to_datetime(frame[date_col], utc=True, errors="coerce").dt.tz_localize(None),
        "open_interest": pd.to_numeric(frame[oi_col], errors="coerce"),
        "lev_long": pd.to_numeric(frame[long_col], errors="coerce"),
        "lev_short": pd.to_numeric(frame[short_col], errors="coerce"),
        "code": frame[code_col].astype(str).str.strip(),
    }).dropna(subset=["report_date", "open_interest", "lev_long", "lev_short"])
    out = out[out["open_interest"] > 0].sort_values("report_date").drop_duplicates("report_date", keep="last")
    out["lev_net_share"] = (out["lev_long"] - out["lev_short"]) / out["open_interest"]
    rolling = out["lev_net_share"].rolling(Z_WINDOW, min_periods=Z_MIN)
    mean = rolling.mean()
    std = rolling.std(ddof=1)
    out["lev_net_z52"] = (out["lev_net_share"] - mean) / std.replace(0, np.nan)
    out = out.dropna(subset=["lev_net_z52"]).reset_index(drop=True)
    return out, {
        "url": url,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows_raw": int(len(frame)),
        "rows_usable": int(len(out)),
        "first_report": out["report_date"].min().date().isoformat(),
        "last_report": out["report_date"].max().date().isoformat(),
        "dataset": CFTC_DATASET,
        "contract_code": CFTC_CODE,
    }


def load_prices() -> tuple[pd.DataFrame, dict]:
    series = {}
    provenance = {}
    for symbol, url in PRICE_URLS.items():
        raw = fetch_bytes(url)
        df = pd.read_csv(io.BytesIO(raw))
        if df.empty:
            raise RuntimeError(f"{symbol} price source empty")
        date = pd.to_datetime(df["Date"], errors="coerce")
        close = pd.to_numeric(df["Close"], errors="coerce")
        s = pd.Series(close.to_numpy(), index=date, name=symbol).dropna()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        series[symbol] = s
        provenance[symbol] = {
            "url": url,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "rows": int(len(s)),
            "first": s.index.min().date().isoformat(),
            "last": s.index.max().date().isoformat(),
        }
    prices = pd.concat(series.values(), axis=1, join="inner").dropna().sort_index()
    return prices, provenance


def effective_session(report_date: pd.Timestamp, sessions: pd.DatetimeIndex) -> pd.Timestamp | None:
    # Friday publication boundary = Tuesday report + 3 days. Trade strictly after it.
    boundary = report_date.normalize() + pd.Timedelta(days=3)
    loc = sessions.searchsorted(boundary, side="right")
    if loc >= len(sessions):
        return None
    return sessions[loc]


def build_intervals(cftc: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    sessions = prices.index
    for row in cftc.itertuples(index=False):
        eff = effective_session(row.report_date, sessions)
        if eff is None:
            continue
        rows.append({"report_date": row.report_date, "effective_date": eff, "z": float(row.lev_net_z52)})
    signals = pd.DataFrame(rows).drop_duplicates("effective_date", keep="last").sort_values("effective_date")
    if len(signals) < 100:
        raise RuntimeError(f"insufficient causal signal observations: {len(signals)}")
    records = []
    values = signals.to_dict("records")
    for current, nxt in zip(values[:-1], values[1:]):
        d0, d1 = current["effective_date"], nxt["effective_date"]
        if d0 not in prices.index or d1 not in prices.index or d1 <= d0:
            continue
        qret = float(prices.at[d1, "QQQ"] / prices.at[d0, "QQQ"] - 1.0)
        sret = float(prices.at[d1, "SPY"] / prices.at[d0, "SPY"] - 1.0)
        asset = "SPY" if float(current["z"]) > CROWDING_THRESHOLD else "QQQ"
        records.append({
            "report_date": current["report_date"],
            "start": d0,
            "end": d1,
            "z": float(current["z"]),
            "asset": asset,
            "qqq_ret": qret,
            "spy_ret": sret,
            "half_ret": 0.5 * qret + 0.5 * sret,
            "gross_ret": sret if asset == "SPY" else qret,
        })
    out = pd.DataFrame(records)
    if len(out) < 100:
        raise RuntimeError(f"insufficient matched intervals: {len(out)}")
    return out


def add_costs(frame: pd.DataFrame, bps: float) -> pd.Series:
    side_cost = bps / 10000.0
    prev = None
    net = []
    for asset, gross in zip(frame["asset"], frame["gross_ret"]):
        sides = 1 if prev is None else (2 if asset != prev else 0)
        net.append((1.0 + float(gross)) * (1.0 - side_cost * sides) - 1.0)
        prev = asset
    return pd.Series(net, index=frame.index)


def static_costed(frame: pd.DataFrame, column: str, bps: float, sides: float = 1.0) -> pd.Series:
    out = frame[column].astype(float).copy()
    if len(out):
        out.iloc[0] = (1.0 + out.iloc[0]) * (1.0 - bps / 10000.0 * sides) - 1.0
    return out


def metrics(returns: pd.Series, starts: pd.Series, ends: pd.Series) -> dict:
    r = returns.astype(float).reset_index(drop=True)
    wealth = (1.0 + r).cumprod()
    days = max(1, int((pd.Timestamp(ends.iloc[-1]) - pd.Timestamp(starts.iloc[0])).days))
    years = days / 365.2425
    cagr = float(wealth.iloc[-1] ** (1.0 / years) - 1.0)
    dd = wealth / wealth.cummax() - 1.0
    ann_vol = float(r.std(ddof=1) * math.sqrt(52.0)) if len(r) > 1 else 0.0
    return {
        "total_return": float(wealth.iloc[-1] - 1.0),
        "cagr": cagr,
        "max_drawdown": float(dd.min()),
        "annualized_weekly_vol": ann_vol,
        "intervals": int(len(r)),
    }


def yearly_beats(frame: pd.DataFrame, strategy: pd.Series, control: pd.Series) -> dict:
    tmp = pd.DataFrame({"end": pd.to_datetime(frame["end"]), "s": strategy, "c": control}).dropna()
    tmp["year"] = tmp["end"].dt.year
    rows = []
    for year, g in tmp.groupby("year"):
        if len(g) < 40:
            continue
        sr = float((1 + g["s"]).prod() - 1)
        cr = float((1 + g["c"]).prod() - 1)
        rows.append({"year": int(year), "strategy": sr, "control": cr, "excess": sr - cr, "beat": sr > cr})
    return {"rows": rows, "beat_count": int(sum(x["beat"] for x in rows)), "year_count": int(len(rows))}


def folds(frame: pd.DataFrame, strategy: pd.Series, control: pd.Series, n: int = 5) -> list[dict]:
    idxs = np.array_split(np.arange(len(frame)), n)
    rows = []
    for i, idx in enumerate(idxs, 1):
        if not len(idx):
            continue
        sr = float((1 + strategy.iloc[idx]).prod() - 1)
        cr = float((1 + control.iloc[idx]).prod() - 1)
        rows.append({
            "fold": i,
            "start": pd.Timestamp(frame.iloc[idx[0]]["start"]).date().isoformat(),
            "end": pd.Timestamp(frame.iloc[idx[-1]]["end"]).date().isoformat(),
            "strategy_return": sr,
            "qqq_return": cr,
            "excess": sr - cr,
            "positive_excess": sr > cr,
        })
    return rows


def run() -> dict:
    cftc, cftc_prov = load_cftc()
    prices, price_prov = load_prices()
    frame = build_intervals(cftc, prices)
    cost_results = {}
    for bps in COST_GRID_BPS:
        strat = add_costs(frame, bps)
        qqq = static_costed(frame, "qqq_ret", bps)
        spy = static_costed(frame, "spy_ret", bps)
        half = static_costed(frame, "half_ret", bps, sides=2.0)
        sm = metrics(strat, frame["start"], frame["end"])
        qm = metrics(qqq, frame["start"], frame["end"])
        pm = metrics(spy, frame["start"], frame["end"])
        hm = metrics(half, frame["start"], frame["end"])
        cost_results[str(int(bps))] = {
            "strategy": sm,
            "qqq": qm,
            "spy": pm,
            "half": hm,
            "cagr_excess_vs_qqq": sm["cagr"] - qm["cagr"],
            "cagr_excess_vs_spy": sm["cagr"] - pm["cagr"],
            "cagr_excess_vs_half": sm["cagr"] - hm["cagr"],
        }
    primary = add_costs(frame, PRIMARY_COST_BPS)
    qqq_primary = static_costed(frame, "qqq_ret", PRIMARY_COST_BPS)
    years = yearly_beats(frame, primary, qqq_primary)
    fold_rows = folds(frame, primary, qqq_primary)
    positive_folds = sum(bool(x["positive_excess"]) for x in fold_rows)
    primary_excess = cost_results[str(int(PRIMARY_COST_BPS))]["cagr_excess_vs_qqq"]
    year_fraction = years["beat_count"] / years["year_count"] if years["year_count"] else 0.0
    supported = bool(primary_excess > 0 and positive_folds >= 3 and year_fraction >= 0.5)
    return {
        "schema": "research.p19_cftc_nasdaq_crowding.v1",
        "status": "PASS",
        "decision": "P19_CFTC_NASDAQ_CROWDING_SUPPORTED" if supported else "P19_CFTC_NASDAQ_CROWDING_NOT_SUPPORTED",
        "frozen_contract": {
            "contract_code": CFTC_CODE,
            "dataset": CFTC_DATASET,
            "position_measure": "(leveraged_money_long-leveraged_money_short)/open_interest",
            "z_window_reports": Z_WINDOW,
            "z_min_reports": Z_MIN,
            "crowding_threshold_z": CROWDING_THRESHOLD,
            "allocation": "QQQ if z<=1.0 else SPY",
            "publication_boundary": "first market session strictly after report_date+3 calendar days",
            "primary_cost_bps_per_side": PRIMARY_COST_BPS,
            "cost_grid_bps_per_side": list(COST_GRID_BPS),
            "support_gate": "primary CAGR excess vs QQQ >0 AND >=3/5 positive chronological folds AND >=50% full years beat QQQ",
        },
        "matched_window": {
            "start": pd.Timestamp(frame.iloc[0]["start"]).date().isoformat(),
            "end": pd.Timestamp(frame.iloc[-1]["end"]).date().isoformat(),
            "intervals": int(len(frame)),
            "spy_state_fraction": float((frame["asset"] == "SPY").mean()),
            "switch_count": int((frame["asset"] != frame["asset"].shift()).sum() - 1),
        },
        "cost_results": cost_results,
        "yearly_vs_qqq": years,
        "chronological_folds_vs_qqq": fold_rows,
        "positive_fold_count_vs_qqq": int(positive_folds),
        "source_provenance": {"cftc": cftc_prov, "prices": price_prov},
        "safety": {
            "public_data_only": True,
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "broker_submission": False,
            "allocation_authority_change": False,
            "live_trading_change": False,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    receipt = run()
    rendered = json.dumps(receipt, indent=2, sort_keys=True)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
