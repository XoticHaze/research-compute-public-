#!/usr/bin/env python3
"""First frozen month-end pseudo-futures forecast discriminator for compute economics.

Public data only. Builds an equal-provider on-demand monthly rental index from
SHA-pinned OpenComputePrices archives and evaluates genuinely forward forecasts.
No interpolation, no future information, no broker/runtime/promotion authority.
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

SCHEMA = "research_compute_public.p10_pseudo_futures_forecast.v1"


def fnum(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def inum(x: Any) -> int | None:
    try:
        v = int(float(x))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def gpu_name(x: str, allowed: set[str]) -> str | None:
    u = (x or "").upper().replace("NVIDIA", " ")
    for g in sorted(allowed, key=len, reverse=True):
        if g in u:
            return g
    return None


def gpu_price(r: dict[str, str]) -> float | None:
    p = fnum(r.get("price_per_gpu_hour"))
    if p is not None:
        return p
    total = fnum(r.get("price_per_hour"))
    n = inum(r.get("gpu_count"))
    return total / n if total is not None and n else None


def download(spec: dict[str, str], dst: Path) -> dict[str, Any]:
    h = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(spec["url"], timeout=180) as src, dst.open("wb") as out:
        while True:
            b = src.read(1024 * 1024)
            if not b:
                break
            h.update(b)
            out.write(b)
            size += len(b)
    got = h.hexdigest()
    if got != spec["sha256"]:
        raise RuntimeError(f"digest mismatch {got} != {spec['sha256']}")
    return {"url": spec["url"], "sha256": got, "bytes": size}


def month_ord(month: str) -> int:
    y, m = map(int, month.split("-"))
    return y * 12 + (m - 1)


def add_months(month: str, n: int) -> str:
    o = month_ord(month) + n
    return f"{o // 12:04d}-{o % 12 + 1:02d}"


def ols_log_slope(history: list[dict[str, Any]]) -> float | None:
    if len(history) < 2:
        return None
    xs = [float(month_ord(r["month"])) for r in history]
    ys = [math.log(float(r["price"])) for r in history]
    xm = statistics.fmean(xs)
    ym = statistics.fmean(ys)
    den = sum((x - xm) ** 2 for x in xs)
    if den <= 0:
        return None
    return sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / den


def metric(rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    vals = [r for r in rows if r.get(model) is not None]
    if not vals:
        return {"n": 0, "mae": None, "mape": None, "median_ape": None}
    abs_err = [abs(r[model] - r["realized"]) for r in vals]
    ape = [e / r["realized"] for e, r in zip(abs_err, vals)]
    return {
        "n": len(vals),
        "mae": statistics.fmean(abs_err),
        "mape": statistics.fmean(ape),
        "median_ape": statistics.median(ape),
    }


def rel_improvement(challenger: float | None, baseline: float | None) -> float | None:
    if challenger is None or baseline is None or baseline <= 0:
        return None
    return (baseline - challenger) / baseline


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("contract", type=Path)
    ap.add_argument("output", type=Path)
    ns = ap.parse_args()
    c = json.loads(ns.contract.read_text())

    targets = list(c["target_generations"])
    pool = list(c["cross_generation_pool"])
    allowed = set(pool)
    bw = {k: float(v) for k, v in c["memory_bandwidth_tb_s"].items()}
    pricing_type = c["pricing_type"]
    receipts = []
    provider_daily_values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    seen: set[tuple[str, str, str, float]] = set()
    source_rows = 0

    with tempfile.TemporaryDirectory() as td:
        for idx, spec in enumerate(c["archives"]):
            path = Path(td) / f"archive_{idx}.csv.gz"
            receipts.append(download(spec, path))
            with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    if (r.get("pricing_type") or "").strip().lower() != pricing_type:
                        continue
                    g = gpu_name(r.get("gpu_name", ""), allowed)
                    if g is None:
                        continue
                    provider = (r.get("provider") or r.get("source") or "").strip().lower()
                    date = (r.get("snapshot_date") or "").strip()
                    price = gpu_price(r)
                    if not provider or not date or price is None:
                        continue
                    source_rows += 1
                    ident = (provider, date, g, round(price, 10))
                    if ident in seen:
                        continue
                    seen.add(ident)
                    provider_daily_values[(provider, date, g)].append(price)

    # One observation per provider/date/generation, then equal-provider generation index.
    generation_daily_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    provider_counts: dict[tuple[str, str], int] = defaultdict(int)
    for (provider, date, g), vals in provider_daily_values.items():
        generation_daily_values[(date, g)].append(statistics.median(vals))
        provider_counts[(date, g)] += 1

    daily = []
    for (date, g), vals in generation_daily_values.items():
        daily.append({
            "date": date,
            "month": date[:7],
            "generation": g,
            "price": statistics.median(vals),
            "provider_count": provider_counts[(date, g)],
        })
    daily.sort(key=lambda r: (r["generation"], r["date"]))

    # Last available observation of each calendar month, no interpolation.
    monthly_by_gen: dict[str, dict[str, dict[str, Any]]] = {g: {} for g in pool}
    for r in daily:
        g = r["generation"]
        prev = monthly_by_gen[g].get(r["month"])
        if prev is None or r["date"] > prev["date"]:
            monthly_by_gen[g][r["month"]] = r

    coverage = {}
    for g in pool:
        rows = sorted(monthly_by_gen[g].values(), key=lambda r: r["month"])
        coverage[g] = {
            "monthly_count": len(rows),
            "first_month": rows[0]["month"] if rows else None,
            "last_month": rows[-1]["month"] if rows else None,
            "first_date": rows[0]["date"] if rows else None,
            "last_date": rows[-1]["date"] if rows else None,
            "distinct_provider_count_range": [
                min((r["provider_count"] for r in rows), default=0),
                max((r["provider_count"] for r in rows), default=0),
            ],
        }

    forecasts: list[dict[str, Any]] = []
    min_prior = int(c["minimum_prior_months_for_depreciation"])
    min_cross = int(c["minimum_cross_generation_sources"])
    horizons = [int(h) for h in c["horizon_months"]]

    for target in targets:
        target_series = monthly_by_gen.get(target, {})
        target_months = sorted(target_series)
        for origin_month in target_months:
            origin = target_series[origin_month]
            history = [target_series[m] for m in target_months if month_ord(m) <= month_ord(origin_month)]
            dep_pred_base = None
            slope = None
            if len(history) >= min_prior:
                slope = ols_log_slope(history)
            # Strict cross-generation origin fair value, requiring >=2 other generations.
            other_levels = []
            other_sources = []
            for g in pool:
                if g == target:
                    continue
                rec = monthly_by_gen.get(g, {}).get(origin_month)
                if rec is not None:
                    other_levels.append(rec["price"] / bw[g])
                    other_sources.append(g)
            cross_level = statistics.median(other_levels) if len(other_levels) >= min_cross else None

            for h in horizons:
                realized_month = add_months(origin_month, h)
                realized_rec = target_series.get(realized_month)
                if realized_rec is None:
                    continue
                rw = origin["price"]
                dep = None
                if slope is not None:
                    dep = origin["price"] * math.exp(min(0.0, slope) * h)
                cross = cross_level * bw[target] if cross_level is not None else None
                forecasts.append({
                    "generation": target,
                    "horizon_months": h,
                    "origin_month": origin_month,
                    "origin_date": origin["date"],
                    "origin_price": origin["price"],
                    "realized_month": realized_month,
                    "realized_date": realized_rec["date"],
                    "realized": realized_rec["price"],
                    "changed_outcome": realized_rec["price"] != origin["price"],
                    "random_walk": rw,
                    "depreciation": dep,
                    "bandwidth_cross_generation": cross,
                    "depreciation_log_slope_per_month": slope,
                    "cross_generation_sources": other_sources if cross is not None else [],
                    "origin_provider_count": origin["provider_count"],
                    "realized_provider_count": realized_rec["provider_count"],
                })

    models = ["random_walk", "depreciation", "bandwidth_cross_generation"]
    minimum_origins = int(c["minimum_origins_for_supported_result"])
    mat = float(c["material_improvement_fraction"])
    results = []
    supported_wins: dict[str, list[int]] = {g: [] for g in targets}

    for g in targets:
        for h in horizons:
            subset = [r for r in forecasts if r["generation"] == g and r["horizon_months"] == h]
            changed = [r for r in subset if r["changed_outcome"]]
            all_metrics = {m: metric(subset, m) for m in models}
            changed_metrics = {m: metric(changed, m) for m in models}
            ch = changed_metrics["bandwidth_cross_generation"]["mape"]
            rw = changed_metrics["random_walk"]["mape"]
            dep = changed_metrics["depreciation"]["mape"]
            improve_rw = rel_improvement(ch, rw)
            improve_dep = rel_improvement(ch, dep)
            supported = (
                changed_metrics["bandwidth_cross_generation"]["n"] >= minimum_origins
                and changed_metrics["random_walk"]["n"] >= minimum_origins
                and changed_metrics["depreciation"]["n"] >= minimum_origins
            )
            passes = bool(
                supported
                and improve_rw is not None and improve_rw >= mat
                and improve_dep is not None and improve_dep >= mat
            )
            if passes:
                supported_wins[g].append(h)
            results.append({
                "generation": g,
                "horizon_months": h,
                "origin_count": len(subset),
                "changed_origin_count": len(changed),
                "all_outcomes": all_metrics,
                "changed_outcomes": changed_metrics,
                "challenger_relative_improvement_vs_random_walk": improve_rw,
                "challenger_relative_improvement_vs_depreciation": improve_dep,
                "supported": supported,
                "passes_advancement_gate": passes,
            })

    req_h = int(c["advancement_gate"]["required_supported_horizons_per_generation"])
    generation_gate = {g: len(supported_wins[g]) >= req_h for g in targets}
    if all(generation_gate.values()):
        classification = "MODELABLE_CANDIDATE_FIRST_FORWARD_GATE_PASS"
    elif any(generation_gate.values()):
        classification = "FORWARD_SIGNAL_NARROW_GENERATION_ONLY"
    else:
        any_supported = any(r["supported"] for r in results)
        classification = "FORWARD_CHALLENGER_FAILS_BASELINES" if any_supported else "INSUFFICIENT_FORWARD_HISTORY_FOR_FROZEN_GATE"

    # Compact changed-outcome examples help diagnose stale-quote effects without changing the gate.
    examples = [r for r in forecasts if r["changed_outcome"] and r["bandwidth_cross_generation"] is not None]
    examples.sort(key=lambda r: (r["generation"], r["horizon_months"], r["origin_month"]))

    result = {
        "schema": SCHEMA,
        "research_only": True,
        "promotion_authority": False,
        "private_data_loaded": False,
        "source": {"dataset": c["dataset"], "archive_receipts": receipts},
        "index_policy": c["index_policy"],
        "forecast_policy": c["forecast_policy"],
        "counts": {
            "source_target_rows_before_exact_dedup": source_rows,
            "exact_dedup_rows": len(seen),
            "provider_daily_series": len(provider_daily_values),
            "generation_daily_rows": len(daily),
            "forecast_rows": len(forecasts),
        },
        "coverage": coverage,
        "results": results,
        "supported_winning_horizons": supported_wins,
        "generation_gate": generation_gate,
        "classification": classification,
        "changed_outcome_examples": examples[:120],
        "parent_gate_note": "A first-pass label is only a candidate. Parent #128 still requires evidence across more than one generation/time segment and should not be promoted from sparse horizons or stale outcomes.",
    }
    ns.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    compact = {
        "classification": classification,
        "counts": result["counts"],
        "coverage": coverage,
        "supported_winning_horizons": supported_wins,
        "generation_gate": generation_gate,
        "results": [
            {
                "generation": r["generation"],
                "horizon_months": r["horizon_months"],
                "origin_count": r["origin_count"],
                "changed_origin_count": r["changed_origin_count"],
                "supported": r["supported"],
                "passes": r["passes_advancement_gate"],
                "rw_changed_mape": r["changed_outcomes"]["random_walk"]["mape"],
                "dep_changed_mape": r["changed_outcomes"]["depreciation"]["mape"],
                "bw_changed_mape": r["changed_outcomes"]["bandwidth_cross_generation"]["mape"],
                "improve_rw": r["challenger_relative_improvement_vs_random_walk"],
                "improve_dep": r["challenger_relative_improvement_vs_depreciation"],
            }
            for r in results
        ],
    }
    print("P10_PSEUDO_FUTURES_TERMINAL=" + json.dumps(compact, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
