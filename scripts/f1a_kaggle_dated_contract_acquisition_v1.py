from __future__ import annotations

"""F1a dated-contract raw-byte acquisition and QA.

Execution-only utility. It downloads one frozen public Kaggle dataset handle,
preserves provider paths/bytes, hashes every file, and emits deterministic QA.
It does not build continuous series, shift OI, engineer features, or train models.
"""

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import kagglehub
import numpy as np
import pandas as pd

ROOT_HANDLES = {
    "ES": "choweric/cme-es",
    "NQ": "choweric/cme-nasdaq",
    "NG": "choweric/nymex-ng",
    "ZS": "choweric/cbot-soybeans",
    "6E": "choweric/cme-euro",
}
ATTRIBUTION = {
    "publisher": "Eric Chow",
    "license": "CC BY-SA 4.0",
    "open_interest_semantics": "provider states Open Interest is reported for the previous trading day; raw values are preserved without forward shifting",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_col(cols: list[str], names: tuple[str, ...]) -> str | None:
    norm = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in cols}
    for n in names:
        k = re.sub(r"[^a-z0-9]", "", n.lower())
        if k in norm:
            return norm[k]
    return None


def numeric_summary(s: pd.Series) -> dict:
    x = pd.to_numeric(s, errors="coerce")
    finite = x[np.isfinite(x)]
    return {
        "null_or_non_numeric": int(x.isna().sum()),
        "negative": int((finite < 0).sum()),
        "zero": int((finite == 0).sum()),
        "min": None if finite.empty else float(finite.min()),
        "max": None if finite.empty else float(finite.max()),
    }


def qa_csv(path: Path, expected_root: str) -> dict:
    out = {"path": path.as_posix(), "parse_state": "NOT_ATTEMPTED", "root_identity": expected_root}
    name = path.name.upper()
    aliases = {expected_root}
    if expected_root == "6E": aliases |= {"6E", "EURO"}
    elif expected_root == "NQ": aliases |= {"NQ", "NASDAQ"}
    elif expected_root == "ES": aliases |= {"ES", "SP500", "S&P"}
    elif expected_root == "NG": aliases |= {"NG", "NATURALGAS", "NATURAL_GAS"}
    elif expected_root == "ZS": aliases |= {"ZS", "SOY", "SOYBEAN"}
    out["provider_path_root_match"] = bool(any(a in name for a in aliases))
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as exc:
        out["parse_state"] = "CSV_PARSE_FAILED"
        out["parse_error"] = f"{type(exc).__name__}: {exc}"[:1000]
        return out
    out["parse_state"] = "PARSED"
    out["rows"] = int(len(df))
    out["columns"] = [str(c) for c in df.columns]
    cols = list(map(str, df.columns))
    ts = find_col(cols, ("timestamp", "datetime", "date", "time"))
    if ts:
        parsed = pd.to_datetime(df[ts], errors="coerce", utc=False)
        valid = parsed.dropna()
        out["time_column"] = ts
        out["time_parse_nulls"] = int(parsed.isna().sum())
        out["first_time"] = None if valid.empty else str(valid.min())
        out["last_time"] = None if valid.empty else str(valid.max())
        tz = getattr(getattr(valid, "dt", None), "tz", None)
        out["timezone_semantics"] = str(tz) if tz is not None else "NAIVE_OR_DATE_ONLY"
        out["duplicate_time_rows"] = int(parsed.duplicated(keep=False).sum())
        if len(valid) >= 3:
            diffs = valid.sort_values().diff().dropna()
            positive = diffs[diffs > pd.Timedelta(0)]
            if not positive.empty:
                mode = positive.mode()
                expected = mode.iloc[0] if not mode.empty else positive.median()
                out["observed_modal_interval"] = str(expected)
                out["intervals_gt_3x_modal"] = int((positive > expected * 3).sum())
    else:
        out["time_column"] = None
        out["timezone_semantics"] = "UNRESOLVED_NO_RECOGNIZED_TIME_COLUMN"
    o = find_col(cols, ("open",)); h = find_col(cols, ("high",)); l = find_col(cols, ("low",)); c = find_col(cols, ("close", "settle", "settlement"))
    if all((o, h, l, c)):
        on = pd.to_numeric(df[o], errors="coerce"); hn = pd.to_numeric(df[h], errors="coerce"); ln = pd.to_numeric(df[l], errors="coerce"); cn = pd.to_numeric(df[c], errors="coerce")
        valid = pd.concat([on, hn, ln, cn], axis=1).dropna()
        out["ohlc_columns"] = {"open": o, "high": h, "low": l, "close": c}
        out["ohlc_invalid_high_lt_open_or_close"] = int((valid.iloc[:, 1] < valid[[valid.columns[0], valid.columns[3]]].max(axis=1)).sum())
        out["ohlc_invalid_low_gt_open_or_close"] = int((valid.iloc[:, 2] > valid[[valid.columns[0], valid.columns[3]]].min(axis=1)).sum())
        out["ohlc_invalid_high_lt_low"] = int((valid.iloc[:, 1] < valid.iloc[:, 2]).sum())
    else:
        out["ohlc_columns"] = None
    vol = find_col(cols, ("volume", "vol")); oi = find_col(cols, ("open interest", "open_interest", "openinterest", "oi"))
    out["volume"] = None if not vol else {"column": vol, **numeric_summary(df[vol])}
    out["open_interest"] = None if not oi else {"column": oi, **numeric_summary(df[oi])}
    out["open_interest_semantics"] = ATTRIBUTION["open_interest_semantics"]
    return out


