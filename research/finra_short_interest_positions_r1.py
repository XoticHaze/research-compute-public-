from __future__ import annotations

"""A4 FINRA consolidated short-interest position R1.

This is a materially distinct follow-on to the rejected daily short-sale-volume
A1 test.  It uses twice-monthly reported *positions*, not short-sale transaction
volume.  The information clock is conservatively delayed 14 calendar days after
settlement so the test never assumes availability before FINRA publication.

Frozen development vintage: consolidated-all-exchange era from 2022-06-30
through 2025-12-31.  No 2026 price outcomes are consumed.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

SCHEMA = "research.finra_short_interest_positions_r1.v1"
OUT = Path("artifacts/finra_short_interest_positions_r1.json")
FINRA_ENDPOINT = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
START_SETTLEMENT = date(2022, 6, 30)
END_SETTLEMENT = date(2025, 12, 31)
PRICE_START = "2022-06-01"
PRICE_END_EXCLUSIVE = "2026-01-01"
PUBLICATION_LAG_CALENDAR_DAYS = 14
HOLD_SESSIONS = 20
ONE_WAY_COST_BPS = 10.0

INDUSTRIES: dict[str, dict[str, Any]] = {
    "SEMICONDUCTOR": {
        "benchmark": "SMH",
        "symbols": ["AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI", "NVDA", "AMD", "MU", "AVGO", "MRVL", "MCHP"],
    },
    "MACHINERY": {
        "benchmark": "XLI",
        "symbols": ["CAT", "DE", "ETN", "PH", "ITW", "EMR", "ROK", "DOV"],
    },
    "SOFTWARE": {
        "benchmark": "IGV",
        "symbols": ["MSFT", "ORCL", "ADBE", "CRM", "INTU", "NOW"],
    },
    "INSURANCE": {
        "benchmark": "KIE",
        "symbols": ["PGR", "CB", "ALL", "TRV", "AFL", "MET", "AIG", "PRU"],
    },
    "RETAIL": {
        "benchmark": "XRT",
        "symbols": ["WMT", "COST", "TGT", "LOW", "HD", "TJX", "ROST", "DG"],
    },
}

UNIVERSE = sorted({symbol for node in INDUSTRIES.values() for symbol in node["symbols"]})
BENCHMARKS = sorted({node["benchmark"] for node in INDUSTRIES.values()} | {"SPY"})


def _post_symbol(symbol: str) -> tuple[str, list[dict[str, Any]]]:
    payload = json.dumps({
        "limit": 5000,
        "compareFilters": [
            {"compareType": "equal", "fieldName": "symbolCode", "fieldValue": symbol}
        ],
    }).encode("utf-8")
    last_error: str | None = None
    for attempt in range(3):
        try:
            req = Request(
                FINRA_ENDPOINT,
                data=payload,
                method="POST",
                headers={
                    "User-Agent": "Mozilla/5.0 research-only FINRA short-interest study",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            with urlopen(req, timeout=45) as resp:
                raw = resp.read()
            rows = json.loads(raw.decode("utf-8"))
            if not isinstance(rows, list):
                raise RuntimeError(f"FINRA non-list response for {symbol}")
            return symbol, rows
        except HTTPError as exc:
            last_error = f"http_{exc.code}"
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = type(exc).__name__
        if attempt < 2:
            import time
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"FINRA short-interest fetch failed symbol={symbol} error={last_error}")


def load_finra() -> tuple[pd.DataFrame, dict[str, Any]]:
    records: list[dict[str, Any]] = []
    symbol_counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_post_symbol, symbol): symbol for symbol in UNIVERSE}
        for future in as_completed(futures):
            symbol, rows = future.result()
            admitted = 0
            for row in rows:
                settlement_raw = row.get("settlementDate")
                current = row.get("currentShortPositionQuantity")
                previous = row.get("previousShortPositionQuantity")
                if settlement_raw is None or current is None or previous is None:
                    continue
                try:
                    settlement = pd.Timestamp(settlement_raw).date()
                    current_f = float(current)
                    previous_f = float(previous)
                except (TypeError, ValueError):
                    continue
                if not (START_SETTLEMENT <= settlement <= END_SETTLEMENT):
                    continue
                if not (math.isfinite(current_f) and math.isfinite(previous_f) and previous_f > 0):
                    continue
                change = current_f / previous_f - 1.0
                if not math.isfinite(change):
                    continue
                records.append({
                    "symbol": symbol,
                    "settlement_date": settlement,
                    "release_not_before": settlement + timedelta(days=PUBLICATION_LAG_CALENDAR_DAYS),
                    "current_short": current_f,
                    "previous_short": previous_f,
                    "short_position_change": change,
                    "days_to_cover": row.get("daysToCoverQuantity"),
                    "revision_flag": row.get("revisionFlag"),
                })
                admitted += 1
            symbol_counts[symbol] = admitted

    if not records:
        raise RuntimeError("FINRA consolidated short-interest API returned zero admitted rows")

    frame = pd.DataFrame(records)
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"])
    frame["release_not_before"] = pd.to_datetime(frame["release_not_before"])
    frame = (
        frame.sort_values(["symbol", "settlement_date"])
        .drop_duplicates(["symbol", "settlement_date"], keep="last")
        .reset_index(drop=True)
    )
    manifest_rows = [
        f"{row.symbol}|{row.settlement_date.date().isoformat()}|{row.current_short:.8f}|{row.previous_short:.8f}|{row.short_position_change:.12f}"
        for row in frame.itertuples(index=False)
    ]
    return frame, {
        "provider": "FINRA Query API / Consolidated Short Interest",
        "endpoint": FINRA_ENDPOINT,
        "requested_symbol_count": len(UNIVERSE),
        "admitted_symbol_count": int(sum(count > 0 for count in symbol_counts.values())),
        "admitted_rows": int(len(frame)),
        "rows_by_symbol": symbol_counts,
        "source_manifest_sha256": hashlib.sha256("\n".join(manifest_rows).encode("utf-8")).hexdigest(),
        "information_clock": (
            "Entry is delayed at least 14 calendar days after settlement. FINRA describes publication as the "
            "7th business day after settlement; the extra lag is a conservative chronology guard."
        ),
        "position_not_volume": True,
    }


def load_prices() -> dict[str, pd.DataFrame]:
    tickers = UNIVERSE + BENCHMARKS
    raw = yf.download(
        tickers,
        start=PRICE_START,
        end=PRICE_END_EXCLUSIVE,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if raw.empty:
        raise RuntimeError("price download returned empty frame")
    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            node = raw[ticker][["Open", "Close"]].dropna().copy()
        except Exception as exc:
            raise RuntimeError(f"price columns missing for {ticker}") from exc
        idx = pd.DatetimeIndex(node.index)
        if idx.tz is not None:
            idx = idx.tz_convert(None)
        node.index = idx.normalize()
        node = node.loc[node.index < pd.Timestamp(PRICE_END_EXCLUSIVE)]
        if len(node) < 500:
            raise RuntimeError(f"insufficient price history for {ticker}: {len(node)}")
        out[ticker] = node
    return out


def _forward_from_release(
    prices: pd.DataFrame,
    release_not_before: pd.Timestamp,
) -> tuple[float, str, str] | None:
    idx = prices.index
    eligible = np.flatnonzero(idx >= release_not_before.normalize())
    if len(eligible) == 0:
        return None
    entry_i = int(eligible[0])
    exit_i = entry_i + HOLD_SESSIONS
    if exit_i >= len(idx):
        return None
    entry_date = idx[entry_i]
    exit_date = idx[exit_i]
    if exit_date > pd.Timestamp("2025-12-31"):
        return None
    entry_px = float(prices.iloc[entry_i]["Open"])
    exit_px = float(prices.iloc[exit_i]["Close"])
    if not (entry_px > 0 and exit_px > 0):
        return None
    return exit_px / entry_px - 1.0, entry_date.date().isoformat(), exit_date.date().isoformat()


def evaluate(finra: pd.DataFrame, prices: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cost = ONE_WAY_COST_BPS / 10000.0

    for settlement_ts, snap in finra.groupby("settlement_date"):
        settlement_ts = pd.Timestamp(settlement_ts)
        release_ts = settlement_ts + pd.Timedelta(days=PUBLICATION_LAG_CALENDAR_DAYS)
        by_symbol = snap.set_index("symbol")
        for industry, spec in INDUSTRIES.items():
            candidates: list[tuple[str, float, float, str, str]] = []
            for symbol in spec["symbols"]:
                if symbol not in by_symbol.index:
                    continue
                fwd = _forward_from_release(prices[symbol], release_ts)
                if fwd is None:
                    continue
                ret, entry_date, exit_date = fwd
                change = float(by_symbol.loc[symbol, "short_position_change"])
                if math.isfinite(change):
                    candidates.append((symbol, change, ret, entry_date, exit_date))
            if len(candidates) < 4:
                continue

            candidates.sort(key=lambda x: x[1])
            k = max(1, int(math.ceil(len(candidates) * 0.25)))
            low = candidates[:k]
            high = candidates[-k:]
            low_mean = float(np.mean([x[2] for x in low]))
            high_mean = float(np.mean([x[2] for x in high]))
            neutral_gross = 0.5 * (low_mean - high_mean)
            neutral_net = neutral_gross - 2.0 * cost

            entry_date = low[0][3]
            exit_date = low[0][4]
            benchmark = spec["benchmark"]
            benchmark_prices = prices[benchmark]
            bench_entry = pd.Timestamp(entry_date)
            bench_exit = pd.Timestamp(exit_date)
            if bench_entry not in benchmark_prices.index or bench_exit not in benchmark_prices.index:
                continue
            spy_prices = prices["SPY"]
            if bench_entry not in spy_prices.index or bench_exit not in spy_prices.index:
                continue
            bench_ret = float(benchmark_prices.loc[bench_exit, "Close"] / benchmark_prices.loc[bench_entry, "Open"] - 1.0)
            spy_ret = float(spy_prices.loc[bench_exit, "Close"] / spy_prices.loc[bench_entry, "Open"] - 1.0)
            low_net = low_mean - 2.0 * cost
            bench_net = bench_ret - 2.0 * cost
            spy_net = spy_ret - 2.0 * cost

            rows.append({
                "settlement_date": settlement_ts.date().isoformat(),
                "release_not_before": release_ts.date().isoformat(),
                "entry_date": entry_date,
                "exit_date": exit_date,
                "year": int(pd.Timestamp(entry_date).year),
                "industry": industry,
                "benchmark": benchmark,
                "eligible_count": len(candidates),
                "leg_count": k,
                "low_short_change_symbols": [x[0] for x in low],
                "high_short_change_symbols": [x[0] for x in high],
                "neutral_spread_net_bps": neutral_net * 10000.0,
                "low_change_long_net_bps": low_net * 10000.0,
                "matched_etf_net_bps": bench_net * 10000.0,
                "long_excess_vs_matched_etf_bps": (low_net - bench_net) * 10000.0,
                "long_excess_vs_spy_bps": (low_net - spy_net) * 10000.0,
            })

    tape = pd.DataFrame(rows)
    if tape.empty:
        raise RuntimeError("no evaluable consolidated-short-interest snapshots")

    def summarize(group: pd.DataFrame) -> dict[str, Any]:
        return {
            "observations": int(len(group)),
            "mean_neutral_spread_net_bps": float(group["neutral_spread_net_bps"].mean()),
            "median_neutral_spread_net_bps": float(group["neutral_spread_net_bps"].median()),
            "neutral_spread_positive_rate": float((group["neutral_spread_net_bps"] > 0).mean()),
            "mean_long_excess_vs_matched_etf_bps": float(group["long_excess_vs_matched_etf_bps"].mean()),
            "mean_long_excess_vs_spy_bps": float(group["long_excess_vs_spy_bps"].mean()),
        }

    by_year = {str(int(k)): summarize(v) for k, v in tape.groupby("year")}
    by_industry = {str(k): summarize(v) for k, v in tape.groupby("industry")}
    overall = summarize(tape)
    contributions = {str(k): float(v["neutral_spread_net_bps"].sum()) for k, v in tape.groupby("industry")}
    positive = {k: max(0.0, v) for k, v in contributions.items()}
    positive_total = sum(positive.values())
    max_positive_share = max(positive.values()) / positive_total if positive_total > 0 else 1.0
    positive_years = sum(x["mean_neutral_spread_net_bps"] > 0 for x in by_year.values())
    positive_industries = sum(x["mean_neutral_spread_net_bps"] > 0 for x in by_industry.values())
    support = (
        overall["mean_neutral_spread_net_bps"] > 0
        and positive_years >= 3
        and positive_industries >= 4
        and overall["mean_long_excess_vs_matched_etf_bps"] > 0
        and max_positive_share <= 0.50
    )
    return tape, {
        "decision": "FINRA_SHORT_INTEREST_POSITIONS_R1_SUPPORTED" if support else "FINRA_SHORT_INTEREST_POSITIONS_R1_REJECTED",
        "overall": overall,
        "by_year": by_year,
        "by_industry": by_industry,
        "positive_years": positive_years,
        "required_positive_years": 3,
        "positive_industries": positive_industries,
        "required_positive_industries": 4,
        "max_positive_industry_contribution_share": max_positive_share,
        "max_allowed_positive_industry_contribution_share": 0.50,
    }


def main() -> None:
    finra, lineage = load_finra()
    prices = load_prices()
    tape, result = evaluate(finra, prices)
    out = {
        "schema": SCHEMA,
        "workload_id": "A4_FINRA_SHORT_INTEREST_POSITIONS_R1",
        "hypothesis": (
            "Large increases in twice-monthly consolidated short-interest positions contain orthogonal bearish information; "
            "within industry, low/declining short-interest-change names should outperform high/increasing names after costs."
        ),
        "scientific_distinction_from_a1": (
            "A1 used daily off-exchange short-sale transaction volume and rejected. A4 uses reported outstanding short "
            "positions at settlement dates. No A1 sign/lookback/hold rescue is performed."
        ),
        "frozen_contract": {
            "settlement_vintage": [START_SETTLEMENT.isoformat(), END_SETTLEMENT.isoformat()],
            "consolidated_all_exchange_start_guard": START_SETTLEMENT.isoformat(),
            "publication_lag_calendar_days": PUBLICATION_LAG_CALENDAR_DAYS,
            "holding_sessions": HOLD_SESSIONS,
            "one_way_cost_bps": ONE_WAY_COST_BPS,
            "signal": "currentShortPositionQuantity / previousShortPositionQuantity - 1",
            "direction": "long lowest-change quartile / short highest-change quartile within fixed industry",
            "matched_controls": ["same-industry ETF identical dates", "SPY opportunity control", "dollar-neutral industry spread"],
            "support_rule": (
                "overall after-cost neutral spread > 0; >=3 calendar years positive; >=4/5 industries positive; "
                "low-change long basket matched-ETF excess > 0; no industry >50% of positive spread contribution"
            ),
            "no_rescue": (
                "No sign, lag, hold, universe, quartile, cost, date, benchmark, short-interest transformation, or threshold rescue "
                "after terminal result. Support advances only to independent PIT-universe replication."
            ),
        },
        "panel": {
            "industries": INDUSTRIES,
            "symbol_count": len(UNIVERSE),
            "fixed_research_panel": True,
            "survivorship_bias_guard": (
                "Static 2026-known panel is a discovery panel, not PIT membership. Any support requires independent "
                "point-in-time membership replication before stronger alpha or allocation claims."
            ),
        },
        "source_lineage": lineage,
        "price_source": {
            "provider": "yfinance adjusted OHLC",
            "start": PRICE_START,
            "end_exclusive": PRICE_END_EXCLUSIVE,
            "2026_price_outcomes_used": False,
        },
        "sample": {
            "evaluated_rows": int(len(tape)),
            "first_entry_date": str(tape["entry_date"].min()),
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
    if pd.Timestamp(out["sample"]["last_exit_date"]) > pd.Timestamp("2025-12-31"):
        raise RuntimeError("2026 protected price-outcome boundary violated")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("RESULT_JSON=" + json.dumps({
        "decision": result["decision"],
        "observations": result["overall"]["observations"],
        "mean_neutral_spread_net_bps": result["overall"]["mean_neutral_spread_net_bps"],
        "mean_long_excess_vs_matched_etf_bps": result["overall"]["mean_long_excess_vs_matched_etf_bps"],
        "positive_years": result["positive_years"],
        "positive_industries": result["positive_industries"],
        "finra_rows": lineage["admitted_rows"],
        "source_manifest_sha256": lineage["source_manifest_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
