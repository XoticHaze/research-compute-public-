from __future__ import annotations

"""Source-only point-in-time SEC fundamental coverage preflight.

No return/path target is computed here.  Every candidate observation is keyed by the
SEC filing date carried by Company Facts, so a later consumer can use only filings
known on or before a signal date and cannot leak a later restatement backward.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("semiconductor_sec_fundamental_preflight_20260906.json")
SYMBOLS = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")
START_FILED = "2014-01-01"
CUTOFF_FILED = "2026-09-03"
FORMS = {"10-Q", "10-K", "20-F", "40-F"}
MIN_DISTINCT_FILINGS = 16
MIN_FILED_YEARS = 8
USER_AGENT = "XoticHaze research-compute-public- 152584286+XoticHaze@users.noreply.github.com"

# Semantic categories are frozen before any model outcome.  Candidate tags only
# bridge US-GAAP / IFRS naming differences; the downstream feature meaning is the
# category, never a symbol-specific post-hoc feature choice.
CANDIDATES = {
    "revenue": (
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "SalesRevenueNet"),
        ("us-gaap", "Revenues"),
        ("ifrs-full", "Revenue"),
    ),
    "gross_profit": (
        ("us-gaap", "GrossProfit"),
        ("ifrs-full", "GrossProfit"),
    ),
    "operating_income": (
        ("us-gaap", "OperatingIncomeLoss"),
        ("ifrs-full", "ProfitLossFromOperatingActivities"),
    ),
    "assets": (
        ("us-gaap", "Assets"),
        ("ifrs-full", "Assets"),
    ),
    "inventory": (
        ("us-gaap", "InventoryNet"),
        ("us-gaap", "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"),
        ("ifrs-full", "Inventories"),
    ),
    "cash": (
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue"),
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
        ("ifrs-full", "CashAndCashEquivalents"),
    ),
}


def get_json(url: str):
    last = None
    for attempt in range(3):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # retain deterministic terminal evidence
            last = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET failed after 3 attempts: {url}: {last}")


def resolve_ciks():
    payload = get_json("https://www.sec.gov/files/company_tickers.json")
    by_ticker = {
        str(v.get("ticker", "")).upper(): str(int(v["cik_str"])).zfill(10)
        for v in payload.values()
        if v.get("ticker") and v.get("cik_str") is not None
    }
    missing = [s for s in SYMBOLS if s not in by_ticker]
    if missing:
        raise RuntimeError(f"SEC ticker map missing symbols={missing}")
    return {s: by_ticker[s] for s in SYMBOLS}


def eligible_units(companyfacts, namespace: str, concept: str):
    fact = companyfacts.get("facts", {}).get(namespace, {}).get(concept)
    if not fact:
        return []
    units = fact.get("units", {})
    # These six categories are monetary and expected in USD for this universe.
    rows = units.get("USD", [])
    out = []
    for row in rows:
        filed = str(row.get("filed") or "")
        form = str(row.get("form") or "")
        val = row.get("val")
        if not (START_FILED <= filed <= CUTOFF_FILED):
            continue
        if form not in FORMS:
            continue
        if not isinstance(val, (int, float)):
            continue
        out.append(row)
    return out


def summarize_candidate(rows):
    filings = sorted(
        {
            (str(r.get("filed")), str(r.get("accn") or ""))
            for r in rows
            if r.get("filed")
        }
    )
    filed_dates = sorted({d for d, _ in filings})
    years = sorted({d[:4] for d in filed_dates})
    period_ends = sorted({str(r.get("end")) for r in rows if r.get("end")})
    return {
        "rows": len(rows),
        "distinct_filings": len(filings),
        "distinct_filed_dates": len(filed_dates),
        "filed_years": len(years),
        "first_filed": filed_dates[0] if filed_dates else None,
        "last_filed": filed_dates[-1] if filed_dates else None,
        "distinct_period_ends": len(period_ends),
    }


def pick_category(companyfacts, candidates):
    scored = []
    for namespace, concept in candidates:
        rows = eligible_units(companyfacts, namespace, concept)
        summary = summarize_candidate(rows)
        scored.append(
            {
                "namespace": namespace,
                "concept": concept,
                **summary,
            }
        )
    scored.sort(
        key=lambda x: (x["distinct_filings"], x["filed_years"], x["rows"]),
        reverse=True,
    )
    best = scored[0]
    best["eligible"] = bool(
        best["distinct_filings"] >= MIN_DISTINCT_FILINGS
        and best["filed_years"] >= MIN_FILED_YEARS
    )
    return best, scored


def main():
    ciks = resolve_ciks()
    source = {}
    all_eligible = True
    for symbol in SYMBOLS:
        facts = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ciks[symbol]}.json")
        categories = {}
        for category, candidates in CANDIDATES.items():
            best, scored = pick_category(facts, candidates)
            categories[category] = {
                "selected": best,
                "candidates": scored,
            }
            all_eligible = all_eligible and bool(best["eligible"])
        source[symbol] = {
            "cik": ciks[symbol],
            "entity_name": facts.get("entityName"),
            "categories": categories,
        }
        time.sleep(0.15)

    status = "PASS" if all_eligible else "FAIL"
    out = {
        "schema": "public_compute.semiconductor_sec_fundamental_preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "development_universe": list(SYMBOLS),
        "source": "SEC Company Facts",
        "source_endpoint_family": "data.sec.gov/api/xbrl/companyfacts",
        "filing_time_authority": "SEC filed date; later-filed restatements are unavailable to earlier signal dates",
        "allowed_forms": sorted(FORMS),
        "filed_window": {"start": START_FILED, "cutoff": CUTOFF_FILED},
        "semantic_categories_frozen_before_model_outcomes": list(CANDIDATES),
        "eligibility_gate": {
            "minimum_distinct_filings_per_category_per_symbol": MIN_DISTINCT_FILINGS,
            "minimum_filed_years_per_category_per_symbol": MIN_FILED_YEARS,
            "all_six_categories_required": True,
        },
        "coverage": source,
        "status": status,
        "targets_computed": False,
        "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "next_boundary": (
            "PASS authorizes one development-only point-in-time fundamental information-value consumer "
            "against the exact PR31/PR34 path-head control; FAIL requires a source/taxonomy diagnosis, "
            "not silent symbol/category dropping"
        ),
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("SEMICONDUCTOR_SEC_FUNDAMENTAL_PREFLIGHT=" + json.dumps(out, sort_keys=True))
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
