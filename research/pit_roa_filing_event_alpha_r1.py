from __future__ import annotations

import bisect
import csv
import io
import json
import statistics
import time
import urllib.request
from datetime import date
from pathlib import Path

PARENT = "PIT_FUNDAMENTAL_EVENT_ROA_R1"
INHERITED_LEARNING = [
    "P287_SEC_POINT_IN_TIME_SOURCE_ADMISSIBLE_FOR_NEXT_ECONOMIC_TEST",
    "WRAPPER_ALPHA_FAMILY_REJECT_NO_RESCUE_20260912",
]
UNRESOLVED_UNCERTAINTY = (
    "Whether a direct, filed-at SEC accounting improvement signal contains durable forward stock excess "
    "that wrapper-level fund selection could not isolate."
)
TICKER_TO_SECTOR = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AMAT": "SMH",
    "CAT": "XLI", "JPM": "XLF", "XOM": "XLE", "JNJ": "XLV",
    "PG": "XLP", "HD": "XLY",
}
SPY = "SPY"
HOLD_SESSIONS = 126
ROUND_TRIP_COST = 0.005
UA = "XoticHaze market-research point-in-time filing-event study contact@example.com"


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def get_text(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8")


def annual_roa_filings(ticker: str, cik: str):
    data = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    us = data.get("facts", {}).get("us-gaap", {})
    ni_vals = us.get("NetIncomeLoss", {}).get("units", {}).get("USD", [])
    asset_vals = us.get("Assets", {}).get("units", {}).get("USD", [])

    ni_by_accn = {}
    for v in ni_vals:
        if v.get("form") != "10-K" or v.get("fp") != "FY" or not all(v.get(k) for k in ("accn", "filed", "end", "fy", "start")):
            continue
        try:
            duration = (date.fromisoformat(v["end"]) - date.fromisoformat(v["start"])).days
        except Exception:
            continue
        if 300 <= duration <= 450:
            ni_by_accn.setdefault(v["accn"], []).append(v)

    assets_by_accn = {}
    for v in asset_vals:
        if v.get("form") != "10-K" or v.get("fp") != "FY" or not all(v.get(k) for k in ("accn", "filed", "end", "fy")):
            continue
        assets_by_accn.setdefault(v["accn"], []).append(v)

    candidates = []
    for accn, nis in ni_by_accn.items():
        current_end = max(v["end"] for v in nis)
        current_ni = [v for v in nis if v["end"] == current_end]
        current_assets = [v for v in assets_by_accn.get(accn, []) if v["end"] == current_end]
        if not current_ni or not current_assets:
            continue
        ni = current_ni[0]
        assets = current_assets[0]
        try:
            av = float(assets["val"])
            niv = float(ni["val"])
        except Exception:
            continue
        if av <= 0:
            continue
        candidates.append({
            "ticker": ticker,
            "fy": int(ni["fy"]),
            "period_end": current_end,
            "filed": ni["filed"],
            "accn": accn,
            "net_income": niv,
            "assets": av,
            "roa": niv / av,
        })

    # Freeze the first ordinary 10-K filing observed for a fiscal year. Later duplicate-tag observations
    # or amendments cannot rewrite the signal after the fact.
    by_fy = {}
    for row in sorted(candidates, key=lambda x: (x["fy"], x["filed"], x["accn"])):
        by_fy.setdefault(row["fy"], row)
    rows = sorted(by_fy.values(), key=lambda x: (x["filed"], x["fy"]))
    out = []
    for prev, cur in zip(rows, rows[1:]):
        if cur["fy"] != prev["fy"] + 1:
            continue
        z = dict(cur)
        z["prev_roa"] = prev["roa"]
        z["delta_roa"] = cur["roa"] - prev["roa"]
        out.append(z)
    return out


def stooq_prices(symbol: str):
    s = symbol.lower() + ".us"
    txt = get_text(f"https://stooq.com/q/d/l/?s={s}&d1=20000101&d2=20260912&i=d")
    rows = []
    for r in csv.DictReader(io.StringIO(txt)):
        try:
            rows.append((r["Date"], float(r["Close"])))
        except Exception:
            continue
    rows.sort()
    if len(rows) < 500:
        raise RuntimeError(f"insufficient Stooq history for {symbol}: {len(rows)} rows")
    return rows


def entry_exit(prices, filed: str):
    dates = [x[0] for x in prices]
    i = bisect.bisect_right(dates, filed)
    j = i + HOLD_SESSIONS
    if i >= len(prices) or j >= len(prices):
        return None
    return prices[i][0], prices[i][1], prices[j][0], prices[j][1]


def return_between(prices, start_date: str, end_date: str):
    dates = [x[0] for x in prices]
    i = bisect.bisect_left(dates, start_date)
    j = bisect.bisect_left(dates, end_date)
    if i >= len(prices) or j >= len(prices) or prices[i][0] > end_date or prices[j][0] > end_date:
        return None
    return prices[j][1] / prices[i][1] - 1.0


def mean(xs):
    return statistics.fmean(xs) if xs else None


def med(xs):
    return statistics.median(xs) if xs else None


def evaluate(events):
    improving = [e for e in events if e["delta_roa"] > 0]
    non_improving = [e for e in events if e["delta_roa"] <= 0]
    sec = [e["sector_excess"] for e in improving]
    spy = [e["spy_excess"] for e in improving]
    non_sec = [e["sector_excess"] for e in non_improving]

    year_rows = []
    for y in sorted({e["filed"][:4] for e in improving}):
        xs = [e["sector_excess"] for e in improving if e["filed"].startswith(y)]
        if len(xs) >= 2:
            year_rows.append({"year": int(y), "n": len(xs), "mean_sector_excess": mean(xs), "positive": mean(xs) > 0})
    positive_year_share = mean([1.0 if x["positive"] else 0.0 for x in year_rows]) if year_rows else None
    recent = [e["sector_excess"] for e in improving if e["filed"] >= "2022-01-01"]
    sign_spread = (mean(sec) - mean(non_sec)) if sec and non_sec else None

    gates = {
        "sample_at_least_30_improving_events": len(improving) >= 30,
        "mean_sector_excess_positive": bool(sec and mean(sec) > 0),
        "median_sector_excess_positive": bool(sec and med(sec) > 0),
        "mean_spy_excess_positive": bool(spy and mean(spy) > 0),
        "positive_event_share_at_least_55pct": bool(sec and mean([x > 0 for x in sec]) >= 0.55),
        "chronology_year_share_at_least_60pct": bool(positive_year_share is not None and positive_year_share >= 0.60),
        "recent_since_2022_sector_excess_positive": bool(recent and mean(recent) > 0),
        "improving_beats_non_improving": bool(sign_spread is not None and sign_spread > 0),
    }
    passed = all(gates.values())
    return {
        "improving_event_count": len(improving),
        "non_improving_event_count": len(non_improving),
        "mean_after_cost_sector_excess": mean(sec),
        "median_after_cost_sector_excess": med(sec),
        "mean_after_cost_spy_excess": mean(spy),
        "positive_sector_excess_share": mean([x > 0 for x in sec]) if sec else None,
        "year_holdouts": year_rows,
        "positive_year_share": positive_year_share,
        "recent_since_2022_mean_sector_excess": mean(recent),
        "improving_minus_non_improving_sector_excess": sign_spread,
        "gates": gates,
        "decision": "ADMIT_FOR_DISJOINT_PIT_UNIVERSE_TEST" if passed else "REJECT_NO_PARAMETER_RESCUE",
    }


def main():
    mapping = get_json("https://www.sec.gov/files/company_tickers.json")
    ciks = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in mapping.values()}
    symbols = sorted(set(TICKER_TO_SECTOR) | set(TICKER_TO_SECTOR.values()) | {SPY})
    px = {}
    for s in symbols:
        px[s] = stooq_prices(s)
        time.sleep(0.10)

    events = []
    ticker_diagnostics = {}
    for ticker, sector in TICKER_TO_SECTOR.items():
        filings = annual_roa_filings(ticker, ciks[ticker])
        used = 0
        for f in filings:
            ee = entry_exit(px[ticker], f["filed"])
            if not ee:
                continue
            entry_date, p0, exit_date, p1 = ee
            sr = return_between(px[sector], entry_date, exit_date)
            br = return_between(px[SPY], entry_date, exit_date)
            if sr is None or br is None:
                continue
            gross = p1 / p0 - 1.0
            after_cost = gross - ROUND_TRIP_COST
            events.append({
                "ticker": ticker, "sector_etf": sector, "fy": f["fy"], "filed": f["filed"],
                "accn": f["accn"], "delta_roa": f["delta_roa"], "entry_date": entry_date,
                "exit_date": exit_date, "stock_gross_return": gross, "stock_after_cost_return": after_cost,
                "sector_return": sr, "spy_return": br, "sector_excess": after_cost - sr,
                "spy_excess": after_cost - br,
            })
            used += 1
        ticker_diagnostics[ticker] = {"sector_etf": sector, "filing_pairs": len(filings), "priced_events": used}
        time.sleep(0.12)

    result = evaluate(events)
    out = {
        "schema": "research.pit_roa_filing_event_alpha_r1",
        "experiment_id": PARENT,
        "inherited_learning_ids": INHERITED_LEARNING,
        "uncertainty_resolved": UNRESOLVED_UNCERTAINTY,
        "claim_tested": "A positive year-over-year change in ROA known at the ordinary SEC 10-K filing date predicts positive 126-session after-cost stock excess versus a frozen matched-sector ETF and SPY.",
        "frozen_specification": {
            "signal": "delta(NetIncomeLoss/Assets) across consecutive fiscal-year ordinary 10-K filings",
            "information_time": "SEC filed date; enter next available trading session",
            "holding_sessions": HOLD_SESSIONS,
            "round_trip_cost": ROUND_TRIP_COST,
            "ticker_to_sector": TICKER_TO_SECTOR,
            "broad_market": SPY,
            "source": "SEC companyfacts plus Stooq daily closes",
            "accession_policy": "first ordinary 10-K accession per fiscal year; same-accession NetIncomeLoss and Assets; no later amendment rewrite",
        },
        "ticker_diagnostics": ticker_diagnostics,
        "event_count": len(events),
        "result": result,
        "events": events,
        "limitations": [
            "Fixed current-ticker cross-sector sample is a mechanism screen, not historical membership authority and not an investable-universe backtest.",
            "Stooq close series is used only for deterministic public return measurement; dividend-total-return differences may affect levels.",
            "A passing result may only admit a new child using disjoint point-in-time universe membership; it cannot promote a fund model directly.",
            "A failing result forbids rescue by changing horizon, ROA threshold, costs, ticker subset, or matched ETF after observing the result.",
        ],
        "boundaries": {"scientific_authority": True, "portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("research/artifacts").mkdir(parents=True, exist_ok=True)
    p = Path("research/artifacts/pit_roa_filing_event_alpha_r1.json")
    p.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({"experiment_id": PARENT, "event_count": len(events), **result}, sort_keys=True))


if __name__ == "__main__":
    main()
