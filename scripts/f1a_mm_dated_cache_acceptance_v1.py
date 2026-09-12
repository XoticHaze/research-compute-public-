from __future__ import annotations

"""Convert admitted F1a dated-contract CSVs into MM local dated-cache staging.

This release/acceptance consumer reshapes only source contracts that satisfy the
existing MM-IBKR dated-contract cache invariants. Provider contracts with invalid
OHLC geometry are quarantined unchanged and reported; they are never silently
repaired. Continuous stitching and roll selection remain MM FuturesManager authority.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOTS = ("6E", "ES", "NG", "NQ", "ZS")
PROVIDER_ROOT_ALIASES = {"6E": ("6E", "EC"), "ES": ("ES",), "NG": ("NG",), "NQ": ("NQ",), "ZS": ("ZS",)}
MONTH_CODE = {"F":"01","G":"02","H":"03","J":"04","K":"05","M":"06","N":"07","Q":"08","U":"09","V":"10","X":"11","Z":"12"}
REQUIRED_PROVIDER_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume", "Open Interest"]
CACHE_REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_contract(path: Path) -> tuple[str, str]:
    root = next((part.upper() for part in path.parts if part.upper() in ROOTS), None)
    if root is None:
        raise RuntimeError(f"root directory identity missing for {path}")
    aliases = "|".join(re.escape(v) for v in PROVIDER_ROOT_ALIASES[root])
    m = re.search(rf"_(?:{aliases})([FGHJKMNQUVXZ])(\d{{4}})$", path.stem.upper())
    if not m:
        raise RuntimeError(f"unrecognized {root} dated-contract filename: {path.name}")
    code, year = m.groups()
    return root, year + MONTH_CODE[code]


def transform_one(source: Path, output_root: Path) -> dict:
    root, yyyymm = parse_contract(source)
    source_sha = sha256_file(source)
    df = pd.read_csv(source, low_memory=False)
    if list(map(str, df.columns)) != REQUIRED_PROVIDER_COLUMNS:
        raise RuntimeError(f"provider columns mismatch for {source.name}: {list(df.columns)!r}")
    out = pd.DataFrame()
    parsed = pd.to_datetime(df["Date"], errors="coerce", utc=False)
    if parsed.isna().any():
        raise RuntimeError(f"unparseable Date values in {source.name}: {int(parsed.isna().sum())}")
    out["timestamp"] = parsed.dt.strftime("%Y-%m-%d")
    for src, dst in (("Open","open"),("High","high"),("Low","low"),("Close","close"),("Volume","volume")):
        out[dst] = pd.to_numeric(df[src], errors="coerce")
    out["open_interest"] = pd.to_numeric(df["Open Interest"], errors="coerce")
    if out[CACHE_REQUIRED_COLUMNS[1:]].isna().any().any():
        bad = {c:int(out[c].isna().sum()) for c in CACHE_REQUIRED_COLUMNS[1:] if out[c].isna().any()}
        raise RuntimeError(f"non-numeric required OHLCV in {source.name}: {bad}")
    if out["timestamp"].duplicated().any():
        raise RuntimeError(f"duplicate timestamps in {source.name}")

    high_lt_low = out["high"] < out["low"]
    high_lt_open_close = out["high"] < out[["open","close"]].max(axis=1)
    low_gt_open_close = out["low"] > out[["open","close"]].min(axis=1)
    invalid = high_lt_low | high_lt_open_close | low_gt_open_close
    if invalid.any():
        bad_rows = []
        for idx in out.index[invalid][:50]:
            bad_rows.append({
                "timestamp": str(out.at[idx,"timestamp"]),
                "open": float(out.at[idx,"open"]), "high": float(out.at[idx,"high"]),
                "low": float(out.at[idx,"low"]), "close": float(out.at[idx,"close"]),
                "high_lt_low": bool(high_lt_low.at[idx]),
                "high_lt_open_or_close": bool(high_lt_open_close.at[idx]),
                "low_gt_open_or_close": bool(low_gt_open_close.at[idx]),
            })
        return {
            "status":"QUARANTINED_SOURCE_OHLC_GEOMETRY",
            "root":root, "contract_month":yyyymm, "source_file":source.name,
            "source_sha256":source_sha, "rows":int(len(out)), "invalid_row_count":int(invalid.sum()),
            "invalid_counts":{
                "high_lt_low":int(high_lt_low.sum()),
                "high_lt_open_or_close":int(high_lt_open_close.sum()),
                "low_gt_open_or_close":int(low_gt_open_close.sum()),
            },
            "invalid_rows_sample":bad_rows,
            "source_mutated":False,
        }

    out = out.sort_values("timestamp").reset_index(drop=True)
    target = output_root / "data" / "futures" / f"{root}-{yyyymm}" / "1Day.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RuntimeError(f"duplicate contract target: {target}")
    out.to_csv(target, index=False, lineterminator="\n")
    return {
        "status":"STAGED", "root":root, "contract_month":yyyymm,
        "source_file":source.name, "source_sha256":source_sha,
        "target_path":target.relative_to(output_root).as_posix(), "target_sha256":sha256_file(target),
        "rows":int(len(out)), "first_timestamp":None if out.empty else str(out["timestamp"].iloc[0]),
        "last_timestamp":None if out.empty else str(out["timestamp"].iloc[-1]), "open_interest_preserved":True,
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--input-root",required=True,type=Path)
    ap.add_argument("--output-root",required=True,type=Path)
    ap.add_argument("--receipt",required=True,type=Path)
    ap.add_argument("--source-run-id",required=True)
    ns=ap.parse_args()
    source_files=sorted(p for p in ns.input_root.rglob("*.csv") if p.is_file())
    if not source_files: raise RuntimeError("no F1a dated-contract CSVs found")
    rows=[transform_one(p,ns.output_root) for p in source_files]
    staged=[r for r in rows if r["status"]=="STAGED"]
    quarantined=[r for r in rows if r["status"]!="STAGED"]
    seen_roots=sorted({r["root"] for r in staged})
    if seen_roots!=sorted(ROOTS): raise RuntimeError(f"five-root clean staging incomplete: {seen_roots!r}")
    staged_counts={root:sum(1 for r in staged if r["root"]==root) for root in ROOTS}
    quarantine_counts={root:sum(1 for r in quarantined if r["root"]==root) for root in ROOTS}
    if any(v==0 for v in staged_counts.values()): raise RuntimeError(f"missing clean staged root: {staged_counts}")
    acceptance="MM_LOCAL_DATED_CACHE_COMPATIBLE_STAGING_WITH_SOURCE_QUARANTINE" if quarantined else "MM_LOCAL_DATED_CACHE_COMPATIBLE_STAGING"
    receipt={
        "schema":"public_research.f1a_mm_dated_cache_acceptance.v1",
        "source_run_id":str(ns.source_run_id), "accepted_roots":seen_roots,
        "source_contract_file_count":len(rows), "staged_contract_file_count":len(staged),
        "quarantined_contract_file_count":len(quarantined), "staged_counts":staged_counts,
        "quarantine_counts":quarantine_counts,
        "cache_contract":"MM-IBKR FuturesManager local dated-contract cache data/futures/<ROOT>-<YYYYMM>/1Day.csv",
        "required_cache_columns":CACHE_REQUIRED_COLUMNS,
        "provider_session_date_preserved_as_naive_timestamp":True,
        "provider_root_aliases":PROVIDER_ROOT_ALIASES, "open_interest_preserved":True,
        "source_rows_repaired_or_deleted":False, "continuous_series_constructed":False,
        "roll_cutoff_selected":False, "feature_materialization_performed":False,
        "strategy_spec_write":False, "runtime_authority":False, "broker_authority":False,
        "live_trading_change":False, "acceptance":acceptance,
        "staged_files":staged, "quarantined_source_contracts":quarantined,
    }
    ns.receipt.parent.mkdir(parents=True,exist_ok=True)
    ns.receipt.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("F1A_MM_DATED_CACHE_ACCEPTANCE=PASS")
    print("F1A_MM_DATED_CACHE_ROOTS="+",".join(seen_roots))
    print("F1A_MM_DATED_CACHE_STAGED_CONTRACTS="+str(len(staged)))
    print("F1A_MM_DATED_CACHE_QUARANTINED_CONTRACTS="+str(len(quarantined)))
    print("F1A_MM_DATED_CACHE_RECEIPT_SHA256="+sha256_file(ns.receipt))
    return 0

if __name__=="__main__": raise SystemExit(main())
