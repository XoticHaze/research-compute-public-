from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pit_roa_filing_event_alpha_r1 as core

EXPERIMENT_ID = "PIT_FUNDAMENTAL_EVENT_CASH_CONVERSION_R1"
INHERITED_LEARNING = [
    "P287_SEC_POINT_IN_TIME_SOURCE_ADMISSIBLE_FOR_NEXT_ECONOMIC_TEST",
    "WRAPPER_ALPHA_FAMILY_REJECT_NO_RESCUE_20260912",
]
CFO_CONCEPT = "NetCashProvidedByUsedInOperatingActivities"
ORIGINAL_URLOPEN = urllib.request.urlopen


def resilient_urlopen(request, *args, **kwargs):
    last = None
    for delay in (0.0, 2.0, 5.0, 10.0):
        if delay:
            time.sleep(delay)
        try:
            return ORIGINAL_URLOPEN(request, *args, **kwargs)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
        except urllib.error.URLError as exc:
            last = exc
    raise last


urllib.request.urlopen = resilient_urlopen


def annual_cash_conversion_filings(ticker: str, cik: str):
    data = core.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    us = data.get("facts", {}).get("us-gaap", {})

    def annual_duration(concept):
        vals = us.get(concept, {}).get("units", {}).get("USD", [])
        out = {}
        for v in vals:
            if v.get("form") != "10-K" or v.get("fp") != "FY" or not all(v.get(k) for k in ("accn", "filed", "end", "fy", "start")):
                continue
            try:
                days = (date.fromisoformat(v["end"]) - date.fromisoformat(v["start"])).days
            except Exception:
                continue
            if 300 <= days <= 450:
                out.setdefault(v["accn"], []).append(v)
        return out

    def instant(concept):
        vals = us.get(concept, {}).get("units", {}).get("USD", [])
        out = {}
        for v in vals:
            if v.get("form") == "10-K" and v.get("fp") == "FY" and all(v.get(k) for k in ("accn", "filed", "end", "fy")):
                out.setdefault(v["accn"], []).append(v)
        return out

    ni = annual_duration("NetIncomeLoss")
    cfo = annual_duration(CFO_CONCEPT)
    assets = instant("Assets")
    rows = []
    for accn in sorted(set(ni) & set(cfo) & set(assets)):
        ends = set(v["end"] for v in ni[accn]) & set(v["end"] for v in cfo[accn]) & set(v["end"] for v in assets[accn])
        if not ends:
            continue
        end = max(ends)
        nv = next(v for v in ni[accn] if v["end"] == end)
        cv = next(v for v in cfo[accn] if v["end"] == end)
        av = next(v for v in assets[accn] if v["end"] == end)
        try:
            n, c, a = float(nv["val"]), float(cv["val"]), float(av["val"])
        except Exception:
            continue
        if a <= 0:
            continue
        rows.append({
            "ticker": ticker, "fy": int(nv["fy"]), "period_end": end, "filed": nv["filed"],
            "accn": accn, "net_income": n, "operating_cash_flow": c, "assets": a,
            "cash_conversion": (c - n) / a,
        })
    by_fy = {}
    for row in sorted(rows, key=lambda x: (x["fy"], x["filed"], x["accn"])):
        by_fy.setdefault(row["fy"], row)
    return sorted(by_fy.values(), key=lambda x: (x["filed"], x["fy"]))


def evaluate(events):
    backed = [e for e in events if e["cash_conversion"] > 0]
    other = [e for e in events if e["cash_conversion"] <= 0]
    sec = [e["sector_excess"] for e in backed]
    spy = [e["spy_excess"] for e in backed]
    oth = [e["sector_excess"] for e in other]
    years = []
    for y in sorted({e["filed"][:4] for e in backed}):
        xs = [e["sector_excess"] for e in backed if e["filed"].startswith(y)]
        if len(xs) >= 2:
            years.append({"year": int(y), "n": len(xs), "mean_sector_excess": core.mean(xs), "positive": core.mean(xs) > 0})
    year_share = core.mean([1.0 if x["positive"] else 0.0 for x in years]) if years else None
    recent = [e["sector_excess"] for e in backed if e["filed"] >= "2022-01-01"]
    sign_spread = (core.mean(sec) - core.mean(oth)) if sec and oth else None
    gates = {
        "sample_at_least_30_cash_backed_events": len(backed) >= 30,
        "mean_sector_excess_positive": bool(sec and core.mean(sec) > 0),
        "median_sector_excess_positive": bool(sec and core.med(sec) > 0),
        "mean_spy_excess_positive": bool(spy and core.mean(spy) > 0),
        "positive_event_share_at_least_55pct": bool(sec and core.mean([x > 0 for x in sec]) >= 0.55),
        "chronology_year_share_at_least_60pct": bool(year_share is not None and year_share >= 0.60),
        "recent_since_2022_sector_excess_positive": bool(recent and core.mean(recent) > 0),
        "cash_backed_beats_other": bool(sign_spread is not None and sign_spread > 0),
    }
    return {
        "cash_backed_event_count": len(backed), "other_event_count": len(other),
        "mean_after_cost_sector_excess": core.mean(sec), "median_after_cost_sector_excess": core.med(sec),
        "mean_after_cost_spy_excess": core.mean(spy),
        "positive_sector_excess_share": core.mean([x > 0 for x in sec]) if sec else None,
        "year_holdouts": years, "positive_year_share": year_share,
        "recent_since_2022_mean_sector_excess": core.mean(recent),
        "cash_backed_minus_other_sector_excess": sign_spread,
        "gates": gates,
        "decision": "ADMIT_FOR_DISJOINT_PIT_UNIVERSE_TEST" if all(gates.values()) else "REJECT_NO_PARAMETER_RESCUE",
    }


