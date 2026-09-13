#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

SYMBOLS = ("DHI", "LEN", "PHM", "NVR", "TOL", "MTH", "KBH", "LGIH", "DFH")
DEV = SYMBOLS[:-1]
EXTERNAL = "DFH"
START = "2019-01-01"
END_EXCLUSIVE = "2026-09-14"
MAX_STALE_DAYS = 200
OUTPUT = Path("research/results/homebuilder_pit_valuation_source_probe_r1.json")
USER_AGENT = "research-compute valuation-source-probe/1.0 contact@example.com"
SHARE_CONCEPTS = (("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding"))
EQUITY_CONCEPTS = (("us-gaap", "StockholdersEquity"), ("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))


def get_json(url: str, user_agent: str = USER_AGENT):
    req = Request(url, headers={"User-Agent": user_agent})
    with urlopen(req, timeout=45) as r:  # noqa: S310 fixed HTTPS hosts only
        return json.loads(r.read().decode("utf-8"))


def epoch(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp())


def yahoo_raw_close(symbol: str) -> pd.Series:
    q = urlencode({"period1": epoch(START), "period2": epoch(END_EXCLUSIVE), "interval": "1d", "events": "history", "includeAdjustedClose": "true"})
    payload = get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{q}", "Mozilla/5.0 research-compute/1.0")
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: no Yahoo chart")
    tz = result.get("meta", {}).get("exchangeTimezoneName") or "America/New_York"
    idx = pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True).tz_convert(tz).normalize().tz_localize(None)
    close = ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
    s = pd.Series(pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(), index=idx, name=symbol).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def ticker_ciks():
    data = get_json("https://www.sec.gov/files/company_tickers.json")
    return {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}


def facts_for(cik: int):
    return get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")


def concept_units(payload, taxonomy: str, concept: str):
    units = payload.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {})
    if not units:
        return []
    preferred = "shares" if "Shares" in concept or "shares" in concept else "USD"
    if units.get(preferred):
        return units[preferred]
    return units[sorted(units)[0]]


def select_instant(payload, concepts, asof: pd.Timestamp):
    asof_d = asof.date()
    for taxonomy, concept in concepts:
        candidates = []
        for f in concept_units(payload, taxonomy, concept):
            end, filed, val = f.get("end"), f.get("filed"), f.get("val")
            if end is None or filed is None or val is None:
                continue
            try:
                end_d, filed_d, val_f = date.fromisoformat(end), date.fromisoformat(filed), float(val)
            except Exception:
                continue
            if not math.isfinite(val_f) or val_f <= 0:
                continue
            if filed_d <= asof_d and end_d <= asof_d and (asof_d - end_d).days <= MAX_STALE_DAYS:
                candidates.append((end_d, filed_d, val_f, concept, taxonomy, f.get("form")))
        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            end_d, filed_d, val_f, concept_name, taxonomy_name, form = candidates[0]
            return {"value": val_f, "concept": concept_name, "taxonomy": taxonomy_name, "end": end_d.isoformat(), "filed": filed_d.isoformat(), "form": form, "staleness_days": (asof_d - end_d).days}
    return None


def month_ends(start="2019-01-31", end="2026-09-12"):
    return list(pd.date_range(start=start, end=end, freq="ME")) + [pd.Timestamp(end)]


def latest_price(prices: pd.Series, asof: pd.Timestamp):
    x = prices.loc[prices.index <= asof]
    if x.empty:
        return None
    d = x.index[-1]
    if (asof - d).days > 7:
        return None
    return {"date": d.date().isoformat(), "raw_close": float(x.iloc[-1])}


