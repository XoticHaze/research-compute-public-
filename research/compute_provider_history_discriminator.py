#!/usr/bin/env python3
"""Public-data-only P10 provider-conditioned GPU pricing discriminator.

Downloads explicitly pinned OpenComputePrices monthly release assets, verifies SHA-256,
filters only H100/H200/B200 rental rows, and evaluates bandwidth normalization inside
strict provider/date/pricing/location/form-factor/GPU-count/tenancy/commitment buckets.
No private inputs, interpolation, provider blending, or trading authority.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA = "research_compute_public.p10_provider_history_discriminator.v1"


def _f(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def _i(value: Any) -> int | None:
    try:
        x = int(float(value))
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def _gpu(value: str) -> str | None:
    u = (value or "").upper().replace("NVIDIA", " ")
    for g in ("H100", "H200", "B200"):
        if g in u:
            return g
    return None


def _price_per_gpu(row: dict[str, str]) -> float | None:
    p = _f(row.get("price_per_gpu_hour"))
    if p is not None:
        return p
    total = _f(row.get("price_per_hour"))
    count = _i(row.get("gpu_count"))
    if total is not None and count:
        return total / count
    return None


def _cv(values: list[float]) -> float:
    mean = statistics.fmean(values)
    return statistics.pstdev(values) / mean if mean else float("nan")


def _loo_mape(prices: dict[str, float], bandwidth: dict[str, float]) -> tuple[float, float]:
    raw_err = []
    norm_err = []
    for held in ("H100", "H200", "B200"):
        actual = prices[held]
        others = [g for g in ("H100", "H200", "B200") if g != held]
        raw_pred = statistics.median([prices[g] for g in others])
        norm_level = statistics.median([prices[g] / bandwidth[g] for g in others])
        norm_pred = norm_level * bandwidth[held]
        raw_err.append(abs(raw_pred - actual) / actual)
        norm_err.append(abs(norm_pred - actual) / actual)
    return statistics.fmean(raw_err), statistics.fmean(norm_err)


def _download(url: str, expected_sha256: str, dst: Path) -> dict[str, Any]:
    h = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(url, timeout=120) as r, dst.open("wb") as out:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            out.write(chunk)
            size += len(chunk)
    got = h.hexdigest()
    if got != expected_sha256:
        raise RuntimeError(f"archive digest mismatch for {url}: {got} != {expected_sha256}")
    return {"url": url, "sha256": got, "bytes": size}


def evaluate(contract: dict[str, Any]) -> dict[str, Any]:
    bandwidth = {k: float(v) for k, v in contract["memory_bandwidth_tb_s"].items()}
    target = set(bandwidth)
    raw_rows = []
    archive_receipts = []
    fieldnames_seen: set[str] = set()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for idx, spec in enumerate(contract["archives"]):
            path = td_path / f"archive_{idx}.csv.gz"
            archive_receipts.append(_download(spec["url"], spec["sha256"], path))
            with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                fieldnames_seen.update(reader.fieldnames or [])
                for row in reader:
                    gpu = _gpu(row.get("gpu_name", ""))
                    if gpu not in target:
                        continue
                    pricing = (row.get("pricing_type") or "").strip().lower()
                    if pricing not in {"on_demand", "spot", "reserved"}:
                        continue
                    price = _price_per_gpu(row)
                    if price is None:
                        continue
                    provider = (row.get("provider") or row.get("source") or "").strip().lower()
                    if not provider:
                        continue
                    date = (row.get("snapshot_date") or "").strip()
                    if not date:
                        continue
                    region = (row.get("region") or row.get("geo_group") or row.get("country") or "__unspecified__").strip()
                    variant = (row.get("gpu_variant") or row.get("gpu_interconnect") or "__unspecified__").strip().upper()
                    gpu_count = _i(row.get("gpu_count")) or 1
                    tenancy = (row.get("tenancy") or "__unspecified__").strip().lower()
                    commitment = (row.get("commitment_period") or "__none__").strip().lower()
                    raw_rows.append({
                        "provider": provider,
                        "date": date,
                        "pricing_type": pricing,
                        "region": region,
                        "variant": variant,
                        "gpu_count": gpu_count,
                        "tenancy": tenancy,
                        "commitment_period": commitment,
                        "gpu": gpu,
                        "price_per_gpu_hour": price,
                        "source": (row.get("source") or "").strip(),
                        "instance_type": (row.get("instance_type") or "").strip(),
                    })

    # Keep strict comparable shape. Multiple rows inside the same exact bucket/generation
    # are reduced by median only after all matching dimensions above are identical.
    grouped: dict[tuple[Any, ...], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    coverage: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for r in raw_rows:
        coverage[(r["provider"], r["gpu"], r["pricing_type"])].add(r["date"])
        key = (
            r["provider"], r["date"], r["pricing_type"], r["region"], r["variant"],
            r["gpu_count"], r["tenancy"], r["commitment_period"],
        )
        grouped[key][r["gpu"]].append(r["price_per_gpu_hour"])

    matched = []
    for key, by_gpu in grouped.items():
        if set(by_gpu) != target:
            continue
        prices = {g: statistics.median(by_gpu[g]) for g in sorted(target)}
        raw_cv = _cv([prices[g] for g in ("H100", "H200", "B200")])
        norm = {g: prices[g] / bandwidth[g] for g in target}
        norm_cv = _cv([norm[g] for g in ("H100", "H200", "B200")])
        raw_loo, norm_loo = _loo_mape(prices, bandwidth)
        matched.append({
            "provider": key[0], "date": key[1], "pricing_type": key[2],
            "region": key[3], "variant": key[4], "gpu_count": key[5],
            "tenancy": key[6], "commitment_period": key[7],
            "prices": prices,
            "raw_cv": raw_cv, "bandwidth_cv": norm_cv,
            "raw_loo_mape": raw_loo, "bandwidth_loo_mape": norm_loo,
            "bandwidth_improved_dispersion": norm_cv < raw_cv,
            "bandwidth_improved_loo": norm_loo < raw_loo,
        })

    provider_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in matched:
        provider_groups[(row["provider"], row["pricing_type"])].append(row)

    provider_results = []
    for (provider, pricing), rows in sorted(provider_groups.items()):
        provider_results.append({
            "provider": provider,
            "pricing_type": pricing,
            "matched_bucket_count": len(rows),
            "first_date": min(r["date"] for r in rows),
            "last_date": max(r["date"] for r in rows),
            "dispersion_improved_count": sum(r["bandwidth_improved_dispersion"] for r in rows),
            "loo_improved_count": sum(r["bandwidth_improved_loo"] for r in rows),
            "median_raw_cv": statistics.median(r["raw_cv"] for r in rows),
            "median_bandwidth_cv": statistics.median(r["bandwidth_cv"] for r in rows),
            "median_raw_loo_mape": statistics.median(r["raw_loo_mape"] for r in rows),
            "median_bandwidth_loo_mape": statistics.median(r["bandwidth_loo_mape"] for r in rows),
        })

    coverage_rows = [
        {"provider": p, "gpu": g, "pricing_type": t, "distinct_dates": len(ds), "first_date": min(ds), "last_date": max(ds)}
        for (p, g, t), ds in coverage.items()
    ]
    coverage_rows.sort(key=lambda r: (-r["distinct_dates"], r["provider"], r["gpu"], r["pricing_type"]))

    testable = [r for r in provider_results if r["matched_bucket_count"] >= int(contract.get("minimum_matched_buckets", 3))]
    classification = (
        "PROVIDER_CONDITIONED_HISTORICAL_TESTABLE"
        if testable
        else "NO_STRICT_PROVIDER_CONDITIONED_THREE_GEN_OVERLAP_IN_SCANNED_ARCHIVES"
    )
    return {
        "schema": SCHEMA,
        "research_only": True,
        "promotion_authority": False,
        "private_data_loaded": False,
        "source": {
            "dataset": "thatkavish/OpenComputePrices",
            "release_tag": "latest-data",
            "archive_receipts": archive_receipts,
            "fieldnames_seen": sorted(fieldnames_seen),
        },
        "matching": {
            "target_gpus": sorted(target),
            "memory_bandwidth_tb_s": bandwidth,
            "exact_bucket_keys": [
                "provider", "snapshot_date", "pricing_type", "region_or_geo_fallback",
                "gpu_variant_or_interconnect", "gpu_count", "tenancy", "commitment_period",
            ],
            "no_interpolation": True,
            "no_provider_blending": True,
        },
        "target_row_count": len(raw_rows),
        "strict_three_generation_bucket_count": len(matched),
        "provider_results": provider_results,
        "testable_provider_results": testable,
        "coverage_top": coverage_rows[:80],
        "matched_buckets": matched[:200],
        "classification": classification,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("contract", type=Path)
    ap.add_argument("output", type=Path)
    ns = ap.parse_args()
    contract = json.loads(ns.contract.read_text())
    result = evaluate(contract)
    ns.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("P10_PROVIDER_HISTORY_TERMINAL=" + json.dumps({
        "classification": result["classification"],
        "target_row_count": result["target_row_count"],
        "strict_three_generation_bucket_count": result["strict_three_generation_bucket_count"],
        "provider_results": result["provider_results"],
        "coverage_top": result["coverage_top"][:20],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
