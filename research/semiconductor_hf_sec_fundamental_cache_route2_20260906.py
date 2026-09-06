from __future__ import annotations

"""Route-2 SEC Company Facts transport that bypasses Hugging Face text search.

The scientific contract is identical to the canonical preflight. This route uses the
Dataset Viewer `/filter` endpoint only. It first tries deterministic SEC entity-folder
names; if those miss, it binary-searches `source_folder` while ordered by that column.
No target/model/holdout is loaded.
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

FOLDER_CANDIDATES = {
    "0000006951": (
        "CIK0000006951_APPLIED_MATERIALS_INC",
        "CIK0000006951_APPLIED_MATERIALS_INC_DE",
        "CIK0000006951_Applied_Materials_Inc",
        "CIK0000006951_Applied_Materials_Inc_DE",
    ),
    "0000820313": (
        "CIK0000820313_AMPHENOL_CORP",
        "CIK0000820313_AMPHENOL_CORP_DE",
        "CIK0000820313_Amphenol_Corp",
        "CIK0000820313_Amphenol_Corp_DE",
    ),
    "0000319201": (
        "CIK0000319201_KLA_CORP",
        "CIK0000319201_KLA_TENCOR_CORP",
        "CIK0000319201_KLA_Corp",
        "CIK0000319201_KLA_Tencor_Corp",
    ),
    "0000707549": (
        "CIK0000707549_LAM_RESEARCH_CORP",
        "CIK0000707549_LAM_RESEARCH_CORPORATION",
        "CIK0000707549_Lam_Research_Corp",
        "CIK0000707549_Lam_Research_Corporation",
    ),
    "0000097476": (
        "CIK0000097476_TEXAS_INSTRUMENTS_INC",
        "CIK0000097476_Texas_Instruments_Inc",
    ),
    "0001413447": (
        "CIK0001413447_NXP_SEMICONDUCTORS_NV",
        "CIK0001413447_NXP_SEMICONDUCTORS_N_V",
        "CIK0001413447_NXP_Semiconductors_NV",
        "CIK0001413447_NXP_Semiconductors_N_V",
    ),
    "0000006281": (
        "CIK0000006281_ANALOG_DEVICES_INC",
        "CIK0000006281_Analog_Devices_Inc",
    ),
}


def q(value: str) -> str:
    return value.replace("'", "''")


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


def filter_page(where: str, *, orderby=None, offset=0, length=1):
    params = {
        "dataset": DATASET,
        "config": "default",
        "split": "train",
        "where": where,
        "offset": offset,
        "length": length,
    }
    if orderby:
        params["orderby"] = orderby
    return get_json(API + "/filter", params)


def exact_folder_probe(folder: str) -> bool:
    payload = filter_page(f'"source_folder"=\'{q(folder)}\'', offset=0, length=1)
    rows = rows_from(payload)
    return bool(rows and str(rows[0].get("source_folder") or "") == folder)


def binary_discover_folder(cik: str) -> str:
    target = f"CIK{cik}_"
    where = '"label"=\'Assets\' AND "unit"=\'USD\''
    first = filter_page(where, orderby='"source_folder"', offset=0, length=1)
    total = int(first.get("num_rows_total") or 0)
    if total <= 0:
        raise RuntimeError("ordered Assets folder-discovery filter returned zero rows")

    lo, hi = 0, total - 1
    probes = 0
    while lo <= hi and probes < 40:
        probes += 1
        mid = (lo + hi) // 2
        payload = filter_page(where, orderby='"source_folder"', offset=mid, length=1)
        rows = rows_from(payload)
        if not rows:
            raise RuntimeError(f"binary folder discovery returned no row at offset={mid}/{total}")
        folder = str(rows[0].get("source_folder") or "")
        if folder.startswith(target):
            print(
                "SEMICONDUCTOR_HF_SEC_ROUTE2_FOLDER="
                + json.dumps({"cik": cik, "source_folder": folder, "method": "ordered_filter_binary_search", "probes": probes}, sort_keys=True)
            )
            return folder
        if folder < target:
            lo = mid + 1
        else:
            hi = mid - 1
    raise RuntimeError(f"CIK{cik}: source_folder not found in ordered Assets filter after {probes} probes")


def discover_folder(cik: str) -> str:
    errors = []
    for folder in FOLDER_CANDIDATES[cik]:
        try:
            if exact_folder_probe(folder):
                print(
                    "SEMICONDUCTOR_HF_SEC_ROUTE2_FOLDER="
                    + json.dumps({"cik": cik, "source_folder": folder, "method": "exact_filter"}, sort_keys=True)
                )
                return folder
        except Exception as exc:
            errors.append(f"{folder}: {exc}")
            break
    try:
        return binary_discover_folder(cik)
    except Exception as exc:
        raise RuntimeError(f"CIK{cik}: filter-only folder discovery failed; exact_probe_errors={errors}; binary_error={exc}") from exc


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
        payload = filter_page(where, orderby='"filed"', offset=offset, length=100)
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
    value = row.get("val_dec")
    if value is None:
        value = row.get("val_text")
    if value is None:
        value = row.get("val")
    if value is None:
        value = row.get("value")
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
        "value": value,
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
            candidates.sort(key=lambda x: (x["distinct_filings"], x["filed_years"], x["rows"]), reverse=True)
            selected = dict(candidates[0])
            selected["eligible"] = bool(
                selected["distinct_filings"] >= MIN_DISTINCT_FILINGS
                and selected["filed_years"] >= MIN_FILED_YEARS
            )
            all_eligible = all_eligible and selected["eligible"]
            categories[category] = {"selected": selected, "candidates": candidates}
            cache_categories[category] = {
                "label": selected["label"],
                "rows": [compact_row(r) for r in rows_by_label[selected["label"]]],
            }
        coverage[symbol] = {"cik": cik, "source_folder": folder, "categories": categories}
        cache_symbols[symbol] = {"cik": cik, "source_folder": folder, "categories": cache_categories}

    cache = {
        "schema": "public_compute.semiconductor_sec_fundamental_cache.v1",
        "source_dataset": DATASET,
        "source_dataset_revision": revision,
        "source_last_modified": info.get("lastModified"),
        "transport": "Hugging Face Dataset Viewer filter-only route; no text search and no bulk parquet download",
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
        "schema": "public_compute.semiconductor_hf_sec_fundamental_preflight.v2-route2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": DATASET,
        "source_dataset_revision": revision,
        "source_last_modified": info.get("lastModified"),
        "transport": "Hugging Face Dataset Viewer filter-only route; no text search and no bulk parquet download",
        "development_universe": list(SYMBOLS),
        "semantic_categories_frozen_before_model_outcomes": list(LABELS),
        "eligibility_gate": {
            "minimum_distinct_filings_per_category_per_symbol": MIN_DISTINCT_FILINGS,
            "minimum_filed_years_per_category_per_symbol": MIN_FILED_YEARS,
            "all_six_categories_required": True,
        },
        "coverage": coverage,
        "normalized_cache": {"path": str(CACHE), "sha256": cache_sha, "bytes": len(raw) + 1},
        "status": status,
        "targets_computed": False,
        "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "next_boundary": "PASS authorizes committing this exact normalized public cache and one development-only point-in-time information-value consumer against PR31/PR34 control",
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
            "schema": "public_compute.semiconductor_hf_sec_fundamental_preflight.v2-route2",
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
