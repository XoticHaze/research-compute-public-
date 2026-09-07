#!/usr/bin/env python3
"""Prospectively frozen P20 SEC Form 4 insider-purchase alpha discriminator.

Scientific contract:
- Public SEC filing metadata and primary Form 4 documents only.
- Semiconductor development universe is fixed before execution.
- Qualifying event is an SEC Form 4 containing open-market purchase code P,
  acquired code A, with aggregate reported purchase value >= $100,000.
- Filing date is the publication boundary. Entry is the first market session
  strictly after filing date. Hold is exactly 20 market sessions.
- Same-ticker overlapping events are suppressed to avoid double-counted capital.
- Compare exact matched windows against SMH, equal semiconductor panel, SPY,
  and QQQ. Primary cost is 25 bps per traded side with 10/25/50 bps stress.
- Five chronological folds and full-year consistency are reported.
- No parameter search, no threshold rescue, no live/runtime/allocation authority.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

UNIVERSE = ["NVDA", "AMD", "AMAT", "AVGO", "MU", "INTC", "QCOM", "TXN"]
BENCHMARKS = ["SMH", "SPY", "QQQ"]
START_DATE = dt.date(2004, 1, 1)
END_DATE = dt.date(2026, 9, 7)
HOLD_SESSIONS = 20
MIN_PURCHASE_USD = 100_000.0
PRIMARY_BPS_PER_SIDE = 25
COST_STRESS_BPS_PER_SIDE = [10, 25, 50]
USER_AGENT = os.environ.get("SEC_USER_AGENT", "MM-IBKR research xotichaze@example.com")


@dataclass(frozen=True)
class FilingEvent:
    ticker: str
    cik: int
    accession: str
    filing_date: dt.date
    primary_document: str
    purchase_value: float
    purchase_shares: float
    document_sha256: str


@dataclass(frozen=True)
class PriceSeries:
    dates: List[dt.date]
    close: List[float]


def fetch_bytes(url: str, *, sec: bool = False, retries: int = 5) -> bytes:
    headers = {
        "User-Agent": USER_AGENT if sec else "Mozilla/5.0 research-compute",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json,text/plain,*/*",
    }
    last: Optional[Exception] = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if sec:
                time.sleep(0.12)
            return data
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"fetch failed after {retries} attempts: {url}: {last}")


def fetch_json(url: str, *, sec: bool = False) -> dict:
    return json.loads(fetch_bytes(url, sec=sec).decode("utf-8"))


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value[:10])


def sec_ticker_map() -> Dict[str, int]:
    raw = fetch_json("https://www.sec.gov/files/company_tickers.json", sec=True)
    out: Dict[str, int] = {}
    for row in raw.values():
        out[str(row["ticker"]).upper()] = int(row["cik_str"])
    return out


def filing_rows(cik: int) -> Iterable[dict]:
    root = fetch_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", sec=True)
    recent = root.get("filings", {}).get("recent", {})
    keys = ["accessionNumber", "filingDate", "form", "primaryDocument"]
    n = len(recent.get("accessionNumber", []))
    for i in range(n):
        yield {k: recent.get(k, [None] * n)[i] for k in keys}
    for f in root.get("filings", {}).get("files", []):
        name = f.get("name")
        if not name:
            continue
        hist = fetch_json(f"https://data.sec.gov/submissions/{name}", sec=True)
        source = hist.get("filings", {}).get("recent", hist)
        n2 = len(source.get("accessionNumber", []))
        for i in range(n2):
            yield {k: source.get(k, [None] * n2)[i] for k in keys}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(node: ET.Element, name: str) -> Optional[str]:
    for el in node.iter():
        if local_name(el.tag) == name and el.text:
            return el.text.strip()
    return None


def form4_purchase_totals(doc: bytes) -> Tuple[float, float]:
    try:
        root = ET.fromstring(doc)
    except ET.ParseError:
        text = doc.decode("utf-8", errors="ignore")
        start = text.find("<ownershipDocument")
        end = text.rfind("</ownershipDocument>")
        if start < 0 or end < 0:
            return 0.0, 0.0
        root = ET.fromstring(text[start : end + len("</ownershipDocument>")])
    total_value = 0.0
    total_shares = 0.0
    for txn in root.iter():
        if local_name(txn.tag) != "nonDerivativeTransaction":
            continue
        code = child_text(txn, "transactionCode")
        acquired = child_text(txn, "transactionAcquiredDisposedCode")
        shares_s = child_text(txn, "transactionShares")
        price_s = child_text(txn, "transactionPricePerShare")
        if code != "P" or acquired != "A" or not shares_s or not price_s:
            continue
        try:
            shares = float(shares_s.replace(",", ""))
            price = float(price_s.replace(",", ""))
        except ValueError:
            continue
        if shares <= 0 or price <= 0:
            continue
        total_shares += shares
        total_value += shares * price
    return total_value, total_shares


def collect_events() -> Tuple[List[FilingEvent], List[dict]]:
    ticker_map = sec_ticker_map()
    events: List[FilingEvent] = []
    provenance: List[dict] = []
    for ticker in UNIVERSE:
        cik = ticker_map[ticker]
        seen_accessions = set()
        for row in filing_rows(cik):
            if row.get("form") not in {"4", "4/A"}:
                continue
            accession = str(row.get("accessionNumber") or "")
            primary = str(row.get("primaryDocument") or "")
            filing_s = str(row.get("filingDate") or "")
            if not accession or not primary or not filing_s or accession in seen_accessions:
                continue
            seen_accessions.add(accession)
            filing_date = parse_date(filing_s)
            if filing_date < START_DATE or filing_date > END_DATE:
                continue
            acc_clean = accession.replace("-", "")
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{urllib.parse.quote(primary)}"
            try:
                doc = fetch_bytes(url, sec=True)
            except Exception as exc:
                provenance.append({"ticker": ticker, "accession": accession, "status": "fetch_failed", "error": str(exc)[:200]})
                continue
            sha = hashlib.sha256(doc).hexdigest()
            value, shares = form4_purchase_totals(doc)
            provenance.append({
                "ticker": ticker,
                "cik": cik,
                "accession": accession,
                "filing_date": filing_date.isoformat(),
                "primary_document": primary,
                "document_sha256": sha,
                "purchase_value": value,
                "purchase_shares": shares,
            })
            if value >= MIN_PURCHASE_USD:
                events.append(FilingEvent(ticker, cik, accession, filing_date, primary, value, shares, sha))
    events.sort(key=lambda e: (e.filing_date, e.ticker, e.accession))
    return events, provenance


def yahoo_series(symbol: str) -> PriceSeries:
    p1 = int(dt.datetime.combine(START_DATE - dt.timedelta(days=40), dt.time(), tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime.combine(END_DATE + dt.timedelta(days=45), dt.time(), tzinfo=dt.timezone.utc).timestamp())
    q = urllib.parse.urlencode({"period1": p1, "period2": p2, "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    raw = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{q}")
    result = raw["chart"]["result"][0]
    ts = result.get("timestamp", [])
    adj = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
    if not adj:
        adj = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    dates, closes = [], []
    for t, c in zip(ts, adj):
        if c is None:
            continue
        dates.append(dt.datetime.fromtimestamp(t, tz=dt.timezone.utc).date())
        closes.append(float(c))
    if len(dates) < 100:
        raise RuntimeError(f"insufficient price rows for {symbol}: {len(dates)}")
    return PriceSeries(dates, closes)


def first_index_after(dates: Sequence[dt.date], date: dt.date) -> Optional[int]:
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] <= date:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(dates) else None


def value_on_or_before(series: PriceSeries, date: dt.date) -> Optional[float]:
    lo, hi = 0, len(series.dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if series.dates[mid] <= date:
            lo = mid + 1
        else:
            hi = mid
    idx = lo - 1
    return series.close[idx] if idx >= 0 else None


def period_return(series: PriceSeries, entry_date: dt.date, exit_date: dt.date) -> Optional[float]:
    p0 = value_on_or_before(series, entry_date)
    p1 = value_on_or_before(series, exit_date)
    if p0 is None or p1 is None or p0 <= 0:
        return None
    return p1 / p0 - 1.0


def mean(xs: Sequence[float]) -> float:
    return statistics.fmean(xs) if xs else float("nan")


def fold_slices(n: int, k: int = 5) -> List[Tuple[int, int]]:
    return [(math.floor(i*n/k), math.floor((i+1)*n/k)) for i in range(k)]


def pct(x: float) -> float:
    return round(100.0*x, 4)


def main() -> int:
    events, provenance = collect_events()
    prices = {s: yahoo_series(s) for s in UNIVERSE + BENCHMARKS}
    rows = []
    next_eligible: Dict[str, dt.date] = {}
    for ev in events:
        ps = prices[ev.ticker]
        idx = first_index_after(ps.dates, ev.filing_date)
        if idx is None or idx + HOLD_SESSIONS >= len(ps.dates):
            continue
        entry_date = ps.dates[idx]
        exit_date = ps.dates[idx + HOLD_SESSIONS]
        if ev.ticker in next_eligible and entry_date <= next_eligible[ev.ticker]:
            continue
        r_stock = ps.close[idx + HOLD_SESSIONS] / ps.close[idx] - 1.0
        comp = {}
        for b in BENCHMARKS:
            rb = period_return(prices[b], entry_date, exit_date)
            if rb is None:
                break
            comp[b] = rb
        else:
            panel = []
            for s in UNIVERSE:
                rp = period_return(prices[s], entry_date, exit_date)
                if rp is not None:
                    panel.append(rp)
            if len(panel) < 6:
                continue
            equal_semis = mean(panel)
            rows.append({
                "ticker": ev.ticker,
                "accession": ev.accession,
                "filing_date": ev.filing_date.isoformat(),
                "entry_date": entry_date.isoformat(),
                "exit_date": exit_date.isoformat(),
                "purchase_value": ev.purchase_value,
                "document_sha256": ev.document_sha256,
                "stock_gross": r_stock,
                "smh_gross": comp["SMH"],
                "spy_gross": comp["SPY"],
                "qqq_gross": comp["QQQ"],
                "equal_semis_gross": equal_semis,
            })
            next_eligible[ev.ticker] = exit_date
    if len(rows) < 20:
        raise RuntimeError(f"insufficient qualifying matched events: {len(rows)}")

    rows.sort(key=lambda r: (r["entry_date"], r["ticker"], r["accession"]))
    primary_rt = 2 * PRIMARY_BPS_PER_SIDE / 10000.0
    for r in rows:
        for key in ["stock", "smh", "spy", "qqq", "equal_semis"]:
            r[f"{key}_net_primary"] = r[f"{key}_gross"] - primary_rt
        r["excess_smh_primary"] = r["stock_net_primary"] - r["smh_net_primary"]
        r["excess_equal_semis_primary"] = r["stock_net_primary"] - r["equal_semis_net_primary"]
        r["excess_spy_primary"] = r["stock_net_primary"] - r["spy_net_primary"]
        r["excess_qqq_primary"] = r["stock_net_primary"] - r["qqq_net_primary"]

    folds = []
    for i, (a, b) in enumerate(fold_slices(len(rows)), 1):
        rr = rows[a:b]
        folds.append({
            "fold": i,
            "n": len(rr),
            "first_entry": rr[0]["entry_date"],
            "last_entry": rr[-1]["entry_date"],
            "mean_stock_net_pct": pct(mean([x["stock_net_primary"] for x in rr])),
            "mean_excess_smh_pct": pct(mean([x["excess_smh_primary"] for x in rr])),
            "mean_excess_equal_semis_pct": pct(mean([x["excess_equal_semis_primary"] for x in rr])),
        })

    by_year: Dict[int, List[dict]] = {}
    for r in rows:
        by_year.setdefault(int(r["entry_date"][:4]), []).append(r)
    years = []
    for y in sorted(by_year):
        rr = by_year[y]
        years.append({
            "year": y,
            "n": len(rr),
            "mean_stock_net_pct": pct(mean([x["stock_net_primary"] for x in rr])),
            "mean_excess_smh_pct": pct(mean([x["excess_smh_primary"] for x in rr])),
            "mean_excess_equal_semis_pct": pct(mean([x["excess_equal_semis_primary"] for x in rr])),
        })
    eligible_years = [y for y in years if y["n"] >= 3]

    stress = []
    for bps in COST_STRESS_BPS_PER_SIDE:
        rt = 2*bps/10000.0
        stock_net = [r["stock_gross"] - rt for r in rows]
        stress.append({
            "bps_per_side": bps,
            "mean_stock_net_pct": pct(mean(stock_net)),
            "positive_event_rate": round(sum(x > 0 for x in stock_net)/len(stock_net), 4),
            "mean_excess_smh_pct": pct(mean([r["stock_gross"] - r["smh_gross"] for r in rows])),
            "mean_excess_equal_semis_pct": pct(mean([r["stock_gross"] - r["equal_semis_gross"] for r in rows])),
        })

    fold_wins_both = sum(f["mean_excess_smh_pct"] > 0 and f["mean_excess_equal_semis_pct"] > 0 for f in folds)
    year_wins_smh = sum(y["mean_excess_smh_pct"] > 0 for y in eligible_years)
    year_wins_equal = sum(y["mean_excess_equal_semis_pct"] > 0 for y in eligible_years)
    agg_excess_smh = mean([r["excess_smh_primary"] for r in rows])
    agg_excess_equal = mean([r["excess_equal_semis_primary"] for r in rows])
    support = (
        len(rows) >= 40
        and agg_excess_smh > 0
        and agg_excess_equal > 0
        and fold_wins_both >= 3
        and (not eligible_years or year_wins_smh / len(eligible_years) >= 0.60)
        and (not eligible_years or year_wins_equal / len(eligible_years) >= 0.60)
        and stress[-1]["mean_stock_net_pct"] > 0
    )
    decision = "P20_SEC_INSIDER_PURCHASE_SUPPORTED_FOR_EXTERNAL_HOLDOUT" if support else "P20_SEC_INSIDER_PURCHASE_NOT_SUPPORTED"

    receipt = {
        "schema": "research.p20_sec_insider_purchase_alpha.v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "decision": decision,
        "scientific_contract": {
            "universe": UNIVERSE,
            "source": "SEC submissions metadata + accession-bound primary Form 4 documents",
            "publication_boundary": "filing_date; enter first market session strictly after filing date",
            "qualifying_transaction": "nonDerivativeTransaction transactionCode=P and acquiredDisposedCode=A",
            "min_aggregate_purchase_usd": MIN_PURCHASE_USD,
            "hold_sessions": HOLD_SESSIONS,
            "same_ticker_overlap": "suppressed until prior 20-session event exits",
            "primary_bps_per_side": PRIMARY_BPS_PER_SIDE,
            "cost_stress_bps_per_side": COST_STRESS_BPS_PER_SIDE,
            "matched_controls": ["SMH", "equal_semiconductor_panel", "SPY", "QQQ"],
            "no_parameter_search": True,
        },
        "matched_window": {
            "first_entry": rows[0]["entry_date"],
            "last_exit": rows[-1]["exit_date"],
            "events": len(rows),
            "tickers_with_events": sorted(set(r["ticker"] for r in rows)),
        },
        "aggregate_primary": {
            "mean_stock_net_pct": pct(mean([r["stock_net_primary"] for r in rows])),
            "mean_smh_net_pct": pct(mean([r["smh_net_primary"] for r in rows])),
            "mean_equal_semis_net_pct": pct(mean([r["equal_semis_net_primary"] for r in rows])),
            "mean_spy_net_pct": pct(mean([r["spy_net_primary"] for r in rows])),
            "mean_qqq_net_pct": pct(mean([r["qqq_net_primary"] for r in rows])),
            "mean_excess_smh_pct": pct(agg_excess_smh),
            "mean_excess_equal_semis_pct": pct(agg_excess_equal),
            "mean_excess_spy_pct": pct(mean([r["excess_spy_primary"] for r in rows])),
            "mean_excess_qqq_pct": pct(mean([r["excess_qqq_primary"] for r in rows])),
            "positive_event_rate": round(sum(r["stock_net_primary"] > 0 for r in rows)/len(rows), 4),
            "beat_smh_event_rate": round(sum(r["excess_smh_primary"] > 0 for r in rows)/len(rows), 4),
            "beat_equal_semis_event_rate": round(sum(r["excess_equal_semis_primary"] > 0 for r in rows)/len(rows), 4),
        },
        "folds": folds,
        "eligible_full_years_min3_events": eligible_years,
        "year_consistency": {
            "eligible_year_count": len(eligible_years),
            "years_positive_excess_smh": year_wins_smh,
            "years_positive_excess_equal_semis": year_wins_equal,
        },
        "cost_stress": stress,
        "events": rows,
        "source_provenance": provenance,
        "protected_boundaries": {
            "strategy_spec_mutation": False,
            "runtime_authority_change": False,
            "allocation_authority": False,
            "broker_submission": False,
            "live_trading_change": False,
        },
    }
    out = os.environ.get("P20_OUTPUT", "p20_sec_insider_purchase_alpha_receipt.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({
        "decision": decision,
        "events": len(rows),
        "first_entry": rows[0]["entry_date"],
        "last_exit": rows[-1]["exit_date"],
        "mean_stock_net_pct": receipt["aggregate_primary"]["mean_stock_net_pct"],
        "mean_excess_smh_pct": receipt["aggregate_primary"]["mean_excess_smh_pct"],
        "mean_excess_equal_semis_pct": receipt["aggregate_primary"]["mean_excess_equal_semis_pct"],
        "fold_wins_both": fold_wins_both,
        "eligible_years": len(eligible_years),
        "year_wins_smh": year_wins_smh,
        "year_wins_equal": year_wins_equal,
        "output": out,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