def main():
    mapping = core.get_json("https://www.sec.gov/files/company_tickers.json")
    ciks = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in mapping.values()}
    symbols = sorted(set(core.TICKER_TO_SECTOR) | set(core.TICKER_TO_SECTOR.values()) | {core.SPY})
    px = {s: core.stooq_prices(s) for s in symbols}
    events, diag = [], {}
    for ticker, sector in core.TICKER_TO_SECTOR.items():
        filings = annual_cash_conversion_filings(ticker, ciks[ticker])
        used = 0
        for f in filings:
            ee = core.entry_exit(px[ticker], f["filed"])
            if not ee:
                continue
            entry_date, p0, exit_date, p1 = ee
            sr = core.return_between(px[sector], entry_date, exit_date)
            br = core.return_between(px[core.SPY], entry_date, exit_date)
            if sr is None or br is None:
                continue
            gross = p1 / p0 - 1.0
            after = gross - core.ROUND_TRIP_COST
            events.append({
                "ticker": ticker, "sector_etf": sector, "fy": f["fy"], "filed": f["filed"], "accn": f["accn"],
                "cash_conversion": f["cash_conversion"], "entry_date": entry_date, "exit_date": exit_date,
                "stock_gross_return": gross, "stock_after_cost_return": after, "sector_return": sr, "spy_return": br,
                "sector_excess": after - sr, "spy_excess": after - br,
            })
            used += 1
        diag[ticker] = {"sector_etf": sector, "filings": len(filings), "priced_events": used}
        time.sleep(0.12)
    result = evaluate(events)
    out = {
        "schema": "research.pit_cash_conversion_event_alpha_r1",
        "experiment_id": EXPERIMENT_ID,
        "inherited_learning_ids": INHERITED_LEARNING,
        "uncertainty_resolved": "Whether cash-backed annual earnings known at filing time contain forward excess information distinct from simple wrapper selection and ROA-change direction.",
        "claim_tested": "Ordinary 10-K filings with operating cash flow above net income predict positive 126-session after-cost stock excess versus frozen matched-sector ETFs and SPY.",
        "frozen_specification": {
            "signal": "(NetCashProvidedByUsedInOperatingActivities - NetIncomeLoss) / Assets > 0",
            "information_time": "SEC filed date; enter next available trading session",
            "holding_sessions": core.HOLD_SESSIONS, "round_trip_cost": core.ROUND_TRIP_COST,
            "ticker_to_sector": core.TICKER_TO_SECTOR, "broad_market": core.SPY,
            "source": "SEC companyfacts plus Stooq daily closes",
            "accession_policy": "first ordinary 10-K accession per fiscal year; same-accession CFO, NetIncomeLoss and Assets",
        },
        "ticker_diagnostics": diag, "event_count": len(events), "result": result, "events": events,
        "limitations": [
            "Fixed current-ticker cross-sector sample is a mechanism screen, not historical membership authority or an investable-universe backtest.",
            "Stooq closes are deterministic public return measurements and may differ from dividend-total-return series.",
            "Passing only admits a disjoint point-in-time universe child; it cannot promote a fund model directly.",
            "Failure forbids rescue by changing cash-conversion threshold, horizon, costs, ticker subset, or matched ETF after observing the result.",
        ],
        "boundaries": {"scientific_authority": True, "portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("research/artifacts").mkdir(parents=True, exist_ok=True)
    Path("research/artifacts/pit_cash_conversion_event_alpha_r1.json").write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"experiment_id": EXPERIMENT_ID, "event_count": len(events), **result}, sort_keys=True))


if __name__ == "__main__":
    main()
