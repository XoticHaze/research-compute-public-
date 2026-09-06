from __future__ import annotations

"""Probe the reorganized DenyTran SEC Company Facts mirror via direct Parquet range reads.

This bypasses both the broken Dataset Viewer filters and the obsolete per-CIK-folder
assumption. It reads one frozen company/category discriminator only and computes no target/model.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

OUT = Path("sec_hf_root_parquet_probe_20260906.json")
URL = "https://huggingface.co/datasets/DenyTranDFW/edgar_xbrl_companyfacts/resolve/main/Facts_UsGaap.parquet"


def main():
    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    schema = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{URL}')").fetchall()]
    required = {"source_folder", "label", "unit", "filed", "form", "accn"}
    missing = sorted(required - set(schema))
    if missing:
        raise RuntimeError(f"root parquet missing required columns={missing}; columns={schema}")
    row = con.execute(
        f"""
        SELECT COUNT(*) AS rows,
               COUNT(DISTINCT accn) AS distinct_filings,
               MIN(filed) AS first_filed,
               MAX(filed) AS last_filed,
               MIN(source_folder) AS folder
        FROM read_parquet('{URL}')
        WHERE source_folder LIKE 'CIK0000006951_%'
          AND label = 'Assets'
          AND UPPER(COALESCE(unit, '')) = 'USD'
          AND filed >= '2014-01-01' AND filed <= '2026-09-03'
          AND form IN ('10-Q','10-K','20-F','40-F')
        """
    ).fetchone()
    receipt = {
        "schema": "public_compute.sec_hf_root_parquet_probe.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": URL,
        "columns": schema,
        "probe": {
            "symbol": "AMAT",
            "cik": "0000006951",
            "category": "assets",
            "label": "Assets",
            "rows": int(row[0]),
            "distinct_filings": int(row[1]),
            "first_filed": None if row[2] is None else str(row[2]),
            "last_filed": None if row[3] is None else str(row[3]),
            "source_folder": row[4],
        },
        "status": "PASS" if int(row[1]) >= 16 else "FAIL",
        "targets_computed": False,
        "model_executed": False,
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print("SEC_HF_ROOT_PARQUET_PROBE=" + json.dumps(receipt, sort_keys=True))
    if receipt["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        failure = {
            "schema": "public_compute.sec_hf_root_parquet_probe.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": URL,
            "status": "TRANSPORT_OR_SCHEMA_FAILURE",
            "error": str(exc),
            "targets_computed": False,
            "model_executed": False,
            "research_only": True,
            "promotion_authority": False,
            "runtime_mutation": False,
            "broker_action": False,
            "live_trading_change": False,
        }
        OUT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        print("SEC_HF_ROOT_PARQUET_PROBE=" + json.dumps(failure, sort_keys=True))
        raise