def classify_download_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    return "SOURCE_CONSENT_REQUIRED" if any(x in text for x in ("consent", "accept", "agreement", "terms")) else "SOURCE_DOWNLOAD_FAILED"


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", choices=sorted(ROOT_HANDLES), required=True); ap.add_argument("--output-root", type=Path, required=True); args = ap.parse_args()
    root = args.root; handle = ROOT_HANDLES[root]; base = args.output_root.resolve(); raw = base / "raw" / root; meta = base / "metadata" / root
    raw.mkdir(parents=True, exist_ok=True); meta.mkdir(parents=True, exist_ok=True)
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    receipt = {"schema": "public_research.f1a_kaggle_dated_contract_acquisition_receipt.v1", "root": root, "handle": handle, "observed_at": observed_at, "kagglehub_version": getattr(kagglehub, "__version__", "unknown"), "license_attribution": ATTRIBUTION, "continuous_series_constructed": False, "open_interest_shift_applied": False}
    try:
        returned = kagglehub.dataset_download(handle, output_dir=str(raw), force_download=True)
        receipt["download_state"] = "ACQUIRED"; receipt["dataset_download_return"] = str(returned)
    except Exception as exc:
        receipt["download_state"] = classify_download_error(exc); receipt["download_error"] = f"{type(exc).__name__}: {exc}"[:4000]
        (meta / "acquisition_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        print("F1A_ROOT_RECEIPT=" + json.dumps(receipt, sort_keys=True)); return 0
    files = sorted(p for p in raw.rglob("*") if p.is_file()); inventory = []; qa = []
    for p in files:
        rel = p.relative_to(raw); inventory.append({"path": rel.as_posix(), "bytes": int(p.stat().st_size), "sha256": sha256_file(p)})
        qa.append(qa_csv(p, root) if p.suffix.lower() in {".csv", ".txt"} else {"path": rel.as_posix(), "parse_state": "NON_CSV_RAW_FILE", "suffix": p.suffix.lower()})
    manifest = {"schema": "public_research.f1a_dated_contract_manifest.v1", "root": root, "handle": handle, "observed_at": observed_at, "license_attribution": ATTRIBUTION, "files": inventory, "file_count": len(inventory), "total_bytes": int(sum(x["bytes"] for x in inventory))}
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    receipt["file_count"] = len(inventory); receipt["total_bytes"] = manifest["total_bytes"]; receipt["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest(); receipt["success_bytes_present"] = bool(inventory and manifest["total_bytes"] > 0)
    summary = {"schema": "public_research.f1a_root_qa.v1", "root": root, "handle": handle, "download_state": receipt["download_state"], "raw_file_count": len(inventory), "raw_total_bytes": manifest["total_bytes"], "parsed_files": int(sum(x.get("parse_state") == "PARSED" for x in qa)), "parse_failures": int(sum(x.get("parse_state") == "CSV_PARSE_FAILED" for x in qa)), "timezone_ambiguous_files": int(sum(x.get("timezone_semantics") == "NAIVE_OR_DATE_ONLY" for x in qa)), "oi_semantics": ATTRIBUTION["open_interest_semantics"], "continuous_series_constructed": False}
    (meta / "f1a_manifest.json").write_bytes(manifest_bytes); (meta / "f1a_qa.json").write_text(json.dumps({"summary": summary, "files": qa}, sort_keys=True, indent=2) + "\n"); (meta / "acquisition_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    (meta / "LICENSE_ATTRIBUTION.md").write_text(f"# F1a source attribution\n\n- Root: {root}\n- Kaggle handle: `{handle}`\n- Publisher: {ATTRIBUTION['publisher']}\n- License: {ATTRIBUTION['license']}\n- Open Interest semantics: {ATTRIBUTION['open_interest_semantics']}\n- Raw provider bytes and provider path names are preserved; no continuous-series construction occurs in F1a.\n")
    print("F1A_ROOT_RECEIPT=" + json.dumps(receipt, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
