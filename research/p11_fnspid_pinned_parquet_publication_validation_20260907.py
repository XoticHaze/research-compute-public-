from __future__ import annotations

import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone
from pathlib import Path

import duckdb
from huggingface_hub import HfApi

from p11_fnspid_article_publication_authority_validation_20260907 import (
    EARLY_TOLERANCE_MINUTES,
    INTRADAY_MEDIAN_MAX_MINUTES,
    INTRADAY_P95_MAX_MINUTES,
    MIN_AUTHORITATIVE_ROWS,
    MIN_AUTHORITATIVE_SYMBOLS,
    SYMBOLS,
    extract_publication_metadata,
    fetch_article,
    parse_ts,
    percentile,
)

MIRROR_REPO = "sabareesh88/FNSPID_nasdaq"
MIRROR_REVISION = "7e2d626"
UPSTREAM_PINNED_OBJECT_SHA256 = "1a7a3eb8e6b97ec19f286f2cfca3371542bddb272ab1eb8f36e33ad98fa5c4da"
EXPECTED_SHARDS = 48
OUT = Path("p11_fnspid_pinned_parquet_publication_validation_20260907.json")


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def resolve_pinned_mirror() -> tuple[str, list[str]]:
    api = HfApi()
    info = api.dataset_info(MIRROR_REPO, revision=MIRROR_REVISION, files_metadata=True)
    resolved = str(info.sha)
    if not resolved.startswith(MIRROR_REVISION):
        raise RuntimeError(f"mirror revision mismatch requested={MIRROR_REVISION} resolved={resolved}")
    names = sorted(
        s.rfilename
        for s in (info.siblings or [])
        if s.rfilename.startswith("data/train-") and s.rfilename.endswith(".parquet")
    )
    expected_names = [f"data/train-{i:05d}-of-{EXPECTED_SHARDS:05d}.parquet" for i in range(EXPECTED_SHARDS)]
    if names != expected_names:
        raise RuntimeError(f"pinned mirror shard set changed: found={len(names)} expected={EXPECTED_SHARDS}")
    urls = [f"https://huggingface.co/datasets/{MIRROR_REPO}/resolve/{resolved}/{name}?download=true" for name in names]
    return resolved, urls


def materialize_deterministic_sample(urls: list[str]) -> tuple[list[dict], dict[str, int]]:
    con = duckdb.connect(database=":memory:")
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    # The first public run proved that the pinned Parquet representation resolves,
    # but DuckDB's default parallel remote scan tripped the Hub's request-rate limit
    # (HTTP 429 on shard 15). Preserve the exact source/sample semantics and change
    # only transport pressure: one DuckDB worker, metadata caching, and bounded
    # exponential retry/backoff for remote range reads.
    con.execute("SET threads=1")
    con.execute("SET enable_http_metadata_cache=true")
    con.execute("SET http_retries=12")
    con.execute("SET http_retry_wait_ms=1000")
    con.execute("SET http_retry_backoff=2")
    con.execute("SET http_timeout=120")
    url_expr = "[" + ",".join(_q(u) for u in urls) + "]"
    symbols_expr = "(" + ",".join(_q(s) for s in SYMBOLS) + ")"
    query = f"""
        WITH base AS (
          SELECT Date, Stock_symbol, Url, Publisher, Article_title
          FROM read_parquet({url_expr})
          WHERE upper(Stock_symbol) IN {symbols_expr}
        ), ranked AS (
          SELECT
            Date,
            upper(Stock_symbol) AS Stock_symbol,
            Url,
            Publisher,
            Article_title,
            row_number() OVER (
              PARTITION BY upper(Stock_symbol)
              ORDER BY Date ASC, coalesce(Url,''), coalesce(Article_title,'')
            ) AS rn,
            count(*) OVER (PARTITION BY upper(Stock_symbol)) AS n
          FROM base
        )
        SELECT Date, Stock_symbol, Url, Publisher, Article_title, rn, n,
          CASE
            WHEN rn = 1 + round((n - 1) * 0.10) THEN 0.10
            WHEN rn = 1 + round((n - 1) * 0.50) THEN 0.50
            WHEN rn = 1 + round((n - 1) * 0.90) THEN 0.90
          END AS quantile
        FROM ranked
        WHERE rn IN (
          1 + round((n - 1) * 0.10),
          1 + round((n - 1) * 0.50),
          1 + round((n - 1) * 0.90)
        )
        ORDER BY Stock_symbol, quantile
    """
    rows = con.execute(query).fetchall()
    cols = [x[0] for x in con.description]
    samples = [dict(zip(cols, row)) for row in rows]
    counts: dict[str, int] = {}
    for sample in samples:
        counts[str(sample["Stock_symbol"])] = int(sample["n"])
        sample["rn"] = int(sample["rn"])
        sample["n"] = int(sample["n"])
        sample["quantile"] = float(sample["quantile"])
    missing = sorted(set(SYMBOLS) - set(counts))
    if missing:
        raise RuntimeError(f"target symbols absent from pinned mirror: {missing}")
    if len(samples) != len(SYMBOLS) * 3:
        raise RuntimeError(f"deterministic sample cardinality mismatch rows={len(samples)} expected={len(SYMBOLS)*3}")
    return samples, counts


