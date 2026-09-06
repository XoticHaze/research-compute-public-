from __future__ import annotations

"""Build a compact, reusable point-in-time fundamental cache from a public SEC mirror.

This is source-only. No price/path target and no model is computed. The mirror preserves
SEC filing dates/accessions, and the cache retains only six predeclared semantic categories
for the seven frozen development symbols. Later consumers must join by filed <= signal date.
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATASET = "DenyTranDFW/edgar_xbrl_companyfacts"
API = "https://datasets-server.huggingface.co"
HF_API = "https://huggingface.co/api/datasets/DenyTranDFW/edgar_xbrl_companyfacts"
OUT = Path("semiconductor_hf_sec_fundamental_preflight_20260906.json")
CACHE = Path("semiconductor_hf_sec_fundamental_cache_20260906.json")
SYMBOLS = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")
CIKS = {
    "AMAT": "0000006951",
    "APH": "0000820313",
    "KLAC": "0000319201",
    "LRCX": "0000707549",
    "TXN": "0000097476",
    "NXPI": "0001413447",
    "ADI": "0000006281",
}
START_FILED = "2014-01-01"
CUTOFF_FILED = "2026-09-03"
FORMS = {"10-Q", "10-K", "20-F", "40-F"}
MIN_DISTINCT_FILINGS = 16
MIN_FILED_YEARS = 8
UA = "research-compute-public/1.0"

# Standard XBRL labels corresponding to the frozen semantic categories.
LABELS = {
    "revenue": (
        "Revenue from Contract with Customer, Excluding Assessed Tax",
        "Sales Revenue, Net",
        "Revenues",
        "Revenue",
    ),
    "gross_profit": ("Gross Profit",),
    "operating_income": (
        "Operating Income (Loss)",
        "Profit (Loss) from Operating Activities",
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
    ),
}


def get_json(url: str, params=None):
    if params:
        url = url + "?" + urlencode(params)
    last = None
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urlopen(req, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET failed after 3 attempts: {url}: {last}")


def rows_from(payload):
    out = []
    for item in payload.get("rows", []):
        row = item.get("row", item)
        if isinstance(row, dict):
            out.append(row)
    return out


def discover_folder(cik: str):
    payload = get_json(
        API + "/search",
        {
            "dataset": DATASET,
            "config": "default",
            "split": "train",
            "query": f"CIK{cik}",
            "offset": 0,
            "length": 100,
        },
    )
    prefix = f"CIK{cik}_"
    folders = sorted(
        {
            str(r.get("source_folder"))
            for r in rows_from(payload)
            if str(r.get("source_folder") or "").startswith(prefix)
        }
    )
    if len(folders) != 1:
        raise RuntimeError(f"CIK{cik}: expected one source folder, got {folders}")
    return folders[0]


def q(value: str):
    return value.replace("'", "''")


def filter_label(folder: str, label: str):
    form_expr = " OR ".join(f'"form"=\'{q(f)}\'' for f in sorted(FORMS))
    where = (
        f'"source_folder"=\'{q(folder)}\' AND '
        f'"label"=\'{q(label)}\' AND '
        f'"unit"=\'USD\' AND '
        f'"filed">=\'{START_FILED}\' AND "filed"<=\'{CUTOFF_FILED}\' AND '
        f'({form_expr})'
    )
    out = []
    offset = 0
    while True:
        payload = get_json(
            API + "/filter",
            {
                "dataset": DATASET,
                "config": "default",
                "split": "train",
                "where": where,
                "orderby": '"filed"',
                "offset": offset,
                "length": 100,
            },
        )
        batch = rows_from(payload)
        out.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
        if offset > 5000:
            raise RuntimeError(f"unexpectedly large filtered result: {folder} {label}")
    return out


def summarize(rows):
    filings = sorted({(str(r.get("filed")), str(r.get("accn") or "")) for r in rows if r.get("filed")})
    dates = sorted({x[0] for x in filings})
    years = sorted({d[:4] for d in dates})
    return {
        "rows": len(rows),
        "distinct_filings": len(filings),
        "filed_years": len(years),
        "first_filed": dates[0] if dates else None,
        "last_filed": dates[-1] if dates else None,
    }


def compact_row(row):
    return {
        "end": row.get("end"),
        "accn": row.get("accn"),
        "fy": row.get("fy"),
        "fp": row.get("fp"),
        "form": row.get("form"),
        "filed": row.get("filed"),
        "frame": row.get("frame"),
        "label": row.get("label"),
        "unit": row.get("unit"),
        "val_text": row.get("val_text"),
        "val_dec": row.get("val_dec"),
    }


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main():
    info = get_json(HF_API)
    revision = info.get("sha")
    if not revision:
        raise RuntimeError("Hugging Face dataset metadata did not expose a revision SHA")

    coverage = {}
    cache_symbols = {}
    all_eligible = True
    for symbol in SYMBOLS:
        cik = CIKS[symbol]
        folder = discover_folder(cik)
        categories = {}
        cache_categories = {}
        for category, labels in LABELS.items():
            candidates = []
            rows_by_label = {}
            for label in labels:
                rows = filter_label(folder, label)
                rows_by_label[label] = rows
                candidates.append({"label": label, **summarize(rows)})
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
            categories[category] = {"selected": selected, "candidates": candidates}
            chosen = rows_by_label[selected["label"]]
            cache_categories[category] = {
                "label": selected["label"],
                "rows": [compact_row(r) for r in chosen],
            }
        coverage[symbol] = {"cik": cik, "source_folder": folder, "categories": categories}
        cache_symbols[symbol] = {"cik": cik, "source_folder": folder, "categories": cache_categories}

    cache = {
        "schema": "public_compute.semiconductor_sec_fundamental_cache.v1",
        "source_dataset": DATASET,
        "source_dataset_revision": revision,
        "source_last_modified": info.get("lastModified"),
        "development_universe": list(SYMBOLS),
        "filing_time_authority": "mirrored SEC filed field; consumers must enforce filed <= signal date",
        "filed_window": {"start": START_FILED, "cutoff": CUTOFF_FILED},
        "semantic_categories": list(LABELS),
        "symbols": cache_symbols,
    }
    raw = canonical_bytes(cache)
    cache_sha = hashlib.sha256(raw).hexdigest()
    CACHE.write_bytes(raw + b"\n")

    status = "PASS" if all_eligible else "FAIL"
    receipt = {
        "schema": "public_compute.semiconductor_hf_sec_fundamental_preflight.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": DATASET,
        "source_dataset_revision": revision,
        "source_last_modified": info.get("lastModified"),
        "development_universe": list(SYMBOLS),
        "semantic_categories_frozen_before_model_outcomes": list(LABELS),
        "eligibility_gate": {
            "minimum_distinct_filings_per_category_per_symbol": MIN_DISTINCT_FILINGS,
            "minimum_filed_years_per_category_per_symbol": MIN_FILED_YEARS,
            "all_six_categories_required": True,
        },
        "coverage": coverage,
        "normalized_cache": {
            "path": str(CACHE),
            "sha256": cache_sha,
            "bytes": len(raw) + 1,
        },
        "status": status,
        "targets_computed": False,
        "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "next_boundary": (
            "PASS authorizes committing this exact normalized public cache and one development-only "
            "point-in-time information-value consumer against the PR31/PR34 path-head control"
        ),
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("SEMICONDUCTOR_HF_SEC_FUNDAMENTAL_PREFLIGHT=" + json.dumps(receipt, sort_keys=True))
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        failure = {
            "schema": "public_compute.semiconductor_hf_sec_fundamental_preflight.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_dataset": DATASET,
            "development_universe": list(SYMBOLS),
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
        print("SEMICONDUCTOR_HF_SEC_FUNDAMENTAL_PREFLIGHT=" + json.dumps(failure, sort_keys=True))
        raise
