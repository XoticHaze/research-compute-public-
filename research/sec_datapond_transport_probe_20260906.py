from __future__ import annotations

"""Probe a public-domain SEC Financial Statement Data Sets DuckDB mirror.

The source database is a redistribution of official SEC quarterly Financial Statement
Data Sets. This probe executes only metadata and filing-coverage queries for the frozen
seven-company development universe. It computes no targets/models and changes no runtime.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import datapond
import duckdb

OUT = Path("sec_datapond_transport_probe_20260906.json")
REMOTE_DB = "https://huggingface.co/datasets/erlenbusch/sec-edgar/resolve/main/sec_edgar.duckdb"
CIKS = (
    "0000006951", "0000820313", "0000319201", "0000707549",
    "0000097476", "0001413447", "0000006281",
)
FORMS = ("10-Q", "10-K", "20-F", "40-F")


def connect_remote():
    try:
        return datapond.connect("sec_edgar"), "datapond_registry"
    except ValueError as exc:
        if "not found in registry" not in str(exc):
            raise
    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"ATTACH '{REMOTE_DB}' AS sec_edgar (READ_ONLY)")
    con.execute("USE sec_edgar")
    return con, "direct_huggingface_duckdb_attach"


def main() -> None:
    con, transport = connect_remote()
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    required = {"submissions", "numbers", "presentations", "tags"}
    missing = sorted(required - set(tables))
    if missing:
        raise RuntimeError(f"remote SEC database missing required tables={missing}; tables={tables}")

    schema_rows = con.execute("DESCRIBE submissions").fetchall()
    schema = [str(r[0]) for r in schema_rows]
    for required_col in ("cik", "form", "filed", "adsh"):
        if required_col not in schema:
            raise RuntimeError(f"submissions missing {required_col}; columns={schema}")

    cik_sql = ",".join("?" for _ in CIKS)
    form_sql = ",".join("?" for _ in FORMS)
    sql = f"""
        SELECT
            LPAD(CAST(cik AS VARCHAR), 10, '0') AS cik,
            COUNT(DISTINCT adsh) AS distinct_filings,
            MIN(filed) AS first_filed,
            MAX(filed) AS last_filed
        FROM submissions
        WHERE LPAD(CAST(cik AS VARCHAR), 10, '0') IN ({cik_sql})
          AND form IN ({form_sql})
          AND filed >= '2014-01-01'
          AND filed <= '2026-09-03'
        GROUP BY 1
        ORDER BY 1
    """
    rows = con.execute(sql, [*CIKS, *FORMS]).fetchall()
    coverage = {
        str(cik): {
            "distinct_filings": int(count),
            "first_filed": str(first_filed),
            "last_filed": str(last_filed),
        }
        for cik, count, first_filed, last_filed in rows
    }
    status = "PASS" if set(coverage) == set(CIKS) and all(v["distinct_filings"] >= 16 for v in coverage.values()) else "FAIL"
    receipt = {
        "schema": "public_compute.sec_datapond_transport_probe.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "erlenbusch/sec-edgar public-domain DuckDB derived from SEC Financial Statement Data Sets",
        "transport": transport,
        "remote_database": REMOTE_DB,
        "required_tables": sorted(required),
        "submissions_columns": schema,
        "development_ciks": list(CIKS),
        "coverage": coverage,
        "status": status,
        "targets_computed": False,
        "model_executed": False,
        "external_holdout_loaded": False,
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
        "next_boundary": (
            "PASS authorizes a six-category SEC tag-coverage query and compact point-in-time cache extraction; "
            "FAIL rejects this transport without weakening the frozen scientific contract"
        ),
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SEC_DATAPOND_TRANSPORT_PROBE=" + json.dumps(receipt, sort_keys=True))
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        failure = {
            "schema": "public_compute.sec_datapond_transport_probe.v2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "TRANSPORT_OR_SCHEMA_FAILURE",
            "error": str(exc),
            "targets_computed": False,
            "model_executed": False,
            "external_holdout_loaded": False,
            "research_only": True,
            "promotion_authority": False,
            "runtime_mutation": False,
            "broker_action": False,
            "live_trading_change": False,
        }
        OUT.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("SEC_DATAPOND_TRANSPORT_PROBE=" + json.dumps(failure, sort_keys=True))
        raise