def inspect_one(sample: dict) -> dict:
    base = {
        "symbol": sample["Stock_symbol"],
        "quantile": sample["quantile"],
        "row_number": sample["rn"],
        "mirror_symbol_rows": sample["n"],
        "fnspid_date_raw": sample.get("Date"),
        "url": sample.get("Url"),
        "publisher": sample.get("Publisher"),
    }
    fn = parse_ts(sample.get("Date"))
    if fn is None:
        return {"kind": "no_metadata", **base, "reason": "fnspid timestamp not offset-aware/parseable"}
    url = (sample.get("Url") or "").strip()
    if not url:
        return {"kind": "no_metadata", **base, "reason": "missing article URL"}
    try:
        html, final_url = fetch_article(url)
    except Exception as exc:
        return {"kind": "fetch_failure", **base, "error": str(exc)}
    candidates = extract_publication_metadata(html)
    if not candidates:
        return {"kind": "no_metadata", **base, "final_url": final_url, "reason": "no explicit article publication metadata"}
    authority, raw, publication = candidates[0]
    lag_minutes = (fn - publication).total_seconds() / 60.0
    return {
        "kind": "observation",
        **base,
        "final_url": final_url,
        "metadata_authority": authority,
        "publication_raw": raw,
        "publication_utc": publication.astimezone(timezone.utc).isoformat(),
        "fnspid_utc": fn.astimezone(timezone.utc).isoformat(),
        "fnspid_minus_publication_minutes": lag_minutes,
        "causal_safe_at_fnspid_time": lag_minutes >= -EARLY_TOLERANCE_MINUTES,
    }


