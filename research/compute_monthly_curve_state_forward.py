#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
import tarfile
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "research_compute_public.p10_monthly_curve_state_forward.v1"


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
    count = inum(r.get("gpu_count"))
    return total / count if total is not None and count else None


def download(spec: dict[str, str], dst: Path) -> dict[str, Any]:
    h = hashlib.sha256()
    size = 0
    req = urllib.request.Request(spec["url"], headers={"User-Agent": "p10-research-consumer/1"})
    with urllib.request.urlopen(req, timeout=300) as src, dst.open("wb") as out:
        while True:
            block = src.read(4 * 1024 * 1024)
            if not block:
                break
            h.update(block)
            out.write(block)
            size += len(block)
    got = h.hexdigest()
    if got != spec["sha256"]:
        raise RuntimeError(f"digest mismatch {got} != {spec['sha256']}")
    return {"url": spec["url"], "sha256": got, "bytes": size}


def month_ord(month: str) -> int:
    year, mon = map(int, month.split("-"))
    return year * 12 + mon - 1


def add_months(month: str, n: int) -> str:
    value = month_ord(month) + n
    return f"{value // 12:04d}-{value % 12 + 1:02d}"


def linear_slope(values: list[float]) -> float:
    n = len(values)
    xs = [float(i) for i in range(n)]
    xm = statistics.fmean(xs)
    ym = statistics.fmean(values)
    den = sum((x - xm) ** 2 for x in xs)
    return 0.0 if den <= 0 else sum((x - xm) * (y - ym) for x, y in zip(xs, values)) / den


def quadratic_acceleration(values: list[float]) -> float:
    n = len(values)
    xs = [i - (n - 1) / 2 for i in range(n)]
    x2 = [x * x for x in xs]
    s0 = float(n)
    s2 = sum(x2)
    s4 = sum(v * v for v in x2)
    sy = sum(values)
    sy2 = sum(y * q for y, q in zip(values, x2))
    den = s0 * s4 - s2 * s2
    a = 0.0 if den == 0 else (s0 * sy2 - s2 * sy) / den
    return 2.0 * a


def one_scale(logs: list[float], prices: list[float], pos: int, window: int) -> tuple[list[float], float, float, float]:
    seg = logs[pos - window:pos + 1]
    rets = [seg[i] - seg[i - 1] for i in range(1, len(seg))]
    slope = linear_slope(seg)
    accel = quadratic_acceleration(seg)
    vol = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    travelled = sum(abs(x) for x in rets)
    efficiency = abs(sum(rets)) / travelled if travelled else 0.0
    distance_high = prices[pos] / max(prices[pos - window:pos + 1]) - 1.0

    prev_seg = logs[pos - window - 1:pos] if pos - 1 >= window else seg
    prev_rets = [prev_seg[i] - prev_seg[i - 1] for i in range(1, len(prev_seg))]
    prev_slope = linear_slope(prev_seg)
    prev_vol = statistics.pstdev(prev_rets) if len(prev_rets) > 1 else 0.0
    slope_delta = slope - prev_slope
    vol_delta = vol - prev_vol
    return [seg[-1] - seg[0], slope, accel, vol, efficiency, distance_high, slope_delta, vol_delta], slope, accel, vol


def state_at(prices: list[float], pos: int, windows: list[int]) -> list[float] | None:
    if pos < max(windows):
        return None
    logs = [math.log(p) for p in prices]
    features: list[float] = []
    slopes: list[float] = []
    accels: list[float] = []
    vols: list[float] = []
    slope_deltas: list[float] = []
    vol_deltas: list[float] = []
    for window in windows:
        scale_features, slope, accel, vol = one_scale(logs, prices, pos, window)
        features.extend(scale_features)
        slopes.append(slope)
        accels.append(accel)
        vols.append(vol)
        slope_deltas.append(scale_features[-2])
        vol_deltas.append(scale_features[-1])

    signs = [1.0 if x > 0 else -1.0 if x < 0 else 0.0 for x in slopes]
    direction = statistics.fmean(signs)
    features.extend([
        direction,
        abs(direction),
        slopes[0] - slopes[-1],
        accels[0] - accels[-1],
    ])
    transition_components: list[float] = []
    for sd, vd, vol in zip(slope_deltas, vol_deltas, vols):
        denom = max(abs(vol), 1e-6)
        transition_components.extend([sd / denom, vd / denom])
    features.append(math.sqrt(statistics.fmean([x * x for x in transition_components])))
    return features if all(math.isfinite(x) for x in features) else None


def median_mad(values: list[float]) -> tuple[float, float]:
    median = statistics.median(values)
    mad = statistics.median([abs(x - median) for x in values])
    return median, mad


