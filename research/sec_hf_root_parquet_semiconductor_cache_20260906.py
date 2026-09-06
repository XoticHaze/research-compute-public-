from __future__ import annotations

"""Materialize the frozen semiconductor SEC fundamental cache from Company Facts Parquet.

The DenyTran mirror is a consolidated redistribution of SEC Company Facts. This consumer
pins the mirror revision, range-queries US-GAAP + IFRS Parquet directly, preserves SEC
`filed`/accession/period fields, and computes no target/model.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import duckdb

DATASET = "DenyTranDFW/edgar_xbrl_companyfacts"
META_URL = f"https://huggingface.co/api/datasets/{DATASET}"
OUT = Path("sec_hf_root_parquet_semiconductor_preflight_20260906.json")
CACHE = Path("sec_hf_root_parquet_semiconductor_cache_20260906.json")
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
LABELS = {
    "revenue": (
        "Revenue from Contract with Customer, Excluding Assessed Tax",
        "Sales Revenue, Net",
        "Revenues",
        "Revenue",
    ),
    "gross_profit": ("Gross Profit", "Gross profit"),
    "operating_income": (
        "Operating Income (Loss)",
        "Profit (Loss) from Operating Activities",
        "Profit (loss) from operating activities",
    ),
    "assets": ("Assets",),
    "inventory": (
        "Inventory, Net",
        "Inventory, Net of Allowances, Customer Advances and Progress Billings",
        "Inventories",
    ),
    "cash": (
        "Cash and Cash Equivalents, at Carrying Value",
        "Cash, Cash Equivalents, Restricted Cash and Restricted Cash Equivalents",
        "Cash and Cash Equivalents",
        "Cash and cash equivalents",
    ),
}


def metadata():
    req = Request(META_URL, headers={"User-Agent": "research-compute-public/1.0"})
    with urlopen(req, timeout=30) as response:
        obj = json.loads(response.read().decode("utf-8"))
    revision = obj.get("sha")
    if not revision:
        raise RuntimeError("Hugging Face dataset metadata did not expose revision SHA")
    return revision, obj.get("lastModified")


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def summarize(rows):
    filings = sorted({(str(r["filed"]), str(r["accn"])) for r in rows if r.get("filed")})
    dates = sorted({d for d, _ in filings})
    years = sorted({d[:4] for d in dates})
    return {
        "rows": len(rows),
        "distinct_filings": len(filings),
        "filed_years": len(years),
        "first_filed": dates[0] if dates else None,
        "last_filed": dates[-1] if dates else None,
    }


def main():
    revision, last_modified = metadata()
    base = f"https://huggingface.co/datasets/{DATASET}/resolve/{revision}"
    urls = [f"{base}/Facts_UsGaap.parquet", f"{base}/Facts_IfrsFull.parquet"]

    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    all_labels = sorted({label for labels in LABELS.values() for label in labels})
    folder_terms = " OR ".join("source_folder LIKE ?" for _ in SYMBOL_CIKS)
    label_terms = ",".join("?" for _ in all_labels)
    form_terms = ",".join("?" for _ in FORMS)
    sql = f"""
        SELECT end, accn, fy, fp, form, filed, item, label, description,
               unit_type, val_text, frame, start, val_dec, source_folder, filename
        FROM read_parquet(?, union_by_name=true, filename=true)
        WHERE ({folder_terms})
          AND label IN ({label_terms})
          AND UPPER(COALESCE(unit_type, '')) = 'USD'
          AND filed >= ? AND filed <= ?
          AND form IN ({form_terms})
        ORDER BY source_folder, filed, accn, label, end NULLS FIRST, start NULLS FIRST
    """
    params = [urls, *[f"CIK{cik}_%" for cik in SYMBOL_CIKS.values()], *all_labels, START_FILED, CUTOFF_FILED, *FORMS]
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = []
    for tup in cur.fetchall():
        rec = {}
        for k, v in zip(cols, tup):
            rec[k] = None if v is None else str(v)
        rows.append(rec)
    if not rows:
        raise RuntimeError("targeted Company Facts Parquet query returned zero rows")

    by_symbol = {}
    for symbol, cik in SYMBOL_CIKS.items():
        prefix = f"CIK{cik}_"
        by_symbol[symbol] = [r for r in rows if (r.get("source_folder") or "").startswith(prefix)]

    coverage = {}
    cache_symbols = {}
    all_eligible = True
    for symbol, cik in SYMBOL_CIKS.items():
        categories = {}
        cache_categories = {}
        symbol_rows = by_symbol[symbol]
        folders = sorted({r["source_folder"] for r in symbol_rows})
        for category, labels in LABELS.items():
            candidates = []
            rows_by_label = {}
            for label in labels:
                part = [r for r in symbol_rows if r.get("label") == label]
                rows_by_label[label] = part
                candidates.append({"label": label, **summarize(part)})
            candidates.sort(key=lambda x: (x["distinct_filings"], x["filed_years"], x["rows"]), reverse=True)
            selected = dict(candidates[0])
            selected["eligible"] = bool(
                selected["distinct_filings"] >= MIN_DISTINCT_FILINGS
                and selected["filed_years"] >= MIN_FILED_YEARS
            )
            all_eligible = all_eligible and selected["eligible"]
            categories[category] = {"selected": selected, "candidates": candidates}
            cache_categories[category] = {"label": selected["label"], "rows": rows_by_label[selected["label"]]}
        coverage[symbol] = {"cik": cik, "source_folders": folders, "categories": categories}
        cache_symbols[symbol] = {"cik": cik, "source_folders": folders, "categories": cache_categories}

    cache = {
        "schema": "public_compute.semiconductor_sec_fundamental_cache.v1",
        "source_dataset": DATASET,
        "source_dataset_revision": revision,
        "source_last_modified": last_modified,
        "source_files": urls,
        "transport": "DuckDB httpfs direct range query of consolidated SEC Company Facts Parquet",
        "development_universe": list(SYMBOL_CIKS),
        "filing_time_authority": "mirrored SEC filed field; consumers must enforce filed <= signal date",
        "filed_window": {"start": START_FILED, "cutoff": CUTOFF_FILED},
        "semantic_categories": list(LABELS),
        "symbols": cache_symbols,
    }
    raw = canonical_bytes(cache)
    sha = hashlib.sha256(raw).hexdigest()
    CACHE.write_bytes(raw + b"\n")
    status = "PASS" if all_eligible else "FAIL"
    receipt = {
        "schema": "public_compute.sec_hf_root_parquet_semiconductor_preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": DATASET,
        "source_dataset_revision": revision,
        "source_last_modified": last_modified,
        "source_files": urls,
        "transport": cache["transport"],
        "development_universe": list(SYMBOL_CIKS),
        "semantic_categories_frozen_before_model_outcomes": list(LABELS),
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
            "PASS authorizes the first development-only filing-safe information-value consumer against the frozen path-head control; "
            "FAIL requires exact taxonomy/coverage diagnosis without model execution"
        ),
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("SEC_HF_ROOT_PARQUET_SEMICONDUCTOR_PREFLIGHT=" + json.dumps(receipt, sort_keys=True))
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        failure = {
            "schema": "public_compute.sec_hf_root_parquet_semiconductor_preflight.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_dataset": DATASET,
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
        OUT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        print("SEC_HF_ROOT_PARQUET_SEMICONDUCTOR_PREFLIGHT=" + json.dumps(failure, sort_keys=True))
        raise
