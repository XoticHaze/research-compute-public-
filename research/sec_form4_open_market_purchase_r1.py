from __future__ import annotations

"""A5 SEC Form 4 open-market purchase filing event study R1.

Orthogonal new-alpha discovery after the short-sale-volume and short-interest
families rejected.  Uses the SEC's official quarterly Insider Transactions Data
Sets, not a bespoke filing parser.

Information time is FILING_DATE.  Transaction date is never used for entry.
"""

from datetime import date
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

import numpy as np
import pandas as pd
import yfinance as yf

SCHEMA = "research.sec_form4_open_market_purchase_r1.v1"
OUT = Path("artifacts/sec_form4_open_market_purchase_r1.json")
ZIP_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{year}q{quarter}_form345.zip"
YEARS = (2022, 2023, 2024, 2025)
QUARTERS = (1, 2, 3, 4)
PRICE_START = "2021-12-01"
PRICE_END_EXCLUSIVE = "2026-01-01"
HOLD_SESSIONS = 5
STOCK_ROUNDTRIP_COST_BPS = 25.0
ETF_ROUNDTRIP_COST_BPS = 10.0
MIN_EVENTS_FOR_DECISION = 40

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
SYMBOL_TO_INDUSTRY = {
    symbol: industry
    for industry, spec in INDUSTRIES.items()
    for symbol in spec["symbols"]
}
UNIVERSE = sorted(SYMBOL_TO_INDUSTRY)
BENCHMARKS = sorted({spec["benchmark"] for spec in INDUSTRIES.values()} | {"SPY"})


def _download_zip(year: int, quarter: int) -> tuple[bytes, dict[str, Any]]:
    url = ZIP_URL.format(year=year, quarter=quarter)
    last: str | None = None
    for attempt in range(3):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 "
                        "XoticHaze-research https://github.com/XoticHaze/research-compute-public-"
                    ),
                    "Accept": "application/zip,application/octet-stream,*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets",
                    "Connection": "close",
                },
            )
            with urlopen(req, timeout=90) as resp:
                raw = resp.read()
            if len(raw) < 1000 or raw[:2] != b"PK":
                raise RuntimeError(f"invalid SEC zip payload {year}Q{quarter}")
            return raw, {
                "year": year,
                "quarter": quarter,
                "url": url,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            last = f"{type(exc).__name__}:{exc}"
            if attempt < 2:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"SEC zip download failed {year}Q{quarter}: {last}")


def _read_member(z: zipfile.ZipFile, member: str, wanted: set[str]) -> pd.DataFrame:
    names = {name.upper(): name for name in z.namelist()}
    actual = names.get(member.upper())
    if actual is None:
        raise RuntimeError(f"SEC zip missing {member}; members={sorted(z.namelist())[:12]}")
    with z.open(actual) as handle:
        frame = pd.read_csv(
            handle,
            sep="\t",
            dtype=str,
            low_memory=False,
            usecols=lambda name: name in wanted,
        )
    for name in wanted:
        if name not in frame.columns:
            frame[name] = pd.NA
    return frame[list(sorted(wanted))]


