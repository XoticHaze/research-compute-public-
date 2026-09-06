from __future__ import annotations

"""Build a compact reusable point-in-time fundamental cache from a public SEC mirror.

Source-only: no price/path target and no model. The Hugging Face repository metadata
resolves each frozen CIK folder; only that company's US-GAAP/IFRS parquet is downloaded.
SEC filing dates/accessions are preserved and later consumers must enforce filed <= signal.
"""

import hashlib
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

DATASET = "DenyTranDFW/edgar_xbrl_companyfacts"
HF_API = "https://huggingface.co/api/datasets/DenyTranDFW/edgar_xbrl_companyfacts"
HF_RESOLVE = "https://huggingface.co/datasets/DenyTranDFW/edgar_xbrl_companyfacts/resolve"
OUT = Path("semiconductor_hf_sec_fundamental_preflight_20260906.json")
CACHE = Path("semiconductor_hf_sec_fundamental_cache_20260906.json")
SYMBOLS = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")
CIKS = {
    "AMAT": "0000006951", "APH": "0000820313", "KLAC": "0000319201",
    "LRCX": "0000707549", "TXN": "0000097476", "NXPI": "0001413447",
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
        "Sales Revenue, Net", "Revenues", "Revenue",
    ),
    "gross_profit": ("Gross Profit",),
    "operating_income": ("Operating Income (Loss)", "Profit (Loss) from Operating Activities"),
    "assets": ("Assets",),
    "inventory": ("Inventory, Net", "Inventory, Net of Allowances, Customer Advances and Progress Billings", "Inventories"),
    "cash": ("Cash and Cash Equivalents, at Carrying Value", "Cash, Cash Equivalents, Restricted Cash and Restricted Cash Equivalents", "Cash and Cash Equivalents"),
}


def request_bytes(url: str):
    last = None
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "application/octet-stream,application/json"})
            with urlopen(req, timeout=60) as response:
                return response.read()
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
    raise RuntimeError(f"GET failed after 3 attempts: {url}: {last}")


def get_json(url: str):
    return json.loads(request_bytes(url).decode("utf-8"))


def repo_paths(info):
    paths = []
    for item in info.get("siblings") or []:
        p = item.get("rfilename") or item.get("path")
        if p:
            paths.append(str(p))
    if not paths:
        raise RuntimeError("Hugging Face dataset metadata exposed no repository file paths")
    return paths


def discover_folder(paths, cik: str):
    prefix = f"CIK{cik}_"
    folders = sorted({p.split("/", 1)[0] for p in paths if p.startswith(prefix) and "/" in p})
    if len(folders) != 1:
        raise RuntimeError(f"CIK{cik}: expected one repository folder, got {folders}")
    return folders[0]


