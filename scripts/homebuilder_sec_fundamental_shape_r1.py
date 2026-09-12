from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from urllib.request import Request, urlopen

SYMBOLS = ("DHI", "LEN", "PHM", "NVR", "TOL", "MTH", "KBH", "LGIH", "DFH", "LEGH")
UA = "XoticHaze market-research source-shape contact@example.com"
CORE = (
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "NetIncomeLoss",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "CashAndCashEquivalentsAtCarryingValue",
    "LongTermDebtCurrent",
    "LongTermDebtNoncurrent",
    "LongTermDebtAndFinanceLeaseObligationsCurrent",
    "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    "InventoryNet",
)
FAMILIES = {
    "inventory": ("inventory",),
    "land": ("land", "lot"),
    "revenue": ("revenue", "sales"),
    "debt": ("debt", "borrow"),
    "equity": ("equity",),
}


def get(url: str) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:  # noqa: S310 fixed SEC HTTPS host
        return json.loads(response.read().decode("utf-8"))


def observations(concept: dict) -> list[dict]:
    rows = []
    for unit, values in concept.get("units", {}).items():
        for value in values:
            if value.get("form") not in ("10-K", "10-Q"):
                continue
            filed = value.get("filed")
            end = value.get("end")
            if not filed or not end or filed < "2019-01-01":
                continue
            rows.append({"unit": unit, "filed": filed, "end": end, "form": value.get("form"), "val": value.get("val")})
    return rows


def main() -> None:
    ticker_map = get("https://www.sec.gov/files/company_tickers.json")
    cik_by_ticker = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in ticker_map.values()}
    results = {}
    family_coverage: dict[str, dict[str, list[str]]] = defaultdict(dict)

    for symbol in SYMBOLS:
        cik = cik_by_ticker.get(symbol)
        if not cik:
            results[symbol] = {"status": "missing_cik"}
            continue
        payload = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        usgaap = payload.get("facts", {}).get("us-gaap", {})
        core = {}
        for name in CORE:
            rows = observations(usgaap.get(name, {}))
            core[name] = {
                "observations_since_2019": len(rows),
                "first_filed": min((row["filed"] for row in rows), default=None),
                "last_filed": max((row["filed"] for row in rows), default=None),
                "units": sorted({row["unit"] for row in rows}),
            }

        families = {}
        for family, needles in FAMILIES.items():
            candidates = []
            for name, concept in usgaap.items():
                lower = name.lower()
                if not any(needle in lower for needle in needles):
                    continue
                rows = observations(concept)
                if len(rows) < 8:
                    continue
                candidates.append({
                    "concept": name,
                    "observations_since_2019": len(rows),
                    "first_filed": min(row["filed"] for row in rows),
                    "last_filed": max(row["filed"] for row in rows),
                    "units": sorted({row["unit"] for row in rows}),
                })
            candidates.sort(key=lambda row: (-row["observations_since_2019"], row["concept"]))
            families[family] = candidates[:12]
            family_coverage[family][symbol] = [row["concept"] for row in candidates[:12]]

        results[symbol] = {"status": "ok", "cik": cik, "core": core, "families": families}
        time.sleep(0.12)

    shared = {}
    for family in FAMILIES:
        sets = [set(family_coverage[family].get(symbol, [])) for symbol in SYMBOLS if results.get(symbol, {}).get("status") == "ok"]
        shared[family] = sorted(set.intersection(*sets)) if sets else []

    payload = {
        "schema": "public_research.homebuilder_sec_fundamental_shape_r1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": list(SYMBOLS),
        "claim": "Map chronology-safe SEC companyfacts coverage before freezing a materially new Homebuilder fundamental/valuation alpha child; this probe contains no return outcomes.",
        "results": results,
        "shared_family_concepts": shared,
        "boundaries": {"source_probe_only": True, "economic_results": False, "live_trading_change": False},
    }
    print("HOMEBUILDER_SEC_FUNDAMENTAL_SHAPE=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
