from __future__ import annotations

"""A1 FINRA short-volume R3 frozen orthogonal alpha discriminator.

Research-only. FINRA daily short-sale volume is treated as an off-exchange
microstructure feature, never as short-interest position data.

Frozen development vintage: 2022-01-03 through 2025-12-31.
2026+ is intentionally unread/protected by this workload.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

SCHEMA = "research.finra_short_volume_r3.v1"
OUT = Path("artifacts/finra_short_volume_r3.json")
FINRA_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{yyyymmdd}.txt"
START = "2022-01-03"
END = "2025-12-31"
PRICE_START = "2021-11-01"
PRICE_END_EXCLUSIVE = "2026-01-01"
LOOKBACK = 20
MIN_LOOKBACK = 15
HOLD_SESSIONS = 5
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


def _fetch_one(ts: pd.Timestamp) -> tuple[str, bytes | None, str | None]:
    ymd = ts.strftime("%Y%m%d")
    url = FINRA_URL.format(yyyymmdd=ymd)
    last_error: str | None = None
    for attempt in range(3):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 research-only FINRA short-volume study",
                    "Accept": "text/plain,*/*",
                },
            )
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
            if not raw.startswith(b"Date|Symbol|ShortVolume|"):
                return ymd, None, "unexpected_header"
            return ymd, raw, None
        except HTTPError as exc:
            # FINRA's CDN returns 403 as well as 404 for dates with no daily
            # file (for example US market holidays). Because admitted trading
            # dates succeed through the same endpoint in this run, classify
            # only these two status codes as an absent calendar-date file.
            if exc.code in {403, 404}:
                return ymd, None, "no_file"
            last_error = f"http_{exc.code}"
        except (URLError, TimeoutError) as exc:
            last_error = type(exc).__name__
        if attempt < 2:
            time.sleep(0.25 * (attempt + 1))
    return ymd, None, last_error or "fetch_failed"


def _parse_file(ymd: str, raw: bytes) -> list[dict[str, Any]]:
    wanted = set(UNIVERSE)
    totals: dict[str, list[float]] = {}
    text = raw.decode("utf-8", errors="strict")
    for line in text.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < 6:
            continue
        symbol = parts[1].strip().upper()
        if symbol not in wanted:
            continue
        try:
            short_volume = float(parts[2])
            total_volume = float(parts[4])
        except ValueError:
            continue
        if not math.isfinite(short_volume) or not math.isfinite(total_volume) or total_volume <= 0:
            continue
        bucket = totals.setdefault(symbol, [0.0, 0.0])
        bucket[0] += short_volume
        bucket[1] += total_volume
    out = []
    for symbol, (short_volume, total_volume) in totals.items():
        out.append(
            {
                "date": pd.Timestamp(ymd),
                "symbol": symbol,
                "short_volume": short_volume,
                "total_volume": total_volume,
                "short_ratio": short_volume / total_volume,
            }
        )
    return out


def load_finra() -> tuple[pd.DataFrame, dict[str, Any]]:
    weekdays = pd.date_range(START, END, freq="B")
    records: list[dict[str, Any]] = []
    identities: list[str] = []
    missing_dates: list[str] = []
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_fetch_one, ts): ts for ts in weekdays}
        for future in as_completed(futures):
            ymd, raw, error = future.result()
            if raw is None:
                if error == "no_file":
                    missing_dates.append(ymd)
                else:
                    errors[ymd] = str(error)
                continue
            identities.append(f"{ymd}:{hashlib.sha256(raw).hexdigest()}")
            records.extend(_parse_file(ymd, raw))

    if errors:
        sample = sorted(errors.items())[:10]
        raise RuntimeError(f"FINRA source fetch failures: count={len(errors)} sample={sample}")
    if not records:
        raise RuntimeError("FINRA source produced zero admitted rows")

    frame = pd.DataFrame(records).sort_values(["symbol", "date"]).reset_index(drop=True)
    frame["prior_mean20"] = frame.groupby("symbol")["short_ratio"].transform(
        lambda s: s.shift(1).rolling(LOOKBACK, min_periods=MIN_LOOKBACK).mean()
    )
    frame["prior_std20"] = frame.groupby("symbol")["short_ratio"].transform(
        lambda s: s.shift(1).rolling(LOOKBACK, min_periods=MIN_LOOKBACK).std(ddof=0)
    )
    frame["short_ratio_z20"] = (
        (frame["short_ratio"] - frame["prior_mean20"]) / frame["prior_std20"].replace(0, np.nan)
    )

    lineage_raw = "\n".join(sorted(identities)).encode("utf-8")
    lineage = {
        "provider": "FINRA Consolidated NMS Daily Short Sale Volume",
        "url_template": FINRA_URL,
        "requested_start": START,
        "requested_end": END,
        "successful_file_count": len(identities),
        "non_session_or_missing_file_count": len(missing_dates),
        "source_manifest_sha256": hashlib.sha256(lineage_raw).hexdigest(),
        "2026_or_later_finra_data_requested": False,
        "interpretation_guard": (
            "FINRA short-sale volume is off-exchange publicly disseminated trade volume; "
            "it is not short-interest position data and is not consolidated with exchange short-sale volume."
        ),
    }
    return frame, lineage


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
            node = raw[ticker][["Open", "Close"]].dropna()
        except Exception as exc:
            raise RuntimeError(f"price columns missing for {ticker}") from exc
        node = node.copy()
        idx = pd.DatetimeIndex(node.index)
        if idx.tz is not None:
            idx = idx.tz_convert(None)
        node.index = idx.normalize()
        node = node.loc[(node.index >= pd.Timestamp(PRICE_START)) & (node.index < pd.Timestamp(PRICE_END_EXCLUSIVE))]
        if len(node) < 500:
            raise RuntimeError(f"insufficient price rows for {ticker}: {len(node)}")
        out[ticker] = node
    return out


def _forward_return(
    prices: pd.DataFrame,
    signal_date: pd.Timestamp,
    hold_sessions: int = HOLD_SESSIONS,
) -> tuple[float, str, str] | None:
    idx = prices.index
    loc = idx.get_indexer([signal_date])[0]
    if loc < 0:
        return None
    entry_i = loc + 1
    exit_i = loc + hold_sessions
    if exit_i >= len(idx):
        return None
    entry_date = idx[entry_i]
    exit_date = idx[exit_i]
    if exit_date > pd.Timestamp(END):
        return None
    entry = float(prices.iloc[entry_i]["Open"])
    exit_px = float(prices.iloc[exit_i]["Close"])
    if not (entry > 0 and exit_px > 0):
        return None
    return exit_px / entry - 1.0, entry_date.date().isoformat(), exit_date.date().isoformat()


def evaluate(signals: pd.DataFrame, prices: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cost = ONE_WAY_COST_BPS / 10000.0

    by_date = {
        key: group.set_index("symbol")
        for key, group in signals.dropna(subset=["short_ratio_z20"]).groupby("date")
    }

    for signal_date, daily in sorted(by_date.items()):
        signal_date = pd.Timestamp(signal_date).normalize()
        if signal_date > pd.Timestamp(END):
            continue
        for industry, spec in INDUSTRIES.items():
            members = [s for s in spec["symbols"] if s in daily.index]
            candidates: list[tuple[str, float, float, str, str]] = []
            for symbol in members:
                forward = _forward_return(prices[symbol], signal_date)
                if forward is None:
                    continue
                ret, entry_date, exit_date = forward
                z = float(daily.loc[symbol, "short_ratio_z20"])
                if math.isfinite(z):
                    candidates.append((symbol, z, ret, entry_date, exit_date))
            if len(candidates) < 4:
                continue

            candidates.sort(key=lambda x: x[1])
            k = max(1, int(math.ceil(len(candidates) * 0.25)))
            low = candidates[:k]
            high = candidates[-k:]
            low_mean = float(np.mean([x[2] for x in low]))
            high_mean = float(np.mean([x[2] for x in high]))
            spread_gross = 0.5 * (low_mean - high_mean)
            spread_net = spread_gross - 2.0 * cost
            entry_date = low[0][3]
            exit_date = low[0][4]

            benchmark = spec["benchmark"]
            bench_forward = _forward_return(prices[benchmark], signal_date)
            spy_forward = _forward_return(prices["SPY"], signal_date)
            if bench_forward is None or spy_forward is None:
                continue
            bench_ret = bench_forward[0]
            spy_ret = spy_forward[0]
            low_net = low_mean - 2.0 * cost
            bench_net = bench_ret - 2.0 * cost
            spy_net = spy_ret - 2.0 * cost

            rows.append(
                {
                    "signal_date": signal_date.date().isoformat(),
                    "year": int(signal_date.year),
                    "industry": industry,
                    "benchmark": benchmark,
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "eligible_count": len(candidates),
                    "leg_count": k,
                    "low_short_symbols": [x[0] for x in low],
                    "high_short_symbols": [x[0] for x in high],
                    "spread_gross_bps": spread_gross * 10000.0,
                    "spread_net_bps": spread_net * 10000.0,
                    "low_short_long_net_bps": low_net * 10000.0,
                    "matched_etf_net_bps": bench_net * 10000.0,
                    "long_excess_vs_matched_etf_bps": (low_net - bench_net) * 10000.0,
                    "long_excess_vs_spy_bps": (low_net - spy_net) * 10000.0,
                }
            )

    tape = pd.DataFrame(rows)
    if tape.empty:
        raise RuntimeError("no evaluable FINRA signal rows")

    def summarize(group: pd.DataFrame) -> dict[str, Any]:
        return {
            "observations": int(len(group)),
            "mean_spread_net_bps": float(group["spread_net_bps"].mean()),
            "median_spread_net_bps": float(group["spread_net_bps"].median()),
            "spread_positive_rate": float((group["spread_net_bps"] > 0).mean()),
            "mean_long_excess_vs_matched_etf_bps": float(group["long_excess_vs_matched_etf_bps"].mean()),
            "mean_long_excess_vs_spy_bps": float(group["long_excess_vs_spy_bps"].mean()),
        }

    by_year = {
        str(int(year)): summarize(group)
        for year, group in tape.groupby("year")
    }
    by_industry = {
        str(industry): summarize(group)
        for industry, group in tape.groupby("industry")
    }
    overall = summarize(tape)

    contributions = {
        industry: float(group["spread_net_bps"].sum())
        for industry, group in tape.groupby("industry")
    }
    positive = {k: max(0.0, v) for k, v in contributions.items()}
    positive_total = sum(positive.values())
    max_positive_share = (
        max(positive.values()) / positive_total
        if positive_total > 0 and positive
        else 1.0
    )

    positive_years = sum(v["mean_spread_net_bps"] > 0 for v in by_year.values())
    positive_industries = sum(v["mean_spread_net_bps"] > 0 for v in by_industry.values())
    support = (
        overall["mean_spread_net_bps"] > 0
        and positive_years >= 3
        and positive_industries >= 4
        and overall["mean_long_excess_vs_matched_etf_bps"] > 0
        and max_positive_share <= 0.50
    )
    summary = {
        "overall": overall,
        "by_year": by_year,
        "by_industry": by_industry,
        "positive_years": positive_years,
        "required_positive_years": 3,
        "positive_industries": positive_industries,
        "required_positive_industries": 4,
        "max_positive_industry_contribution_share": max_positive_share,
        "max_allowed_positive_industry_contribution_share": 0.50,
        "decision": "FINRA_SHORT_VOLUME_R3_SUPPORTED" if support else "FINRA_SHORT_VOLUME_R3_REJECTED",
    }
    return tape, summary


def main() -> None:
    finra, lineage = load_finra()
    prices = load_prices()
    tape, summary = evaluate(finra, prices)

    out = {
        "schema": SCHEMA,
        "workload_id": "A1_FINRA_SHORT_VOLUME_R3",
        "hypothesis": (
            "Unusually high FINRA consolidated off-exchange short-sale volume relative to a symbol's own prior "
            "20-session baseline predicts near-term underperformance; a sector-neutral long-low/short-high portfolio "
            "should therefore earn positive after-cost spread return."
        ),
        "frozen_contract": {
            "development_vintage": [START, END],
            "protected_vintage": "2026+",
            "lookback_sessions": LOOKBACK,
            "minimum_prior_observations": MIN_LOOKBACK,
            "signal": "current FINRA short-volume ratio z-score versus prior 20 observations",
            "direction": "long lowest-z quartile / short highest-z quartile within each fixed industry",
            "execution": "signal available after trade-date FINRA publication; enter next session open; exit after 5 sessions at close",
            "holding_sessions": HOLD_SESSIONS,
            "one_way_cost_bps": ONE_WAY_COST_BPS,
            "matched_controls": [
                "same-industry ETF over identical entry/exit window",
                "SPY opportunity control",
                "dollar-neutral within-industry spread",
            ],
            "support_rule": (
                "overall after-cost neutral spread > 0; >=3/4 calendar years positive; >=4/5 industries positive; "
                "low-short long basket matched-ETF excess > 0; no single industry >50% of positive spread contribution"
            ),
            "no_rescue": (
                "No sign flip, lookback, hold, universe, quartile, cost, date, industry, benchmark, or threshold rescue "
                "after terminal result. Support advances only to independent/PIT-universe replication."
            ),
        },
        "panel": {
            "industries": INDUSTRIES,
            "symbol_count": len(UNIVERSE),
            "fixed_research_panel": True,
            "survivorship_bias_guard": (
                "This is a preregistered fixed high-reuse panel, not a point-in-time constituent universe. "
                "Any support requires independent replication with PIT membership before stronger claims."
            ),
        },
        "source_lineage": lineage,
        "price_source": {
            "provider": "yfinance adjusted OHLC",
            "start": PRICE_START,
            "end_exclusive": PRICE_END_EXCLUSIVE,
            "2026_price_outcomes_used": False,
        },
        "result": summary,
        "sample": {
            "signal_rows": int(len(tape)),
            "first_signal_date": str(tape["signal_date"].min()),
            "last_signal_date": str(tape["signal_date"].max()),
            "max_exit_date": str(tape["exit_date"].max()),
        },
        "boundaries": {
            "research_only": True,
            "allocation_authority": False,
            "strategy_spec_write": False,
            "runtime_mutation": False,
            "broker_action": False,
            "promotion_authority": False,
            "live_trading_change": False,
            "2026_protected": True,
        },
    }
    if pd.Timestamp(out["sample"]["max_exit_date"]) > pd.Timestamp(END):
        raise RuntimeError("protected 2026+ outcome boundary violated")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(
        "RESULT_JSON="
        + json.dumps(
            {
                "decision": summary["decision"],
                "observations": summary["overall"]["observations"],
                "mean_spread_net_bps": summary["overall"]["mean_spread_net_bps"],
                "mean_long_excess_vs_matched_etf_bps": summary["overall"]["mean_long_excess_vs_matched_etf_bps"],
                "positive_years": summary["positive_years"],
                "positive_industries": summary["positive_industries"],
                "source_file_count": lineage["successful_file_count"],
                "source_manifest_sha256": lineage["source_manifest_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