def load_fact_frames(paths, revision: str, folder: str):
    available = set(paths)
    frames = []
    loaded = []
    for filename in ("Facts_UsGaap.parquet", "Facts_IfrsFull.parquet"):
        rel = f"{folder}/{filename}"
        if rel not in available:
            continue
        url = f"{HF_RESOLVE}/{quote(revision, safe='')}/{quote(rel, safe='/')}?download=true"
        raw = request_bytes(url)
        with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
            tmp.write(raw); tmp.flush()
            frame = pd.read_parquet(tmp.name)
        frame["_source_file"] = filename
        frames.append(frame)
        loaded.append({"path": rel, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    if not frames:
        raise RuntimeError(f"{folder}: neither US-GAAP nor IFRS fact parquet exists")
    return pd.concat(frames, ignore_index=True), loaded


def normalize(df):
    required = {"label", "unit", "filed", "form"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"fact parquet missing required columns={missing}; columns={list(df.columns)}")
    out = df.copy()
    for c in ("label", "unit", "filed", "form", "accn", "end", "fp", "frame"):
        if c not in out.columns:
            out[c] = None
    if "fy" not in out.columns:
        out["fy"] = None
    value_cols = [c for c in ("val_dec", "val_text", "val", "value") if c in out.columns]
    if not value_cols:
        raise RuntimeError(f"fact parquet has no supported value column; columns={list(out.columns)}")
    out["_value"] = None
    for c in value_cols:
        out["_value"] = out["_value"].where(out["_value"].notna(), out[c])
    out = out[
        out["filed"].astype(str).between(START_FILED, CUTOFF_FILED)
        & out["form"].astype(str).isin(FORMS)
        & (out["unit"].astype(str) == "USD")
    ].copy()
    return out


def rows_for_label(df, label):
    return df[df["label"].astype(str) == label].copy()


def summarize(df):
    filings = sorted({(str(r.filed), str(r.accn)) for r in df.itertuples() if pd.notna(r.filed)})
    dates = sorted({x[0] for x in filings})
    years = sorted({d[:4] for d in dates})
    return {
        "rows": int(len(df)), "distinct_filings": len(filings), "filed_years": len(years),
        "first_filed": dates[0] if dates else None, "last_filed": dates[-1] if dates else None,
    }


def json_value(v):
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


def compact_rows(df):
    rows = []
    for r in df.sort_values(["filed", "end", "accn"], na_position="first").itertuples():
        rows.append({
            "end": json_value(r.end), "accn": json_value(r.accn), "fy": json_value(r.fy),
            "fp": json_value(r.fp), "form": json_value(r.form), "filed": json_value(r.filed),
            "frame": json_value(r.frame), "label": json_value(r.label), "unit": json_value(r.unit),
            "value": json_value(r._value),
        })
    return rows


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main():
    info = get_json(HF_API)
    revision = info.get("sha")
    if not revision:
        raise RuntimeError("Hugging Face metadata did not expose a revision SHA")
    paths = repo_paths(info)
    coverage, cache_symbols = {}, {}
    all_eligible = True

    for symbol in SYMBOLS:
        cik = CIKS[symbol]
        folder = discover_folder(paths, cik)
        raw_df, loaded = load_fact_frames(paths, revision, folder)
        df = normalize(raw_df)
        categories, cache_categories = {}, {}
        for category, labels in LABELS.items():
            candidates, frames = [], {}
            for label in labels:
                part = rows_for_label(df, label)
                frames[label] = part
                candidates.append({"label": label, **summarize(part)})
            candidates.sort(key=lambda x: (x["distinct_filings"], x["filed_years"], x["rows"]), reverse=True)
            selected = dict(candidates[0])
            selected["eligible"] = bool(selected["distinct_filings"] >= MIN_DISTINCT_FILINGS and selected["filed_years"] >= MIN_FILED_YEARS)
            all_eligible = all_eligible and selected["eligible"]
            categories[category] = {"selected": selected, "candidates": candidates}
            cache_categories[category] = {"label": selected["label"], "rows": compact_rows(frames[selected["label"]])}
        coverage[symbol] = {"cik": cik, "source_folder": folder, "downloaded": loaded, "categories": categories}
        cache_symbols[symbol] = {"cik": cik, "source_folder": folder, "categories": cache_categories}

    cache = {
        "schema": "public_compute.semiconductor_sec_fundamental_cache.v1",
        "source_dataset": DATASET, "source_dataset_revision": revision,
        "source_last_modified": info.get("lastModified"), "development_universe": list(SYMBOLS),
        "filing_time_authority": "mirrored SEC filed field; consumers must enforce filed <= signal date",
        "filed_window": {"start": START_FILED, "cutoff": CUTOFF_FILED},
        "semantic_categories": list(LABELS), "symbols": cache_symbols,
    }
    raw = canonical_bytes(cache); cache_sha = hashlib.sha256(raw).hexdigest(); CACHE.write_bytes(raw + b"\n")
    status = "PASS" if all_eligible else "FAIL"
    receipt = {
        "schema": "public_compute.semiconductor_hf_sec_fundamental_preflight.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(), "source_dataset": DATASET,
        "source_dataset_revision": revision, "source_last_modified": info.get("lastModified"),
        "transport": "Hugging Face repository metadata + targeted per-CIK parquet; no dataset-server search/filter",
        "development_universe": list(SYMBOLS), "semantic_categories_frozen_before_model_outcomes": list(LABELS),
        "eligibility_gate": {"minimum_distinct_filings_per_category_per_symbol": MIN_DISTINCT_FILINGS, "minimum_filed_years_per_category_per_symbol": MIN_FILED_YEARS, "all_six_categories_required": True},
        "coverage": coverage, "normalized_cache": {"path": str(CACHE), "sha256": cache_sha, "bytes": len(raw)+1},
        "status": status, "targets_computed": False, "model_executed": False,
        "external_semiconductor_holdouts_loaded": False,
        "next_boundary": "PASS authorizes committing this exact normalized public cache and one development-only point-in-time information-value consumer against PR31/PR34 control",
        "research_only": True, "promotion_authority": False, "runtime_mutation": False, "broker_action": False, "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n")
    print("SEMICONDUCTOR_HF_SEC_FUNDAMENTAL_PREFLIGHT="+json.dumps(receipt, sort_keys=True))
    if status != "PASS": raise SystemExit(2)


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except Exception as exc:
        failure = {"schema":"public_compute.semiconductor_hf_sec_fundamental_preflight.v2","generated_at":datetime.now(timezone.utc).isoformat(),"source_dataset":DATASET,"development_universe":list(SYMBOLS),"status":"TRANSPORT_OR_SCHEMA_FAILURE","error":str(exc),"targets_computed":False,"model_executed":False,"external_semiconductor_holdouts_loaded":False,"research_only":True,"promotion_authority":False,"runtime_mutation":False,"broker_action":False,"live_trading_change":False}
        OUT.write_text(json.dumps(failure,indent=2,sort_keys=True)+"\n"); print("SEMICONDUCTOR_HF_SEC_FUNDAMENTAL_PREFLIGHT="+json.dumps(failure,sort_keys=True)); raise