def load_events() -> tuple[pd.DataFrame, dict[str, Any]]:
    issuer_days: list[pd.DataFrame] = []
    zip_meta: list[dict[str, Any]] = []

    for year in YEARS:
        for quarter in QUARTERS:
            raw, meta = _download_zip(year, quarter)
            zip_meta.append(meta)
            with zipfile.ZipFile(BytesIO(raw)) as z:
                sub = _read_member(
                    z,
                    "SUBMISSION.tsv",
                    {
                        "ACCESSION_NUMBER",
                        "FILING_DATE",
                        "DOCUMENT_TYPE",
                        "ISSUERTRADINGSYMBOL",
                    },
                )
                tx = _read_member(
                    z,
                    "NONDERIV_TRANS.tsv",
                    {
                        "ACCESSION_NUMBER",
                        "TRANS_CODE",
                        "TRANS_SHARES",
                        "TRANS_PRICEPERSHARE",
                        "TRANS_ACQUIRED_DISP_CD",
                    },
                )

            sub["ISSUERTRADINGSYMBOL"] = sub["ISSUERTRADINGSYMBOL"].astype(str).str.upper().str.strip()
            sub = sub[
                (sub["DOCUMENT_TYPE"].astype(str).str.strip() == "4")
                & sub["ISSUERTRADINGSYMBOL"].isin(UNIVERSE)
            ].copy()
            if sub.empty:
                time.sleep(0.15)
                continue
            tx = tx[
                (tx["TRANS_CODE"].astype(str).str.strip() == "P")
                & (tx["TRANS_ACQUIRED_DISP_CD"].astype(str).str.strip() == "A")
            ].copy()
            if tx.empty:
                time.sleep(0.15)
                continue

            tx["TRANS_SHARES"] = pd.to_numeric(tx["TRANS_SHARES"], errors="coerce")
            tx["TRANS_PRICEPERSHARE"] = pd.to_numeric(tx["TRANS_PRICEPERSHARE"], errors="coerce")
            tx = tx[
                tx["TRANS_SHARES"].gt(0)
                & tx["TRANS_PRICEPERSHARE"].gt(0)
                & np.isfinite(tx["TRANS_SHARES"])
                & np.isfinite(tx["TRANS_PRICEPERSHARE"])
            ].copy()
            tx["purchase_notional"] = tx["TRANS_SHARES"] * tx["TRANS_PRICEPERSHARE"]

            merged = tx.merge(
                sub[["ACCESSION_NUMBER", "FILING_DATE", "ISSUERTRADINGSYMBOL"]],
                on="ACCESSION_NUMBER",
                how="inner",
                validate="many_to_one",
            )
            if merged.empty:
                time.sleep(0.15)
                continue
            merged["FILING_DATE"] = pd.to_datetime(merged["FILING_DATE"], errors="coerce")
            merged = merged[
                merged["FILING_DATE"].notna()
                & merged["FILING_DATE"].between("2022-01-01", "2025-12-31")
            ]
            if merged.empty:
                time.sleep(0.15)
                continue

            day = (
                merged.groupby(["ISSUERTRADINGSYMBOL", "FILING_DATE"], as_index=False)
                .agg(
                    accession_count=("ACCESSION_NUMBER", "nunique"),
                    purchase_row_count=("ACCESSION_NUMBER", "size"),
                    purchase_notional=("purchase_notional", "sum"),
                )
                .rename(columns={"ISSUERTRADINGSYMBOL": "symbol", "FILING_DATE": "filing_date"})
            )
            issuer_days.append(day)
            time.sleep(0.15)

    if not issuer_days:
        raise RuntimeError("SEC bulk data produced zero admitted issuer-day purchase events")

    events = pd.concat(issuer_days, ignore_index=True)
    events = (
        events.groupby(["symbol", "filing_date"], as_index=False)
        .agg(
            accession_count=("accession_count", "sum"),
            purchase_row_count=("purchase_row_count", "sum"),
            purchase_notional=("purchase_notional", "sum"),
        )
        .sort_values(["filing_date", "symbol"])
        .reset_index(drop=True)
    )
    events["industry"] = events["symbol"].map(SYMBOL_TO_INDUSTRY)
    lineage_text = "\n".join(f"{x['year']}Q{x['quarter']}:{x['sha256']}" for x in zip_meta)
    return events, {
        "provider": "U.S. SEC Insider Transactions Data Sets",
        "quarters": zip_meta,
        "quarter_count": len(zip_meta),
        "zip_manifest_sha256": hashlib.sha256(lineage_text.encode("utf-8")).hexdigest(),
        "document_type": "Form 4 only; amendments excluded",
        "transaction_filter": "non-derivative code P + acquired A + positive shares + positive price",
        "information_time": "FILING_DATE",
        "transaction_date_used_for_entry": False,
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
        out[ticker] = node
    return out


def _event_return(prices: pd.DataFrame, filing_date: pd.Timestamp) -> tuple[float, str, str] | None:
    idx = prices.index
    eligible = np.flatnonzero(idx > filing_date.normalize())
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


def evaluate(events: pd.DataFrame, prices: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stock_cost = STOCK_ROUNDTRIP_COST_BPS / 10000.0
    etf_cost = ETF_ROUNDTRIP_COST_BPS / 10000.0

    for event in events.itertuples(index=False):
        stock = _event_return(prices[event.symbol], pd.Timestamp(event.filing_date))
        if stock is None:
            continue
        stock_gross, entry_date, exit_date = stock
        industry = str(event.industry)
        benchmark = INDUSTRIES[industry]["benchmark"]
        bpx = prices[benchmark]
        spx = prices["SPY"]
        entry_ts = pd.Timestamp(entry_date)
        exit_ts = pd.Timestamp(exit_date)
        if entry_ts not in bpx.index or exit_ts not in bpx.index or entry_ts not in spx.index or exit_ts not in spx.index:
            continue
        bench_gross = float(bpx.loc[exit_ts, "Close"] / bpx.loc[entry_ts, "Open"] - 1.0)
        spy_gross = float(spx.loc[exit_ts, "Close"] / spx.loc[entry_ts, "Open"] - 1.0)
        stock_net = stock_gross - stock_cost
        bench_net = bench_gross - etf_cost
        spy_net = spy_gross - etf_cost
        rows.append({
            "symbol": event.symbol,
            "industry": industry,
            "benchmark": benchmark,
            "filing_date": pd.Timestamp(event.filing_date).date().isoformat(),
            "entry_date": entry_date,
            "exit_date": exit_date,
            "year": int(pd.Timestamp(entry_date).year),
            "purchase_notional": float(event.purchase_notional),
            "purchase_row_count": int(event.purchase_row_count),
            "accession_count": int(event.accession_count),
            "stock_net_bps": stock_net * 10000.0,
            "matched_etf_net_bps": bench_net * 10000.0,
            "spy_net_bps": spy_net * 10000.0,
            "excess_vs_matched_etf_bps": (stock_net - bench_net) * 10000.0,
            "excess_vs_spy_bps": (stock_net - spy_net) * 10000.0,
        })

    tape = pd.DataFrame(rows)
    if tape.empty:
        raise RuntimeError("no scoreable Form 4 purchase events")

    def summary(group: pd.DataFrame) -> dict[str, Any]:
        return {
            "events": int(len(group)),
            "mean_stock_net_bps": float(group["stock_net_bps"].mean()),
            "mean_excess_vs_matched_etf_bps": float(group["excess_vs_matched_etf_bps"].mean()),
            "median_excess_vs_matched_etf_bps": float(group["excess_vs_matched_etf_bps"].median()),
            "matched_excess_positive_rate": float((group["excess_vs_matched_etf_bps"] > 0).mean()),
            "mean_excess_vs_spy_bps": float(group["excess_vs_spy_bps"].mean()),
        }

    overall = summary(tape)
    by_year = {str(int(k)): summary(v) for k, v in tape.groupby("year")}
    by_industry = {str(k): summary(v) for k, v in tape.groupby("industry")}
    positive_years = sum(v["mean_excess_vs_matched_etf_bps"] > 0 for v in by_year.values())
    positive_industries = sum(v["mean_excess_vs_matched_etf_bps"] > 0 for v in by_industry.values())
    contrib = {str(k): float(v["excess_vs_matched_etf_bps"].sum()) for k, v in tape.groupby("industry")}
    positive = {k: max(0.0, v) for k, v in contrib.items()}
    pos_total = sum(positive.values())
    max_share = max(positive.values()) / pos_total if pos_total > 0 else 1.0
    decision_ready = len(tape) >= MIN_EVENTS_FOR_DECISION and len(by_year) >= 3 and len(by_industry) >= 4
    support = (
        decision_ready
        and overall["mean_excess_vs_matched_etf_bps"] > 0
        and overall["mean_excess_vs_spy_bps"] > 0
        and overall["matched_excess_positive_rate"] > 0.50
        and positive_years >= 3
        and positive_industries >= 4
        and max_share <= 0.50
    )
    if not decision_ready:
        decision = "SEC_FORM4_PURCHASE_R1_INCONCLUSIVE_SAMPLE"
    else:
        decision = "SEC_FORM4_PURCHASE_R1_SUPPORTED" if support else "SEC_FORM4_PURCHASE_R1_REJECTED"
    return tape, {
        "decision": decision,
        "overall": overall,
        "by_year": by_year,
        "by_industry": by_industry,
        "positive_years": positive_years,
        "required_positive_years": 3,
        "positive_industries": positive_industries,
        "required_positive_industries": 4,
        "max_positive_industry_contribution_share": max_share,
        "max_allowed_positive_industry_contribution_share": 0.50,
        "minimum_events_for_decision": MIN_EVENTS_FOR_DECISION,
    }


def main() -> None:
    events, lineage = load_events()
    prices = load_prices()
    tape, result = evaluate(events, prices)
    out = {
        "schema": SCHEMA,
        "workload_id": "A5_SEC_FORM4_OPEN_MARKET_PURCHASE_R1",
        "hypothesis": (
            "Public Form 4 disclosure of non-derivative open-market insider purchases contains short-horizon issuer information; "
            "the issuer should outperform its matched industry ETF and SPY over the next five sessions after costs."
        ),
        "frozen_contract": {
            "filing_vintage": ["2022-01-01", "2025-12-31"],
            "information_clock": "FILING_DATE; enter next market session open",
            "transaction_filter": "Form 4, non-derivative code P, acquired A, positive shares and price",
            "issuer_day_aggregation": "all qualifying accessions/rows for one issuer filing date become one event",
            "holding_sessions": HOLD_SESSIONS,
            "stock_roundtrip_cost_bps": STOCK_ROUNDTRIP_COST_BPS,
            "etf_roundtrip_cost_bps": ETF_ROUNDTRIP_COST_BPS,
            "matched_controls": ["industry ETF identical entry/exit", "SPY identical entry/exit"],
            "support_rule": (
                ">=40 events; mean after-cost excess vs industry ETF >0 and SPY >0; >50% event matched-excess hit rate; "
                ">=3 positive years; >=4/5 positive industries; no industry >50% of positive matched-excess contribution"
            ),
            "no_rescue": (
                "No owner-title, purchase-size, cluster-count, transaction-date, hold, cost, universe, year, industry, "
                "benchmark, 10b5-1, or threshold rescue after terminal result. Any later refinement requires an independently "
                "preregistered information mechanism and untouched evidence."
            ),
        },
        "panel": {
            "industries": INDUSTRIES,
            "symbol_count": len(UNIVERSE),
            "fixed_research_panel": True,
            "pit_limitation": "Current-known panel is discovery-only; support requires PIT-universe replication before stronger claims.",
        },
        "source_lineage": lineage,
        "sample": {
            "raw_issuer_day_purchase_events": int(len(events)),
            "scoreable_events": int(len(tape)),
            "first_filing_date": str(events["filing_date"].min().date()),
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
            "2026_price_outcomes_protected": True,
        },
    }
    if pd.Timestamp(out["sample"]["last_exit_date"]) > pd.Timestamp("2025-12-31"):
        raise RuntimeError("2026 protected outcome boundary violated")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("RESULT_JSON=" + json.dumps({
        "decision": result["decision"],
        "events": result["overall"]["events"],
        "mean_excess_vs_matched_etf_bps": result["overall"]["mean_excess_vs_matched_etf_bps"],
        "mean_excess_vs_spy_bps": result["overall"]["mean_excess_vs_spy_bps"],
        "positive_years": result["positive_years"],
        "positive_industries": result["positive_industries"],
        "zip_manifest_sha256": lineage["zip_manifest_sha256"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