def main() -> None:
    resolved_revision, urls = resolve_pinned_mirror()
    samples, counts = materialize_deterministic_sample(urls)

    inspected: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(inspect_one, sample): sample for sample in samples}
        for future in as_completed(futures):
            inspected.append(future.result())
    inspected.sort(key=lambda x: (x.get("symbol", ""), float(x.get("quantile", 0.0))))

    observations = [{k: v for k, v in x.items() if k != "kind"} for x in inspected if x["kind"] == "observation"]
    fetch_failures = [{k: v for k, v in x.items() if k != "kind"} for x in inspected if x["kind"] == "fetch_failure"]
    no_metadata = [{k: v for k, v in x.items() if k != "kind"} for x in inspected if x["kind"] == "no_metadata"]

    lags = [float(x["fnspid_minus_publication_minutes"]) for x in observations]
    auth_symbols = sorted({x["symbol"] for x in observations})
    unsafe = [x for x in observations if not x["causal_safe_at_fnspid_time"]]
    sufficient = len(observations) >= MIN_AUTHORITATIVE_ROWS and len(auth_symbols) >= MIN_AUTHORITATIVE_SYMBOLS
    median = statistics.median(lags) if lags else None
    p95 = percentile(lags, 0.95)

    if sufficient and not unsafe and median is not None and median <= INTRADAY_MEDIAN_MAX_MINUTES and p95 is not None and p95 <= INTRADAY_P95_MAX_MINUTES:
        decision = "FNSPID_INTRADAY_PUBLICATION_AUTHORITY_SUPPORTED"
        next_boundary = "Run the frozen News State scorer-calibration gate if not already complete, then execute the fixed incremental-value ablation only if calibration admits a scorer."
    elif sufficient and not unsafe:
        decision = "FNSPID_CAUSAL_BUT_INTRADAY_TIMELINESS_NOT_SUPPORTED"
        next_boundary = "Retain for daily/descriptive causal research; do not run the frozen intraday ablation without a better publication-time source."
    else:
        decision = "FNSPID_PUBLICATION_AUTHORITY_HOLD_OR_ROTATE"
        next_boundary = "Rotate P11 to a source with explicit point-in-time publication metadata, or obtain stronger authoritative article-level coverage before economic testing."

    out = {
        "schema": "public_research.p11_fnspid_pinned_parquet_publication_validation.v1",
        "research_only": True,
        "transport_change_only": True,
        "transport_mirror": MIRROR_REPO,
        "mirror_revision_requested": MIRROR_REVISION,
        "mirror_revision_resolved": resolved_revision,
        "mirror_native_parquet_shards": len(urls),
        "remote_transport": {
            "duckdb_threads": 1,
            "http_retries": 12,
            "http_retry_wait_ms": 1000,
            "http_retry_backoff": 2,
            "http_timeout_seconds": 120,
            "metadata_cache": True,
            "mechanism_change_reason": "first pinned-Parquet run reached the exact shard scan then failed HTTP 429 on shard 15 under default parallel remote I/O",
        },
        "mirror_role": "existing admitted Nasdaq-only FNSPID transport mirror previously used by P11 indexed validation; Parquet replaces failed server-side /filter only",
        "upstream_semantic_parent": "Zdong104/FNSPID_Financial_News_Dataset@4054842ec476953b30ee874d4b7e8eea786a21fa",
        "upstream_pinned_object_sha256": UPSTREAM_PINNED_OBJECT_SHA256,
        "sample_rule": "For each frozen Semiconductor/Homebuilder symbol, order the pinned mirror by Date then URL/title and take 10%, 50%, 90% rows. Rule inherited from the prior publication-authority validator before article fetches.",
        "mirror_symbol_row_counts": counts,
        "sampled_rows": len(samples),
        "authoritative_metadata_rows": len(observations),
        "authoritative_symbols": auth_symbols,
        "fetch_failures": fetch_failures,
        "no_authoritative_metadata": no_metadata,
        "observations": observations,
        "causality_gate": {
            "minimum_authoritative_rows": MIN_AUTHORITATIVE_ROWS,
            "minimum_authoritative_symbols": MIN_AUTHORITATIVE_SYMBOLS,
            "early_tolerance_minutes": EARLY_TOLERANCE_MINUTES,
            "unsafe_early_rows": len(unsafe),
            "median_fnspid_minus_publication_minutes": median,
            "p95_fnspid_minus_publication_minutes": p95,
            "decision": decision,
            "next_boundary": next_boundary,
        },
        "publication_metadata_allowed": ["JSON-LD datePublished", "meta article:published_time", "explicit publication-date meta fields"],
        "heuristic_page_dates_used": False,
        "economic_model_executed": False,
        "strategy_spec_mutation": False,
        "runtime_mutation": False,
        "promotion_authority": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(out, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("P11_FNSPID_PINNED_PARQUET_PUBLICATION=" + json.dumps(out, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
