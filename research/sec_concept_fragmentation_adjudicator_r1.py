from __future__ import annotations

import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

WORKLOAD_ID = "SEC_CONCEPT_FRAGMENTATION_ADJUDICATOR_R1"
TICKERS = ["AAPL", "MSFT", "NVDA", "AMAT", "CAT", "JPM", "XOM", "JNJ", "PG", "HD"]
UA = "XoticHaze market-research source-validation contact@example.com"
CONCEPTS = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "InterestAndDividendIncomeOperating",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "assets": ["Assets"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "PartnersCapital",
    ],
}
MINIMUMS = {"revenue": 20, "net_income": 20, "assets": 20, "equity": 12}


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def observations(us_gaap: dict, aliases: list[str]) -> tuple[list[dict], dict[str, int]]:
    unique = {}
    contribution = defaultdict(int)
    for concept in aliases:
        units = us_gaap.get(concept, {}).get("units", {})
        for unit, vals in units.items():
            for v in vals:
                if v.get("form") not in ("10-K", "10-Q") or not v.get("filed") or not v.get("end"):
                    continue
                # Keep chronology and accession identity explicit. Values themselves are not
                # used for alpha here; this is source/representation adjudication only.
                key = (v.get("filed"), v.get("end"), v.get("form"), v.get("accn"), unit)
                if key not in unique:
                    unique[key] = {
                        "filed": v.get("filed"),
                        "end": v.get("end"),
                        "form": v.get("form"),
                        "accn": v.get("accn"),
                        "unit": unit,
                        "concept": concept,
                    }
                    contribution[concept] += 1
    rows = sorted(unique.values(), key=lambda x: (x["filed"], x["end"], x.get("accn") or ""))
    return rows, dict(contribution)


def main() -> None:
    mapping = get("https://www.sec.gov/files/company_tickers.json")
    cik = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in mapping.values()}
    rows = {}
    for ticker in TICKERS:
        c = cik.get(ticker)
        rec = {"cik": c, "families": {}, "pass": False, "failed_families": []}
        if not c:
            rec["failed_families"] = list(CONCEPTS)
            rows[ticker] = rec
            continue
        data = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c}.json")
        us_gaap = data.get("facts", {}).get("us-gaap", {})
        for family, aliases in CONCEPTS.items():
            obs, contribution = observations(us_gaap, aliases)
            rec["families"][family] = {
                "observations": len(obs),
                "minimum": MINIMUMS[family],
                "aliases_with_contribution": contribution,
                "first_filed": obs[0]["filed"] if obs else None,
                "last_filed": obs[-1]["filed"] if obs else None,
                "distinct_period_ends": len({x["end"] for x in obs}),
                "distinct_accessions": len({x["accn"] for x in obs if x.get("accn")}),
            }
            if len(obs) < MINIMUMS[family]:
                rec["failed_families"].append(family)
        rec["pass"] = not rec["failed_families"]
        rows[ticker] = rec
        time.sleep(0.12)

    passing = sum(v["pass"] for v in rows.values())
    multi_alias_evidence = {
        ticker: {
            family: info["aliases_with_contribution"]
            for family, info in rec["families"].items()
            if len(info["aliases_with_contribution"]) > 1
        }
        for ticker, rec in rows.items()
    }
    decision = (
        "SEC_CONCEPT_FRAGMENTATION_EXPLAINS_SOURCE_GAP__SOURCE_ADMISSIBLE"
        if passing >= 8
        else "SEC_SOURCE_GAP_PERSISTS_AFTER_CONCEPT_ADJUDICATION"
    )
    out = {
        "schema": "research.sec_concept_fragmentation_adjudicator_r1",
        "workload_id": WORKLOAD_ID,
        "parent_context": "P287",
        "claim": "Adjudicate whether P287's 7/10 SEC companyfacts admission failure was caused by XBRL concept fragmentation rather than genuinely insufficient filed-at point-in-time accounting coverage, without lowering the fixed sample or coverage thresholds.",
        "fixed_sample": TICKERS,
        "concept_families": CONCEPTS,
        "minimum_observations": MINIMUMS,
        "ticker_results": rows,
        "multi_alias_contribution": multi_alias_evidence,
        "passing_tickers": passing,
        "ticker_count": len(TICKERS),
        "decision_rule": "Admit the SEC source representation only if at least 8/10 unchanged fixed-sample tickers pass the unchanged P287 coverage thresholds after deterministic concept-family unioning by filed date, period end, form, accession and unit. Do not lower thresholds, change tickers, or infer alpha.",
        "decision": decision,
        "limitations": [
            "This tests source representation only and cannot establish an investable factor premium.",
            "Companyfacts can include amendments/restatements; any economic model must select facts strictly by filed date and freeze an accession policy.",
            "Current ticker-to-CIK mapping is not historical universe membership authority.",
            "Concept-family unioning does not make economically different concepts interchangeable in a later model; model construction must define deterministic field precedence and comparability rules.",
        ],
        "boundaries": {
            "scientific_authority": True,
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    Path("research/artifacts").mkdir(parents=True, exist_ok=True)
    Path("research/artifacts/sec_concept_fragmentation_adjudicator_r1.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, allow_nan=False)
    )
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