def knn_predict(origin: list[float], candidates: list[dict[str, Any]], k: int, origin_price: float) -> tuple[float | None, float | None]:
    if len(candidates) < k:
        return None, None
    dimensions = len(origin)
    scales: list[float] = []
    for j in range(dimensions):
        _, mad = median_mad([row["feature"][j] for row in candidates])
        scales.append(mad)
    scored: list[tuple[float, float]] = []
    for row in candidates:
        parts = [((origin[j] - row["feature"][j]) / scales[j]) ** 2 for j in range(dimensions) if scales[j] > 1e-12]
        distance = math.sqrt(statistics.fmean(parts)) if parts else 0.0
        scored.append((distance, row["forward_log_return"]))
    scored.sort(key=lambda item: item[0])
    chosen = scored[:k]
    prediction = origin_price * math.exp(statistics.median([value for _, value in chosen]))
    return prediction, statistics.median([distance for distance, _ in chosen])


def ols_log_slope(history: list[dict[str, Any]]) -> float | None:
    if len(history) < 2:
        return None
    xs = [float(month_ord(row["month"])) for row in history]
    ys = [math.log(float(row["price"])) for row in history]
    xm = statistics.fmean(xs)
    ym = statistics.fmean(ys)
    den = sum((x - xm) ** 2 for x in xs)
    return None if den <= 0 else sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / den


