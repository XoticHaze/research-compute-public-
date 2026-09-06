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

SCHEMA = "research_compute_public.p10_provider_breadth_forward.v1"


def fnum(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def inum(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def normalize_gpu(value: str, allowed: set[str]) -> str | None:
    text = (value or "").upper().replace("NVIDIA", " ")
    for generation in sorted(allowed, key=len, reverse=True):
        if generation in text:
            return generation
    return None


def per_gpu_price(row: dict[str, str]) -> float | None:
    direct = fnum(row.get("price_per_gpu_hour"))
    if direct is not None:
        return direct
    total = fnum(row.get("price_per_hour"))
    count = inum(row.get("gpu_count"))
    return total / count if total is not None and count else None


def download(spec: dict[str, str], destination: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(spec["url"], headers={"User-Agent": "p10-research-consumer/1"})
    with urllib.request.urlopen(request, timeout=300) as source, destination.open("wb") as output:
        while True:
            block = source.read(4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
            output.write(block)
            size += len(block)
    observed = digest.hexdigest()
    if observed != spec["sha256"]:
        raise RuntimeError(f"digest mismatch {observed} != {spec['sha256']}")
    return {"url": spec["url"], "sha256": observed, "bytes": size}


def month_ordinal(month: str) -> int:
    year, mon = map(int, month.split("-"))
    return year * 12 + mon - 1


def add_months(month: str, count: int) -> str:
    ordinal = month_ordinal(month) + count
    return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"


def previous_month(month: str) -> str:
    return add_months(month, -1)


def median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return 0.0
    median = statistics.median(values)
    return statistics.median([abs(value - median) for value in values])


def consume_rows(
    rows: Iterable[dict[str, str]],
    allowed_generations: set[str],
    allowed_pricing_types: set[str],
    provider_date_values: dict[tuple[str, str, str, str], list[float]],
    seen: set[tuple[str, str, str, str, float]],
) -> tuple[int, int]:
    scanned = 0
    admitted = 0
    for row in rows:
        scanned += 1
        pricing_type = (row.get("pricing_type") or "").strip().lower()
        if pricing_type not in allowed_pricing_types:
            continue
        generation = normalize_gpu(row.get("gpu_name", ""), allowed_generations)
        if generation is None:
            continue
        provider = (row.get("provider") or row.get("source") or "").strip().lower()
        date = (row.get("snapshot_date") or "").strip()[:10]
        price = per_gpu_price(row)
        if not provider or len(date) != 10 or price is None:
            continue
        identity = (provider, date, generation, pricing_type, round(price, 10))
        if identity in seen:
            continue
        seen.add(identity)
        provider_date_values[(provider, date, generation, pricing_type)].append(price)
        admitted += 1
    return scanned, admitted


def write_panel(rows: list[dict[str, Any]], path: Path) -> str:
    fields = ["provider", "month", "generation", "pricing_type", "observation_date", "price_per_gpu_hour"]
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.DictWriter(text, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow({field: row[field] for field in fields})
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def fit_ols_1d(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator <= 1e-15:
        return None
    beta = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    alpha = y_mean - beta * x_mean
    return alpha, beta


def ols_log_slope(history: list[dict[str, Any]]) -> float | None:
    if len(history) < 2:
        return None
    xs = [float(month_ordinal(row["month"])) for row in history]
    ys = [math.log(float(row["price"])) for row in history]
    fit = fit_ols_1d(xs, ys)
    return fit[1] if fit else None


def metric(rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    valid = [row for row in rows if row.get(model) is not None]
    if not valid:
        return {"n": 0, "mae": None, "mape": None, "median_ape": None}
    abs_errors = [abs(row[model] - row["realized"]) for row in valid]
    apes = [error / row["realized"] for error, row in zip(abs_errors, valid)]
    return {
        "n": len(valid),
        "mae": statistics.fmean(abs_errors),
        "mape": statistics.fmean(apes),
        "median_ape": statistics.median(apes),
    }


def relative_improvement(challenger: float | None, baseline: float | None) -> float | None:
    if challenger is None or baseline is None or baseline <= 0:
        return None
    return (baseline - challenger) / baseline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=Path)
    parser.add_argument("panel_output", type=Path)
    parser.add_argument("result_output", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())

    pool = list(contract["training_pool_generations"])
    targets = list(contract["target_generations"])
    allowed_generations = set(pool)
    allowed_pricing_types = set(contract["pricing_types"])
    provider_date_values: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    seen: set[tuple[str, str, str, str, float]] = set()
    receipts: list[dict[str, Any]] = []
    source_rows_scanned = 0
    source_rows_admitted = 0

    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        for index, spec in enumerate(contract["historical_archives"]):
            archive_path = temp / f"historical_{index}.csv.gz"
            receipts.append(download(spec, archive_path))
            with gzip.open(archive_path, "rt", encoding="utf-8", newline="") as handle:
                scanned, admitted = consume_rows(
                    csv.DictReader(handle), allowed_generations, allowed_pricing_types,
                    provider_date_values, seen,
                )
                source_rows_scanned += scanned
                source_rows_admitted += admitted

        active_spec = contract["active_archive"]
        active_path = temp / "data.tar.gz"
        receipts.append(download(active_spec, active_path))
        target_basename = active_spec["member_basename"]
        matched = 0
        with tarfile.open(active_path, "r|gz") as archive:
            for member in archive:
                if not member.isfile() or Path(member.name).name != target_basename:
                    continue
                matched += 1
                raw = archive.extractfile(member)
                if raw is None:
                    raise RuntimeError(f"unable to extract {member.name}")
                with raw, io.TextIOWrapper(raw, encoding="utf-8", newline="") as text:
                    scanned, admitted = consume_rows(
                        csv.DictReader(text), allowed_generations, allowed_pricing_types,
                        provider_date_values, seen,
                    )
                    source_rows_scanned += scanned
                    source_rows_admitted += admitted
                break
        if matched != 1:
            raise RuntimeError(f"expected one {target_basename} in active archive, found {matched}")

    provider_date_price = {
        key: statistics.median(values)
        for key, values in provider_date_values.items()
    }

    # Provider-month panel: last exact observed date for each provider/generation/pricing type in each month.
    provider_month: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for (provider, date, generation, pricing_type), price in provider_date_price.items():
        month = date[:7]
        key = (provider, month, generation, pricing_type)
        current = provider_month.get(key)
        if current is None or date > current["observation_date"]:
            provider_month[key] = {
                "provider": provider,
                "month": month,
                "generation": generation,
                "pricing_type": pricing_type,
                "observation_date": date,
                "price_per_gpu_hour": price,
            }
    panel_rows = sorted(provider_month.values(), key=lambda row: (
        row["month"], row["generation"], row["provider"], row["pricing_type"], row["observation_date"]
    ))
    panel_sha256 = write_panel(panel_rows, args.panel_output)

    # Exact same-provider/same-date reliability basis, then last exact paired basis per provider-month.
    exact_basis: dict[tuple[str, str, str], float] = {}
    base_keys = {(provider, date, generation) for provider, date, generation, _ in provider_date_price}
    for provider, date, generation in base_keys:
        on_demand = provider_date_price.get((provider, date, generation, "on_demand"))
        spot = provider_date_price.get((provider, date, generation, "spot"))
        if on_demand is not None and spot is not None and on_demand > 0:
            exact_basis[(provider, date, generation)] = 1.0 - spot / on_demand

    provider_month_basis: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (provider, date, generation), discount in exact_basis.items():
        month = date[:7]
        key = (provider, month, generation)
        current = provider_month_basis.get(key)
        if current is None or date > current["date"]:
            provider_month_basis[key] = {"date": date, "discount": discount}

    # Generation-month on-demand index from equal provider weights.
    generation_month_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in panel_rows:
        if row["pricing_type"] == "on_demand":
            generation_month_values[(row["generation"], row["month"])].append(row["price_per_gpu_hour"])
    generation_month_index: dict[str, dict[str, dict[str, Any]]] = {generation: {} for generation in pool}
    for (generation, month), values in generation_month_values.items():
        dates = [
            row["observation_date"] for row in panel_rows
            if row["generation"] == generation and row["month"] == month and row["pricing_type"] == "on_demand"
        ]
        generation_month_index[generation][month] = {
            "month": month,
            "date": max(dates),
            "price": statistics.median(values),
            "provider_count": len(values),
        }

    min_common = int(contract["minimum_common_on_demand_providers"])
    min_basis = int(contract["minimum_exact_spot_basis_providers"])
    states: dict[str, dict[str, dict[str, Any]]] = {generation: {} for generation in pool}
    for generation in pool:
        months = sorted(generation_month_index[generation], key=month_ordinal)
        for month in months:
            prior = previous_month(month)
            current_by_provider = {
                row["provider"]: row["price_per_gpu_hour"]
                for row in panel_rows
                if row["generation"] == generation and row["month"] == month and row["pricing_type"] == "on_demand"
            }
            prior_by_provider = {
                row["provider"]: row["price_per_gpu_hour"]
                for row in panel_rows
                if row["generation"] == generation and row["month"] == prior and row["pricing_type"] == "on_demand"
            }
            common = sorted(set(current_by_provider) & set(prior_by_provider))
            changes = [math.log(current_by_provider[provider] / prior_by_provider[provider]) for provider in common]
            breadth = None
            dispersion = None
            if len(common) >= min_common:
                signs = [1.0 if change > 0 else -1.0 if change < 0 else 0.0 for change in changes]
                breadth = statistics.fmean(signs)
                dispersion = median_absolute_deviation(changes)

            basis_values = [
                provider_month_basis[(provider, month, generation)]["discount"]
                for provider in {key[0] for key in provider_month_basis if key[1] == month and key[2] == generation}
            ]
            reliability = statistics.median(basis_values) if len(basis_values) >= min_basis else None
            states[generation][month] = {
                "breadth": breadth,
                "paired_provider_count": len(common),
                "change_dispersion": dispersion,
                "spot_discount_median": reliability,
                "spot_basis_provider_count": len(basis_values),
            }

    horizons = [int(value) for value in contract["horizon_months"]]
    min_training = int(contract["minimum_training_states"])
    min_prior = int(contract["minimum_prior_months_for_depreciation"])
    forecasts: list[dict[str, Any]] = []

    for target in targets:
        target_months = sorted(generation_month_index[target], key=month_ordinal)
        for origin_month in target_months:
            origin_state = states[target].get(origin_month)
            if not origin_state or origin_state["breadth"] is None:
                continue
            origin = generation_month_index[target][origin_month]
            history = [
                dict(generation_month_index[target][month], month=month)
                for month in target_months if month_ordinal(month) <= month_ordinal(origin_month)
            ]
            depreciation_slope = ols_log_slope(history) if len(history) >= min_prior else None
            for horizon in horizons:
                realized_month = add_months(origin_month, horizon)
                realized = generation_month_index[target].get(realized_month)
                if realized is None:
                    continue

                same_generation_candidates: list[tuple[float, float]] = []
                transport_candidates: list[tuple[float, float]] = []
                same_generation_reliability: list[tuple[float, float]] = []
                transport_reliability: list[tuple[float, float]] = []
                for candidate_generation in pool:
                    for candidate_month, candidate_state in states[candidate_generation].items():
                        candidate_origin = generation_month_index[candidate_generation].get(candidate_month)
                        candidate_realized_month = add_months(candidate_month, horizon)
                        candidate_realized = generation_month_index[candidate_generation].get(candidate_realized_month)
                        if candidate_origin is None or candidate_realized is None:
                            continue
                        if candidate_realized["date"] > origin["date"]:
                            continue
                        forward_return = math.log(candidate_realized["price"] / candidate_origin["price"])
                        if candidate_state["breadth"] is not None:
                            pair = (candidate_state["breadth"], forward_return)
                            if candidate_generation == target:
                                same_generation_candidates.append(pair)
                            else:
                                transport_candidates.append(pair)
                        if candidate_state["spot_discount_median"] is not None:
                            pair = (candidate_state["spot_discount_median"], forward_return)
                            if candidate_generation == target:
                                same_generation_reliability.append(pair)
                            else:
                                transport_reliability.append(pair)

                breadth_candidates = same_generation_candidates if target == "H100" else [
                    pair for generation in ["H100", "H200"]
                    for pair in [
                        (states[generation][candidate_month]["breadth"], math.log(
                            generation_month_index[generation][add_months(candidate_month, horizon)]["price"] /
                            generation_month_index[generation][candidate_month]["price"]
                        ))
                        for candidate_month in states[generation]
                        if states[generation][candidate_month]["breadth"] is not None
                        and add_months(candidate_month, horizon) in generation_month_index[generation]
                        and generation_month_index[generation][add_months(candidate_month, horizon)]["date"] <= origin["date"]
                    ]
                ]
                reliability_candidates = same_generation_reliability if target == "H100" else [
                    pair for generation in ["H100", "H200"]
                    for pair in [
                        (states[generation][candidate_month]["spot_discount_median"], math.log(
                            generation_month_index[generation][add_months(candidate_month, horizon)]["price"] /
                            generation_month_index[generation][candidate_month]["price"]
                        ))
                        for candidate_month in states[generation]
                        if states[generation][candidate_month]["spot_discount_median"] is not None
                        and add_months(candidate_month, horizon) in generation_month_index[generation]
                        and generation_month_index[generation][add_months(candidate_month, horizon)]["date"] <= origin["date"]
                    ]
                ]

                breadth_fit = fit_ols_1d(
                    [pair[0] for pair in breadth_candidates], [pair[1] for pair in breadth_candidates]
                ) if len(breadth_candidates) >= min_training else None
                reliability_fit = fit_ols_1d(
                    [pair[0] for pair in reliability_candidates], [pair[1] for pair in reliability_candidates]
                ) if len(reliability_candidates) >= min_training and origin_state["spot_discount_median"] is not None else None

                breadth_prediction = None
                if breadth_fit is not None:
                    alpha, beta = breadth_fit
                    breadth_prediction = origin["price"] * math.exp(alpha + beta * origin_state["breadth"])
                reliability_prediction = None
                if reliability_fit is not None:
                    alpha, beta = reliability_fit
                    reliability_prediction = origin["price"] * math.exp(alpha + beta * origin_state["spot_discount_median"])
                depreciation = (
                    origin["price"] * math.exp(min(0.0, depreciation_slope) * horizon)
                    if depreciation_slope is not None else None
                )
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
                    "breadth": origin_state["breadth"],
                    "paired_provider_count": origin_state["paired_provider_count"],
                    "spot_discount_median": origin_state["spot_discount_median"],
                    "spot_basis_provider_count": origin_state["spot_basis_provider_count"],
                    "random_walk": origin["price"],
                    "depreciation": depreciation,
                    "breadth_ols": breadth_prediction if target == "H100" else None,
                    "breadth_ols_transport": breadth_prediction if target == "B200" else None,
                    "reliability_ols_secondary": reliability_prediction,
                    "breadth_training_states": len(breadth_candidates),
                    "reliability_training_states": len(reliability_candidates),
                })

    min_changed = int(contract["minimum_changed_origins_for_supported_result"])
    material = float(contract["material_improvement_fraction"])
    results: list[dict[str, Any]] = []
    wins: dict[str, list[int]] = {generation: [] for generation in targets}
    reliability_results: list[dict[str, Any]] = []

    for generation in targets:
        gate_model = contract["gate_models"][generation]
        for horizon in horizons:
            subset = [row for row in forecasts if row["generation"] == generation and row["horizon_months"] == horizon]
            changed = [row for row in subset if row["changed_outcome"]]
            common_gate_rows = [row for row in changed if row.get(gate_model) is not None]
            gate_metrics = {
                gate_model: metric(common_gate_rows, gate_model),
                "random_walk": metric(common_gate_rows, "random_walk"),
                "depreciation": metric(common_gate_rows, "depreciation"),
            }
            challenger = gate_metrics[gate_model]["mape"]
            rw = gate_metrics["random_walk"]["mape"]
            dep = gate_metrics["depreciation"]["mape"]
            improve_rw = relative_improvement(challenger, rw)
            improve_dep = relative_improvement(challenger, dep)
            supported = (
                gate_metrics[gate_model]["n"] >= min_changed
                and gate_metrics["random_walk"]["n"] >= min_changed
                and gate_metrics["depreciation"]["n"] >= min_changed
            )
            passes = bool(
                supported and improve_rw is not None and improve_rw >= material
                and improve_dep is not None and improve_dep >= material
            )
            if passes:
                wins[generation].append(horizon)
            training_counts = [row["breadth_training_states"] for row in common_gate_rows]
            results.append({
                "generation": generation,
                "horizon_months": horizon,
                "gate_model": gate_model,
                "origin_count": len(subset),
                "changed_origin_count": len(changed),
                "common_gate_changed_count": len(common_gate_rows),
                "metrics_on_common_gate_rows": gate_metrics,
                "improve_rw": improve_rw,
                "improve_depreciation": improve_dep,
                "supported": supported,
                "passes": passes,
                "breadth_training_state_count_range": [min(training_counts), max(training_counts)] if training_counts else [0, 0],
            })

            common_reliability_rows = [row for row in changed if row.get("reliability_ols_secondary") is not None]
            reliability_metrics = {
                "reliability_ols_secondary": metric(common_reliability_rows, "reliability_ols_secondary"),
                "random_walk": metric(common_reliability_rows, "random_walk"),
                "depreciation": metric(common_reliability_rows, "depreciation"),
            }
            reliability_results.append({
                "generation": generation,
                "horizon_months": horizon,
                "common_changed_count": len(common_reliability_rows),
                "metrics_on_common_rows": reliability_metrics,
                "improve_rw": relative_improvement(reliability_metrics["reliability_ols_secondary"]["mape"], reliability_metrics["random_walk"]["mape"]),
                "improve_depreciation": relative_improvement(reliability_metrics["reliability_ols_secondary"]["mape"], reliability_metrics["depreciation"]["mape"]),
                "supported": reliability_metrics["reliability_ols_secondary"]["n"] >= min_changed,
                "secondary_only": True,
            })

    required = int(contract["advancement_gate"]["required_supported_winning_horizons_per_generation"])
    generation_gate = {generation: len(wins[generation]) >= required for generation in targets}
    if all(generation_gate.values()):
        classification = "MODELABLE_CANDIDATE_PROVIDER_BREADTH_PASS"
    elif any(generation_gate.values()):
        classification = "PROVIDER_BREADTH_NARROW_GENERATION_ONLY"
    elif any(row["supported"] for row in results):
        classification = "PROVIDER_BREADTH_SUPPORTED_BUT_FAILS_BASELINES"
    else:
        classification = "INSUFFICIENT_PROVIDER_BREADTH_SUPPORT"

    coverage = {}
    for generation in pool:
        months = sorted(generation_month_index[generation], key=month_ordinal)
        breadth_months = [month for month in months if states[generation].get(month, {}).get("breadth") is not None]
        reliability_months = [month for month in months if states[generation].get(month, {}).get("spot_discount_median") is not None]
        coverage[generation] = {
            "monthly_index_count": len(months),
            "breadth_state_month_count": len(breadth_months),
            "reliability_state_month_count": len(reliability_months),
            "first_month": months[0] if months else None,
            "last_month": months[-1] if months else None,
            "breadth_first_month": breadth_months[0] if breadth_months else None,
            "breadth_last_month": breadth_months[-1] if breadth_months else None,
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
        "cache": {
            "provider_month_panel_path": args.panel_output.name,
            "provider_month_panel_sha256": panel_sha256,
            "provider_month_panel_rows": len(panel_rows),
            "format": "gzip_csv",
            "columns": contract["cache_policy"]["panel_columns"],
        },
        "counts": {
            "source_rows_scanned": source_rows_scanned,
            "source_rows_admitted_after_exact_dedup": source_rows_admitted,
            "unique_provider_date_generation_pricing_price": len(seen),
            "provider_date_series": len(provider_date_values),
            "provider_month_panel_rows": len(panel_rows),
            "exact_spot_basis_provider_dates": len(exact_basis),
            "forecast_rows": len(forecasts),
        },
        "coverage": coverage,
        "primary_breadth_results": results,
        "secondary_reliability_results": reliability_results,
        "supported_winning_horizons": wins,
        "generation_gate": generation_gate,
        "state_policy": contract["state_policy"],
        "forecast_policy": contract["forecast_policy"],
        "decision_rule": contract["decision_rule"],
        "parent_gate_note": "Provider repricing breadth is a distinct causal feature family from curve-state/bandwidth. Reliability basis is secondary-only in this frozen pass and cannot rescue the primary gate.",
    }
    args.result_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    compact = {
        "classification": classification,
        "cache": result["cache"],
        "counts": result["counts"],
        "coverage": coverage,
        "wins": wins,
        "gate": generation_gate,
        "primary": [
            {
                "generation": row["generation"],
                "horizon_months": row["horizon_months"],
                "gate_model": row["gate_model"],
                "changed": row["changed_origin_count"],
                "common_gate_changed": row["common_gate_changed_count"],
                "gate_mape": row["metrics_on_common_gate_rows"][row["gate_model"]]["mape"],
                "rw_mape": row["metrics_on_common_gate_rows"]["random_walk"]["mape"],
                "dep_mape": row["metrics_on_common_gate_rows"]["depreciation"]["mape"],
                "improve_rw": row["improve_rw"],
                "improve_dep": row["improve_depreciation"],
                "supported": row["supported"],
                "passes": row["passes"],
                "training_range": row["breadth_training_state_count_range"],
            }
            for row in results
        ],
        "reliability_secondary": reliability_results,
    }
    print("P10_PROVIDER_BREADTH_TERMINAL=" + json.dumps(compact, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