def main():
    ciks = ticker_ciks()
    rows_by_symbol, diagnostics = {}, {}
    for symbol in SYMBOLS:
        if symbol not in ciks:
            raise RuntimeError(f"missing CIK for {symbol}")
        prices, cf = yahoo_raw_close(symbol), facts_for(ciks[symbol])
        time.sleep(0.12)
        rows, concepts_seen = [], {"shares": set(), "equity": set()}
        for asof in month_ends():
            if asof < prices.index.min() or asof > prices.index.max() + pd.Timedelta(days=7):
                continue
            px, sh, eq = latest_price(prices, asof), select_instant(cf, SHARE_CONCEPTS, asof), select_instant(cf, EQUITY_CONCEPTS, asof)
            if not px or not sh or not eq:
                continue
            mcap = sh["value"] * px["raw_close"]
            btm = eq["value"] / mcap if mcap > 0 else float("nan")
            if not (math.isfinite(mcap) and math.isfinite(btm)):
                continue
            if not (1e8 <= mcap <= 2e11 and 0.01 <= btm <= 10.0):
                continue
            concepts_seen["shares"].add(sh["concept"]); concepts_seen["equity"].add(eq["concept"])
            rows.append({"asof": asof.date().isoformat(), "price_date": px["date"], "raw_close": px["raw_close"], "shares": sh["value"], "shares_concept": sh["concept"], "shares_end": sh["end"], "shares_filed": sh["filed"], "shares_staleness_days": sh["staleness_days"], "equity": eq["value"], "equity_concept": eq["concept"], "equity_end": eq["end"], "equity_filed": eq["filed"], "equity_staleness_days": eq["staleness_days"], "market_cap": mcap, "book_to_market": btm})
        rows_by_symbol[symbol] = rows
        vals = [r["book_to_market"] for r in rows]
        diagnostics[symbol] = {"cik": ciks[symbol], "eligible_months": len(rows), "first_eligible": rows[0]["asof"] if rows else None, "last_eligible": rows[-1]["asof"] if rows else None, "shares_concepts_used": sorted(concepts_seen["shares"]), "equity_concepts_used": sorted(concepts_seen["equity"]), "book_to_market_min": min(vals, default=None), "book_to_market_median": float(pd.Series(vals).median()) if vals else None, "book_to_market_max": max(vals, default=None), "market_cap_min": min((r["market_cap"] for r in rows), default=None), "market_cap_max": max((r["market_cap"] for r in rows), default=None)}
    gates = {"all_dev_min_72_months": all(diagnostics[s]["eligible_months"] >= 72 for s in DEV), "dfh_min_48_months": diagnostics[EXTERNAL]["eligible_months"] >= 48, "all_symbols_have_share_and_equity_concepts": all(diagnostics[s]["shares_concepts_used"] and diagnostics[s]["equity_concepts_used"] for s in SYMBOLS)}
    result = {"schema": "public.homebuilder_pit_valuation_source_probe_r1.v1", "experiment_id": "HOMEBUILDER-PIT-VALUATION-SOURCE-PROBE-R1", "claim_tested": "Whether filed-at SEC instant shares and equity can be joined to contemporaneous unadjusted market closes with enough point-in-time coverage to test Homebuilder book-to-market without split-basis lookahead.", "information_contract": {"sec_fact_filed_lte_signal": True, "sec_fact_end_lte_signal": True, "max_fact_staleness_days": MAX_STALE_DAYS, "market_price": "Yahoo raw close on or before signal; no adjusted-close market-cap multiplication", "shares_fallback": [x[1] for x in SHARE_CONCEPTS], "equity_fallback": [x[1] for x in EQUITY_CONCEPTS], "economic_outcomes_examined": False}, "diagnostics": diagnostics, "gates": gates, "decision": "HOMEBUILDER_PIT_VALUATION_SOURCE_ADMITTED" if all(gates.values()) else "HOMEBUILDER_PIT_VALUATION_SOURCE_REJECTED", "rows_by_symbol": rows_by_symbol, "authority": "SOURCE_CONTRACT_ONLY", "portfolio_allocation_authority": False, "live_trading_change": False}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": result["decision"], "diagnostics": diagnostics, "gates": gates}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
