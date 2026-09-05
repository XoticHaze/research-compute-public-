#!/usr/bin/env python3
import json
import urllib.parse
import urllib.request
from pathlib import Path

import duckdb

DATASET = "Zihan1004/FNSPID"
BASE = "https://datasets-server.huggingface.co"
UA = {"User-Agent": "research-compute-public/1"}


def get_json(path: str):
    req = urllib.request.Request(f"{BASE}{path}", headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except Exception as exc:
        return {"request_error": type(exc).__name__, "message": str(exc)}


def main() -> None:
    ds = urllib.parse.quote(DATASET, safe="")
    validity = get_json(f"/is-valid?dataset={ds}")
    splits = get_json(f"/splits?dataset={ds}")
    parquet = get_json(f"/parquet?dataset={ds}")
    size = get_json(f"/size?dataset={ds}")
    files = parquet.get("parquet_files") or []

    schemas = []
    if files:
        con = duckdb.connect()
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
        for item in files[:4]:
            url = item["url"]
            rows = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [url]).fetchall()
            schemas.append({
                "config": item.get("config"),
                "split": item.get("split"),
                "filename": item.get("filename"),
                "size": item.get("size"),
                "url": url,
                "columns": [{"name": r[0], "type": r[1]} for r in rows],
            })

    out = {
        "schema": "research_compute_public.fnspid_parquet_capability_probe.v1",
        "dataset": DATASET,
        "validity": validity,
        "splits": splits,
        "size": size,
        "parquet_available": bool(files),
        "parquet_file_count": len(files),
        "parquet_files": files,
        "sample_schemas": schemas,
        "next_route": "parquet_remote_filter" if files else "pinned_lfs_http_range_probe",
        "research_only": True,
        "promotion_authority": False,
    }
    Path("fnspid-parquet-capability-receipt.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("FNSPID_PARQUET_CAPABILITY=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
