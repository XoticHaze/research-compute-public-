from __future__ import annotations

"""A6 Treasury General Account liquidity -> QQQ/SPY selection R1.

A genuinely orthogonal macro-liquidity discriminator using the U.S. Treasury
Daily Treasury Statement operating cash balance API.

Chronology:
- The Daily Treasury Statement for record date D is published the following
  business day.
- To avoid assuming intraday publication availability, the strategy enters at
  the OPEN of the second market session after the Treasury record date.
- Weekly signals use the last Treasury record available in each Friday-ended
  week, after a fixed five-Treasury-record TGA change.
"""

from datetime import date
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

SCHEMA = "research.tga_qqq_spy_liquidity_r1.v1"
OUT = Path("artifacts/tga_qqq_spy_liquidity_r1.json")
API_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
START = "2016-01-01"
END = "2025-12-31"
PRICE_START = "2015-12-01"
PRICE_END_EXCLUSIVE = "2026-01-01"
LOOKBACK_TREASURY_RECORDS = 5
INFO_DELAY_MARKET_SESSIONS = 2
HOLD_MARKET_SESSIONS = 5
ONE_WAY_COST_BPS = 10.0


def load_tga() -> tuple[pd.DataFrame, dict[str, Any]]:
    params = {
        "fields": "record_date,account_type,close_today_bal",
        "filter": f"record_date:gte:{START},record_date:lte:{END}",
        "sort": "record_date",
        "page[size]": "10000",
    }
    url = API_BASE + "?" + urlencode(params, safe=":,")
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 XoticHaze-research https://github.com/XoticHaze/research-compute-public-",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=90) as resp:
        raw = resp.read()
    payload = json.loads(raw.decode("utf-8"))
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Treasury Fiscal Data API returned no rows")

    frame = pd.DataFrame(rows)
    if not {"record_date", "account_type", "close_today_bal"} <= set(frame.columns):
        raise RuntimeError(f"unexpected Treasury fields: {sorted(frame.columns)}")
    types = sorted(set(frame["account_type"].dropna().astype(str)))
    mask = frame["account_type"].astype(str).str.contains(
        "Treasury General Account", case=False, regex=False
    )
    tga = frame.loc[mask, ["record_date", "account_type", "close_today_bal"]].copy()
    if tga.empty:
        raise RuntimeError(f"TGA account row not found; observed account types={types}")
    tga["record_date"] = pd.to_datetime(tga["record_date"], errors="coerce")
    tga["close_today_bal"] = pd.to_numeric(
        tga["close_today_bal"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    tga = (
        tga.dropna(subset=["record_date", "close_today_bal"])
        .sort_values("record_date")
        .drop_duplicates("record_date", keep="last")
        .reset_index(drop=True)
    )
    if len(tga) < 1000:
        raise RuntimeError(f"insufficient TGA history: {len(tga)} rows")

    tga["tga_change_5"] = tga["close_today_bal"] / tga["close_today_bal"].shift(LOOKBACK_TREASURY_RECORDS) - 1.0
    tga = tga.dropna(subset=["tga_change_5"]).copy()

    # Last Treasury observation in each Friday-ended week. The sign is frozen:
    # TGA drawdown (<0) is hypothesized to release liquidity and favor QQQ.
    weekly = (
        tga.set_index("record_date")
        .resample("W-FRI")
        .last()
        .dropna(subset=["tga_change_5"])
        .reset_index(drop=False)
        .rename(columns={"record_date": "week_end"})
    )
    # Preserve the actual source record date, not the resample label.
    actual = (
        tga.assign(week=tga["record_date"].dt.to_period("W-FRI"))
        .groupby("week", as_index=False)
        .tail(1)[["record_date", "tga_change_5", "close_today_bal"]]
        .copy()
    )
    actual["week"] = actual["record_date"].dt.to_period("W-FRI")
    weekly["week"] = weekly["week_end"].dt.to_period("W-FRI")
    weekly = weekly.drop(columns=["tga_change_5", "close_today_bal"], errors="ignore").merge(
        actual[["week", "record_date", "tga_change_5", "close_today_bal"]],
        on="week",
        how="inner",
        validate="one_to_one",
    )
    weekly = weekly.sort_values("record_date").reset_index(drop=True)

    manifest = (
        tga[["record_date", "close_today_bal"]]
        .assign(record_date=lambda x: x["record_date"].dt.date.astype(str))
        .to_csv(index=False)
        .encode("utf-8")
    )
    return weekly, {
        "provider": "U.S. Treasury Fiscal Data / Daily Treasury Statement",
        "endpoint": API_BASE,
        "requested_window": [START, END],
        "raw_api_sha256": hashlib.sha256(raw).hexdigest(),
        "normalized_tga_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "tga_daily_rows": int(len(tga)),
        "weekly_signal_rows": int(len(weekly)),
        "account_types_observed": types,
        "publication_clock": "Daily Treasury Statement is published the following business day; R1 enters only on the second market session after record_date.",
        "2026_tga_requested": False,
    }


def load_prices() -> dict[str, pd.DataFrame]:
    raw = yf.download(
        ["QQQ", "SPY"],
        start=PRICE_START,
        end=PRICE_END_EXCLUSIVE,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if raw.empty:
        raise RuntimeError("price download returned empty")
    out: dict[str, pd.DataFrame] = {}
    for ticker in ("QQQ", "SPY"):
        node = raw[ticker][["Open", "Close"]].dropna().copy()
        idx = pd.DatetimeIndex(node.index)
        if idx.tz is not None:
            idx = idx.tz_convert(None)
        node.index = idx.normalize()
        out[ticker] = node.loc[node.index < pd.Timestamp(PRICE_END_EXCLUSIVE)]
    return out


def _event_return(
    prices: pd.DataFrame,
    record_date: pd.Timestamp,
) -> tuple[float, str, str] | None:
    idx = prices.index
    after = np.flatnonzero(idx > record_date.normalize())
    if len(after) < INFO_DELAY_MARKET_SESSIONS:
        return None
    entry_i = int(after[INFO_DELAY_MARKET_SESSIONS - 1])
    exit_i = entry_i + HOLD_MARKET_SESSIONS
    if exit_i >= len(idx):
        return None
    entry_date = idx[entry_i]
    exit_date = idx[exit_i]
    if exit_date > pd.Timestamp(END):
        return None
    entry_px = float(prices.iloc[entry_i]["Open"])
    exit_px = float(prices.iloc[exit_i]["Close"])
    if not (entry_px > 0 and exit_px > 0):
        return None
    return exit_px / entry_px - 1.0, entry_date.date().isoformat(), exit_date.date().isoformat()


def build_tape(signals: pd.DataFrame, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    roundtrip_cost = 2.0 * ONE_WAY_COST_BPS / 10000.0
    for row in signals.itertuples(index=False):
        record_date = pd.Timestamp(row.record_date)
        q = _event_return(prices["QQQ"], record_date)
        s = _event_return(prices["SPY"], record_date)
        if q is None or s is None:
            continue
        qret, entry_date, exit_date = q
        sret, s_entry, s_exit = s
        if (entry_date, exit_date) != (s_entry, s_exit):
            raise RuntimeError("QQQ/SPY event calendar mismatch")
        drawdown = bool(float(row.tga_change_5) < 0.0)
        selected = qret if drawdown else sret
        rows.append({
            "record_date": record_date.date().isoformat(),
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_year": int(pd.Timestamp(entry_date).year),
            "tga_close_millions": float(row.close_today_bal),
            "tga_change_5": float(row.tga_change_5),
            "tga_drawdown_signal": drawdown,
            "selected": "QQQ" if drawdown else "SPY",
            "qqq_return": float(qret),
            "spy_return": float(sret),
            "selected_net": float(selected - roundtrip_cost),
        })
    tape = pd.DataFrame(rows)
    if len(tape) < 300:
        raise RuntimeError(f"insufficient scoreable weekly TGA events: {len(tape)}")
    return tape


def _slice_stats(tape: pd.DataFrame) -> dict[str, Any]:
    if tape.empty:
        raise RuntimeError("empty evaluation slice")
    p = float(tape["tga_drawdown_signal"].mean())
    roundtrip_cost = 2.0 * ONE_WAY_COST_BPS / 10000.0
    control = p * tape["qqq_return"] + (1.0 - p) * tape["spy_return"] - roundtrip_cost
    excess = tape["selected_net"] - control
    spy_net = tape["spy_return"] - roundtrip_cost
    qqq_spy = tape["qqq_return"] - tape["spy_return"]
    draw = tape["tga_drawdown_signal"]
    diff = float(qqq_spy[draw].mean() - qqq_spy[~draw].mean()) if draw.any() and (~draw).any() else None
    return {
        "events": int(len(tape)),
        "qqq_participation": p,
        "mean_selected_net_bps": float(tape["selected_net"].mean() * 10000.0),
        "mean_matched_control_net_bps": float(control.mean() * 10000.0),
        "mean_matched_excess_bps": float(excess.mean() * 10000.0),
        "matched_excess_positive_rate": float((excess > 0).mean()),
        "mean_excess_vs_spy_bps": float((tape["selected_net"] - spy_net).mean() * 10000.0),
        "qqq_minus_spy_drawdown_vs_build_diff_bps": None if diff is None else diff * 10000.0,
    }


def evaluate(tape: pd.DataFrame) -> dict[str, Any]:
    windows = {
        "2016_plus": _slice_stats(tape[tape["entry_year"] >= 2016]),
        "2020_plus": _slice_stats(tape[tape["entry_year"] >= 2020]),
        "2022_plus": _slice_stats(tape[tape["entry_year"] >= 2022]),
    }
    blocks = {
        "2016_2018": _slice_stats(tape[(tape["entry_year"] >= 2016) & (tape["entry_year"] <= 2018)]),
        "2019_2021": _slice_stats(tape[(tape["entry_year"] >= 2019) & (tape["entry_year"] <= 2021)]),
        "2022_2023": _slice_stats(tape[(tape["entry_year"] >= 2022) & (tape["entry_year"] <= 2023)]),
        "2024_2025": _slice_stats(tape[(tape["entry_year"] >= 2024) & (tape["entry_year"] <= 2025)]),
    }
    positive_blocks = sum(v["mean_matched_excess_bps"] > 0 for v in blocks.values())
    support = (
        all(v["mean_matched_excess_bps"] > 0 for v in windows.values())
        and all((v["qqq_minus_spy_drawdown_vs_build_diff_bps"] or 0) > 0 for v in windows.values())
        and positive_blocks >= 3
    )
    return {
        "decision": "TGA_QQQ_SPY_LIQUIDITY_R1_SUPPORTED" if support else "TGA_QQQ_SPY_LIQUIDITY_R1_REJECTED",
        "windows": windows,
        "blocks": blocks,
        "positive_blocks": positive_blocks,
        "required_positive_blocks": 3,
    }


def main() -> None:
    signals, lineage = load_tga()
    prices = load_prices()
    tape = build_tape(signals, prices)
    result = evaluate(tape)
    out = {
        "schema": SCHEMA,
        "workload_id": "A6_TGA_QQQ_SPY_LIQUIDITY_R1",
        "hypothesis": (
            "A five-report Treasury General Account drawdown releases near-term dollar liquidity and should increase "
            "QQQ relative return versus SPY over the next market week."
        ),
        "frozen_contract": {
            "development_window": [START, END],
            "protected_window": "2026+",
            "signal_frequency": "last Treasury record in each Friday-ended week",
            "signal": "TGA closing balance / closing balance 5 Treasury records earlier - 1",
            "direction": "TGA change < 0 selects QQQ; otherwise SPY",
            "information_delay_market_sessions": INFO_DELAY_MARKET_SESSIONS,
            "holding_market_sessions": HOLD_MARKET_SESSIONS,
            "one_way_cost_bps": ONE_WAY_COST_BPS,
            "matched_control": "static QQQ/SPY blend matched to realized QQQ participation in each evaluation slice",
            "support_rule": (
                "positive matched excess in 2016+, 2020+, and 2022+; positive QQQ-vs-SPY drawdown/build differential "
                "in all three windows; >=3/4 positive chronology blocks"
            ),
            "no_rescue": (
                "No sign flip, TGA lookback, weekly sampling day, delay, holding period, QQQ/SPY substitution, cost, "
                "date, threshold, transform, or control rescue after terminal result."
            ),
        },
        "source_lineage": lineage,
        "sample": {
            "scoreable_weekly_events": int(len(tape)),
            "first_record_date": str(tape["record_date"].min()),
            "last_exit_date": str(tape["exit_date"].max()),
        },
        "result": result,
        "boundaries": {
            "research_only": True,
            "allocation_authority": False,
            "strategy_spec_write": False,
            "runtime_mutation": False,
            "broker_action": False,
            "promotion_authority": False,
            "live_trading_change": False,
            "2026_outcomes_protected": True,
        },
    }
    if pd.Timestamp(out["sample"]["last_exit_date"]) > pd.Timestamp(END):
        raise RuntimeError("protected 2026 outcome boundary violated")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("RESULT_JSON=" + json.dumps({
        "decision": result["decision"],
        "events": len(tape),
        "matched_excess_2016_plus_bps": result["windows"]["2016_plus"]["mean_matched_excess_bps"],
        "matched_excess_2020_plus_bps": result["windows"]["2020_plus"]["mean_matched_excess_bps"],
        "matched_excess_2022_plus_bps": result["windows"]["2022_plus"]["mean_matched_excess_bps"],
        "positive_blocks": result["positive_blocks"],
        "source_manifest_sha256": lineage["normalized_tga_manifest_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
