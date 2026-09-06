from __future__ import annotations

"""Materialize the frozen semiconductor SEC fundamental cache from the remote SEC FSD database.

This is a source-only point-in-time consumer of the transport proven by
sec_datapond_transport_probe_20260906.py. It preserves SEC filing dates and accession
identities, freezes six semantic categories before model outcomes, and computes no target/model.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

REMOTE_DB = "https://huggingface.co/datasets/erlenbusch/sec-edgar/resolve/main/sec_edgar.duckdb"
OUT = Path("sec_datapond_semiconductor_preflight_20260906.json")
CACHE = Path("sec_datapond_semiconductor_cache_20260906.json")
START_FILED = "2014-01-01"
CUTOFF_FILED = "2026-09-03"
FORMS = ("10-Q", "10-K", "20-F", "40-F")
MIN_DISTINCT_FILINGS = 16
MIN_FILED_YEARS = 8
SYMBOL_CIKS = {
    "AMAT": "0000006951",
    "APH": "0000820313",
    "KLAC": "0000319201",
    "LRCX": "0000707549",
    "TXN": "0000097476",
    "NXPI": "0001413447",
    "ADI": "0000006281",
}

# Standard XBRL element names corresponding to the already-frozen semantic categories.
TAGS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
        "Revenue",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": (
        "OperatingIncomeLoss",
        "ProfitLossFromOperatingActivities",
    ),
    "assets": ("Assets",),
    "inventory": (
        "InventoryNet",
        "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings",
        "Inventories",
    ),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndCashEquivalents",
    ),
}


def connect_remote():
    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"ATTACH '{REMOTE_DB}' AS sec_edgar (READ_ONLY)")
    con.execute("USE sec_edgar")
    return con


def placeholders(n: int) -> str:
    return ",".join("?" for _ in range(n))


def candidate_rows(con, cik: str, tag: str):
    sql = f"""
        SELECT
            s.adsh,
            LPAD(CAST(s.cik AS VARCHAR), 10, '0') AS cik,
            s.filed,
            s.form,
            s.fy,
            s.fp,
            n.tag,
            n.version,
            n.ddate,
            n.qtrs,
            n.uom,
            n.coreg,
            n.value
        FROM submissions AS s
        JOIN numbers AS n USING (adsh)
        WHERE LPAD(CAST(s.cik AS VARCHAR), 10, '0') = ?
          AND s.form IN ({placeholders(len(FORMS))})
          AND s.filed >= ?
          AND s.filed <= ?
          AND n.tag = ?
          AND UPPER(COALESCE(n.uom, '')) = 'USD'
        ORDER BY s.filed, s.adsh, n.ddate, n.qtrs, n.coreg NULLS FIRST
    """
    return con.execute(sql, [cik, *FORMS, START_FILED, CUTOFF_FILED, tag]).fetchall()


def summarize(rows):
    filings = sorted({(str(r[2]), str(r[0])) for r in rows if r[2] is not None})
    dates = sorted({x[0] for x in filings})
    years = sorted({d[:4] for d in dates})
    return {
        "rows": len(rows),
        "distinct_filings": len(filings),
        "filed_years": len(years),
        "first_filed": dates[0] if dates else None,
        "last_filed": dates[-1] if dates else None,
    }


def compact(rows):
    names = ("adsh", "cik", "filed", "form", "fy", "fp", "tag", "version", "ddate", "qtrs", "uom", "coreg", "value")
    out = []
    seen = set()
    for row in rows:
        rec = {k: (None if v is None else str(v)) for k, v in zip(names, row)}
        key = tuple(rec[k] for k in names)
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main():
    con = connect_remote()
    schemas = {}
    for table in ("submissions", "numbers", "tags"):
        schemas[table] = [str(r[0]) for r in con.execute(f"DESCRIBE {table}").fetchall()]
    for col in ("adsh", "cik", "filed", "form", "fy", "fp"):
        if col not in schemas["submissions"]:
            raise RuntimeError(f"submissions missing required column {col}: {schemas['submissions']}")
    for col in ("adsh", "tag", "version", "ddate", "qtrs", "uom", "coreg", "value"):
        if col not in schemas["numbers"]:
            raise RuntimeError(f"numbers missing required column {col}: {schemas['numbers']}")

    coverage = {}
    cache_symbols = {}
    all_eligible = True
    for symbol, cik in SYMBOL_CIKS.items():
        category_receipts = {}
        cache_categories = {}
        for category, tags in TAGS.items():
            candidates = []
            rows_by_tag = {}
            for tag in tags:
                rows = candidate_rows(con, cik, tag)
                rows_by_tag[tag] = rows
                candidates.append({"tag": tag, **summarize(rows)})
            candidates.sort(
                key=lambda x: (x["distinct_filings"], x["filed_years"], x["rows"]),
                reverse=True,
            )
            selected = dict(candidates[0])
            selected["eligible"] = bool(
                selected["distinct_filings"] >= MIN_DISTINCT_FILINGS
                and selected["filed_years"] >= MIN_FILED_YEARS
            )
            all_eligible = all_eligible and selected["eligible"]
            category_receipts[category] = {"selected": selected, "candidates": candidates}
            cache_categories[category] = {
                "tag": selected["tag"],
                "rows": compact(rows_by_tag[selected["tag"]]),
            }
        coverage[symbol] = {"cik": cik, "categories": category_receipts}
        cache_symbols[symbol] = {"cik": cik, "categories": cache_categories}

    cache = {
        "schema": "public_compute.semiconductor_sec_fundamental_cache.v1",
        "source": "erlenbusch/sec-edgar public-domain DuckDB derived from SEC Financial Statement Data Sets",
        "source_database": REMOTE_DB,
        "development_universe": list(SYMBOL_CIKS),
        "filing_time_authority": "SEC Financial Statement Data Sets submissions.filed; consumers must enforce filed <= signal date",
        "filed_window": {"start": START_FILED, "cutoff": CUTOFF_FILED},
        "semantic_categories": list(TAGS),
        "symbols": cache_symbols,
    }
    raw = canonical_bytes(cache)
    sha = hashlib.sha256(raw).hexdigest()
    CACHE.write_bytes(raw + b"\n")

    status = "PASS" if all_eligible else "FAIL"
    receipt = {
        "schema": "public_compute.sec_datapond_semiconductor_preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": cache["source"],
        "source_database": REMOTE_DB,
        "transport": "direct Hugging Face remote DuckDB attach",
        "development_universe": list(SYMBOL_CIKS),
        "semantic_categories_frozen_before_model_outcomes": list(TAGS),
        "eligibility_gate": {
            "minimum_distinct_filings_per_category_per_symbol": MIN_DISTINCT_FILINGS,
            "minimum_filed_years_per_category_per_symbol": MIN_FILED_YEARS,
            "all_six_categories_required": True,
        },
        "coverage": coverage,
        "normalized_cache": {"path": str(CACHE), "sha256": sha, "bytes": len(raw) + 1},
        "status": status,
        "targets_computed": False,
        "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
        "next_boundary": (
            "PASS authorizes the first development-only point-in-time information-value consumer against the frozen path-head control; "
            "FAIL requires taxonomy/coverage diagnosis without model execution"
        ),
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SEC_DATAPOND_SEMICONDUCTOR_PREFLIGHT=" + json.dumps(receipt, sort_keys=True))
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        failure = {
            "schema": "public_compute.sec_datapond_semiconductor_preflight.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "TRANSPORT_OR_SCHEMA_FAILURE",
            "error": str(exc),
            "targets_computed": False,
            "model_executed": False,
            "external_semiconductor_holdouts_loaded": False,
            "research_only": True,
            "promotion_authority": False,
            "runtime_mutation": False,
            "broker_action": False,
            "live_trading_change": False,
        }
        OUT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("SEC_DATAPOND_SEMICONDUCTOR_PREFLIGHT=" + json.dumps(failure, sort_keys=True))
        raise