def metric(rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    values = [row for row in rows if row.get(model) is not None]
    if not values:
        return {"n": 0, "mae": None, "mape": None, "median_ape": None}
    abs_errors = [abs(row[model] - row["realized"]) for row in values]
    apes = [error / row["realized"] for error, row in zip(abs_errors, values)]
    return {
        "n": len(values),
        "mae": statistics.fmean(abs_errors),
        "mape": statistics.fmean(apes),
        "median_ape": statistics.median(apes),
    }


def relative_improvement(challenger: float | None, baseline: float | None) -> float | None:
    if challenger is None or baseline is None or baseline <= 0:
        return None
    return (baseline - challenger) / baseline


def consume_rows(rows: Iterable[dict[str, str]], allowed: set[str], pricing_type: str, provider_daily_values: dict, seen: set) -> tuple[int, int]:
    scanned = 0
    admitted = 0
    for row in rows:
        scanned += 1
        if (row.get("pricing_type") or "").strip().lower() != pricing_type:
            continue
        generation = gpu_name(row.get("gpu_name", ""), allowed)
        if generation is None:
            continue
        provider = (row.get("provider") or row.get("source") or "").strip().lower()
        date = (row.get("snapshot_date") or "").strip()
        price = gpu_price(row)
        if not provider or len(date) < 10 or price is None:
            continue
        ident = (provider, date[:10], generation, round(price, 10))
        if ident in seen:
            continue
        seen.add(ident)
        provider_daily_values[(provider, date[:10], generation)].append(price)
        admitted += 1
    return scanned, admitted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())

    pool = list(contract["state_pool_generations"])
    targets = list(contract["target_generations"])
    allowed = set(pool)
    pricing_type = contract["pricing_type"]
    provider_daily_values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    seen: set[tuple[str, str, str, float]] = set()
    receipts: list[dict[str, Any]] = []
    source_rows_scanned = 0
    source_rows_admitted = 0

    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        for index, spec in enumerate(contract["historical_archives"]):
            path = temp / f"historical_{index}.csv.gz"
            receipts.append(download(spec, path))
            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                scanned, admitted = consume_rows(csv.DictReader(handle), allowed, pricing_type, provider_daily_values, seen)
                source_rows_scanned += scanned
                source_rows_admitted += admitted

        active_spec = contract["active_archive"]
        tar_path = temp / "data.tar.gz"
        receipts.append(download(active_spec, tar_path))
        with tarfile.open(tar_path, "r:gz") as archive:
            basename = active_spec["member_basename"]
            matches = [member for member in archive.getmembers() if member.isfile() and Path(member.name).name == basename]
            if len(matches) != 1:
                raise RuntimeError(f"expected exactly one {basename} member, found {len(matches)}")
            raw = archive.extractfile(matches[0])
            if raw is None:
                raise RuntimeError(f"unable to extract {matches[0].name}")
            with raw, io.TextIOWrapper(raw, encoding="utf-8", newline="") as text:
                scanned, admitted = consume_rows(csv.DictReader(text), allowed, pricing_type, provider_daily_values, seen)
                source_rows_scanned += scanned
                source_rows_admitted += admitted

    generation_daily_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    provider_counts: dict[tuple[str, str], int] = defaultdict(int)
    for (provider, date, generation), values in provider_daily_values.items():
        generation_daily_values[(date, generation)].append(statistics.median(values))
        provider_counts[(date, generation)] += 1

    daily_by_generation: dict[str, list[dict[str, Any]]] = {generation: [] for generation in pool}
    for (date, generation), values in generation_daily_values.items():
        daily_by_generation[generation].append({
            "date": date,
            "month": date[:7],
            "price": statistics.median(values),
            "provider_count": provider_counts[(date, generation)],
        })
    for generation in pool:
        daily_by_generation[generation].sort(key=lambda row: row["date"])

    monthly: dict[str, dict[str, dict[str, Any]]] = {generation: {} for generation in pool}
    for generation, rows in daily_by_generation.items():
        for row in rows:
            current = monthly[generation].get(row["month"])
            if current is None or row["date"] > current["date"]:
                monthly[generation][row["month"]] = row

    windows = [int(value) for value in contract["curve_windows_months"]]
    states: dict[str, dict[str, list[float]]] = {generation: {} for generation in pool}
    for generation in pool:
        months = sorted(monthly[generation], key=month_ord)
        prices = [monthly[generation][month]["price"] for month in months]
        for pos, month in enumerate(months):
            feature = state_at(prices, pos, windows)
            if feature is not None:
                states[generation][month] = feature

    horizons = [int(value) for value in contract["horizon_months"]]
    k = int(contract["knn_k"])
    min_training = int(contract["minimum_training_states"])
    min_prior = int(contract["minimum_prior_months_for_depreciation"])
    forecasts: list[dict[str, Any]] = []

    for target in targets:
        target_months = sorted(monthly[target], key=month_ord)
        for origin_month in target_months:
            if origin_month not in states[target]:
                continue
            origin = monthly[target][origin_month]
            history = [dict(monthly[target][month], month=month) for month in target_months if month_ord(month) <= month_ord(origin_month)]
            slope = ols_log_slope(history) if len(history) >= min_prior else None
            for horizon in horizons:
                realized_month = add_months(origin_month, horizon)
                realized = monthly[target].get(realized_month)
                if realized is None:
                    continue
                own_candidates: list[dict[str, Any]] = []
                transport_candidates: list[dict[str, Any]] = []
                for candidate_generation in pool:
                    for candidate_month, feature in states[candidate_generation].items():
                        candidate_realized_month = add_months(candidate_month, horizon)
                        candidate_realized = monthly[candidate_generation].get(candidate_realized_month)
                        candidate_origin = monthly[candidate_generation].get(candidate_month)
                        if candidate_realized is None or candidate_origin is None:
                            continue
                        if candidate_realized["date"] > origin["date"]:
                            continue
                        candidate = {
                            "generation": candidate_generation,
                            "feature": feature,
                            "forward_log_return": math.log(candidate_realized["price"] / candidate_origin["price"]),
                        }
                        if candidate_generation == target:
                            own_candidates.append(candidate)
                        else:
                            transport_candidates.append(candidate)

                own_prediction, own_distance = (knn_predict(states[target][origin_month], own_candidates, k, origin["price"]) if len(own_candidates) >= min_training else (None, None))
                transport_prediction, transport_distance = (knn_predict(states[target][origin_month], transport_candidates, k, origin["price"]) if len(transport_candidates) >= min_training else (None, None))
                depreciation = origin["price"] * math.exp(min(0.0, slope) * horizon) if slope is not None else None
                forecasts.append({
                    "generation": target,
                    "horizon_months": horizon,
                    "origin_month": origin_month,
                    "origin_date": origin["date"],
                    "origin_price": origin["price"],
                    "realized_month": realized_month,
                    "realized_date": realized["date"],
                    "realized": realized["price"],
                    "changed_outcome": realized["price"] != origin["price"],
                    "random_walk": origin["price"],
                    "depreciation": depreciation,
                    "own_curve_knn": own_prediction,
                    "transport_curve_knn": transport_prediction,
                    "own_training_states": len(own_candidates),
                    "transport_training_states": len(transport_candidates),
                    "own_neighbor_distance_median": own_distance,
                    "transport_neighbor_distance_median": transport_distance,
                })

    models = ["random_walk", "depreciation", "own_curve_knn", "transport_curve_knn"]
    min_changed = int(contract["minimum_changed_origins_for_supported_result"])
    material = float(contract["material_improvement_fraction"])
    results: list[dict[str, Any]] = []
    wins: dict[str, list[int]] = {generation: [] for generation in targets}

    for generation in targets:
        gate_model = contract["gate_models"][generation]
        prefix = "own" if gate_model.startswith("own") else "transport"
        for horizon in horizons:
            subset = [row for row in forecasts if row["generation"] == generation and row["horizon_months"] == horizon]
            changed = [row for row in subset if row["changed_outcome"]]
            metrics = {model: metric(changed, model) for model in models}
            challenger = metrics[gate_model]["mape"]
            rw = metrics["random_walk"]["mape"]
            depreciation = metrics["depreciation"]["mape"]
            improve_rw = relative_improvement(challenger, rw)
            improve_depreciation = relative_improvement(challenger, depreciation)
            supported = (
                metrics[gate_model]["n"] >= min_changed
                and metrics["random_walk"]["n"] >= min_changed
                and metrics["depreciation"]["n"] >= min_changed
            )
            passes = bool(
                supported
                and improve_rw is not None and improve_rw >= material
                and improve_depreciation is not None and improve_depreciation >= material
            )
            if passes:
                wins[generation].append(horizon)
            distances = [row[f"{prefix}_neighbor_distance_median"] for row in changed if row.get(f"{prefix}_neighbor_distance_median") is not None]
            training_counts = [row[f"{prefix}_training_states"] for row in changed]
            results.append({
                "generation": generation,
                "horizon_months": horizon,
                "gate_model": gate_model,
                "origin_count": len(subset),
                "changed_origin_count": len(changed),
                "changed_metrics": metrics,
                "improve_rw": improve_rw,
                "improve_depreciation": improve_depreciation,
                "supported": supported,
                "passes": passes,
                "median_gate_neighbor_distance": statistics.median(distances) if distances else None,
                "gate_training_state_count_range": [min(training_counts), max(training_counts)] if training_counts else [0, 0],
            })

    required = int(contract["advancement_gate"]["required_supported_winning_horizons_per_generation"])
    generation_gate = {generation: len(wins[generation]) >= required for generation in targets}
    if all(generation_gate.values()):
        classification = "MODELABLE_CANDIDATE_MONTHLY_CURVE_STATE_PASS"
    elif any(generation_gate.values()):
        classification = "MONTHLY_CURVE_STATE_NARROW_GENERATION_ONLY"
    elif any(row["supported"] for row in results):
        classification = "MONTHLY_CURVE_STATE_SUPPORTED_BUT_FAILS_BASELINES"
    else:
        classification = "INSUFFICIENT_MONTHLY_CURVE_STATE_SUPPORT"

    coverage = {}
    for generation in pool:
        months = sorted(monthly[generation], key=month_ord)
        coverage[generation] = {
            "daily_count": len(daily_by_generation[generation]),
            "monthly_count": len(months),
            "state_month_count": len(states[generation]),
            "first_month": months[0] if months else None,
            "last_month": months[-1] if months else None,
            "first_date": daily_by_generation[generation][0]["date"] if daily_by_generation[generation] else None,
            "last_date": daily_by_generation[generation][-1]["date"] if daily_by_generation[generation] else None,
        }

    result = {
        "schema": SCHEMA,
        "research_only": True,
        "promotion_authority": False,
        "private_data_loaded": False,
        "classification": classification,
        "source": {
            "dataset": contract["dataset"],
            "release_tag": contract["release_tag"],
            "release_as_of": contract["active_archive"]["release_as_of"],
            "receipts": receipts,
        },
        "counts": {
            "source_rows_scanned": source_rows_scanned,
            "source_target_rows_admitted_after_dedup": source_rows_admitted,
            "unique_provider_date_generation_price": len(seen),
            "provider_daily_series": len(provider_daily_values),
            "forecast_rows": len(forecasts),
        },
        "coverage": coverage,
        "results": results,
        "supported_winning_horizons": wins,
        "generation_gate": generation_gate,
        "index_policy": contract["index_policy"],
        "curve_state_policy": contract["curve_state_policy"],
        "decision_rule": contract["decision_rule"],
        "parent_gate_note": "This is the single predeclared calendar-month adaptation after the observation-cadence falsification. Do not retune windows/support after seeing this outcome.",
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    compact = {
        "classification": classification,
        "counts": result["counts"],
        "coverage": coverage,
        "wins": wins,
        "gate": generation_gate,
        "results": [
            {
                "generation": row["generation"],
                "horizon_months": row["horizon_months"],
                "gate_model": row["gate_model"],
                "origin_count": row["origin_count"],
                "changed_origin_count": row["changed_origin_count"],
                "gate_n": row["changed_metrics"][row["gate_model"]]["n"],
                "gate_mape": row["changed_metrics"][row["gate_model"]]["mape"],
                "rw_mape": row["changed_metrics"]["random_walk"]["mape"],
                "dep_mape": row["changed_metrics"]["depreciation"]["mape"],
                "improve_rw": row["improve_rw"],
                "improve_dep": row["improve_depreciation"],
                "supported": row["supported"],
                "passes": row["passes"],
                "training_state_range": row["gate_training_state_count_range"],
            }
            for row in results
        ],
    }
    print("P10_MONTHLY_CURVE_STATE_TERMINAL=" + json.dumps(compact, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
