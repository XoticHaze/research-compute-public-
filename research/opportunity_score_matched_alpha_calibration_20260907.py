from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import opportunity_cross_family_stagea_capacity_allocator_20260907 as development
import opportunity_prior_alpha_blend_disjoint_family_confirmation_20260907 as disjoint

OUT = Path("opportunity_score_matched_alpha_calibration_20260907.json")
CAPACITY = 3
EVAL_FOLDS = (4, 5, 6)
RIDGE_ALPHA = 10.0


def feature_row(prediction_bps: float, family: str, families: tuple[str, ...]) -> list[float]:
    one_hot = [1.0 if family == f else 0.0 for f in families]
    interactions = [prediction_bps * value for value in one_hot]
    return [prediction_bps, *one_hot, *interactions]


def fit_calibrator(records: list[dict], before_fold: int, target_field: str, families: tuple[str, ...]):
    train = [r for r in records if int(r["fold"]) < before_fold]
    if len(train) < 100:
        raise RuntimeError(f"fold={before_fold}: insufficient calibration rows={len(train)}")
    x = np.asarray(
        [feature_row(float(r["prediction_bps"]), str(r["family"]), families) for r in train],
        dtype=float,
    )
    y = np.asarray([float(r[target_field]) for r in train], dtype=float)
    model = Pipeline([
        ("scale", StandardScaler()),
        ("ridge", Ridge(alpha=RIDGE_ALPHA)),
    ])
    model.fit(x, y)
    fitted = model.predict(x)
    corr = float(np.corrcoef(fitted, y)[0, 1]) if len(y) > 1 and np.std(fitted) > 0 and np.std(y) > 0 else None
    return model, {
        "train_rows": len(train),
        "train_target_mean_bps": float(np.mean(y)),
        "train_target_std_bps": float(np.std(y)),
        "train_fitted_target_correlation": corr,
        "train_folds": sorted({int(r["fold"]) for r in train}),
        "family_rows": {f: sum(str(r["family"]) == f for r in train) for f in families},
    }


def calibrated_scores(model, candidates: list[dict], families: tuple[str, ...]) -> list[tuple[float, dict]]:
    if not candidates:
        return []
    x = np.asarray(
        [feature_row(float(r["prediction_bps"]), str(r["family"]), families) for r in candidates],
        dtype=float,
    )
    scores = model.predict(x)
    return sorted(
        [(float(score), r) for score, r in zip(scores, candidates)],
        key=lambda item: (-item[0], -float(item[1]["prediction_bps"]), str(item[1]["family"]), str(item[1]["symbol"])),
    )


def simulate_calibrated(records: list[dict], fold: int, model, families: tuple[str, ...]) -> dict:
    candidates = [r for r in records if int(r["fold"]) == fold]
    grouped: dict[int, list[dict]] = defaultdict(list)
    for record in candidates:
        grouped[int(record["entry_i"])].append(record)

    slots = [
        {"stock": 1.0 / CAPACITY, "etf": 1.0 / CAPACITY, "qqq": 1.0 / CAPACITY, "record": None, "exit_i": -1}
        for _ in range(CAPACITY)
    ]
    accepted: list[tuple[float, dict]] = []

    def realize(index: int):
        for slot in slots:
            record = slot["record"]
            if record is not None and int(slot["exit_i"]) <= index:
                slot["stock"] *= 1.0 + float(record["stock_net"])
                slot["etf"] *= 1.0 + float(record["etf_net"])
                slot["qqq"] *= 1.0 + float(record["qqq_net"])
                slot["record"] = None
                slot["exit_i"] = -1

    for entry_i in sorted(grouped):
        realize(entry_i)
        free = [slot for slot in slots if slot["record"] is None]
        if not free:
            continue
        active_symbols = {str(slot["record"]["symbol"]) for slot in slots if slot["record"] is not None}
        for score, record in calibrated_scores(model, grouped[entry_i], families):
            if not free:
                break
            symbol = str(record["symbol"])
            if symbol in active_symbols:
                continue
            slot = free.pop(0)
            slot["record"] = record
            slot["exit_i"] = int(record["exit_i"])
            active_symbols.add(symbol)
            accepted.append((score, record))
    realize(10**9)

    stock_wealth = float(sum(slot["stock"] for slot in slots))
    etf_wealth = float(sum(slot["etf"] for slot in slots))
    qqq_wealth = float(sum(slot["qqq"] for slot in slots))
    family_counts: dict[str, int] = defaultdict(int)
    for _, record in accepted:
        family_counts[str(record["family"])] += 1
    return {
        "stock_return": stock_wealth - 1.0,
        "matched_etf_return": etf_wealth - 1.0,
        "qqq_return": qqq_wealth - 1.0,
        "stock_minus_matched_etf_return": stock_wealth - etf_wealth,
        "stock_minus_qqq_return": stock_wealth - qqq_wealth,
        "accepted_trades": len(accepted),
        "family_trade_counts": dict(sorted(family_counts.items())),
        "mean_calibrated_alpha_score_bps": float(np.mean([score for score, _ in accepted])) if accepted else None,
        "mean_realized_matched_alpha_bps": float(np.mean([
            float(record.get("stock_minus_etf_bps", record.get("matched_excess_bps"))) for _, record in accepted
        ])) if accepted else None,
    }


def aggregate(rows: list[dict]) -> dict:
    stock = float(np.prod([1.0 + float(r["stock_return"]) for r in rows]) - 1.0)
    etf = float(np.prod([1.0 + float(r["matched_etf_return"]) for r in rows]) - 1.0)
    qqq = float(np.prod([1.0 + float(r["qqq_return"]) for r in rows]) - 1.0)
    family_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        for family, count in row.get("family_trade_counts", {}).items():
            family_counts[family] += int(count)
    return {
        "compound_stock_return": stock,
        "compound_matched_etf_return": etf,
        "compound_qqq_return": qqq,
        "compound_stock_minus_matched_etf": stock - etf,
        "compound_stock_minus_qqq": stock - qqq,
        "accepted_trades": int(sum(int(r["accepted_trades"]) for r in rows)),
        "fold_stock_returns": [float(r["stock_return"]) for r in rows],
        "fold_matched_excess": [float(r["stock_minus_matched_etf_return"]) for r in rows],
        "family_trade_counts": dict(sorted(family_counts.items())),
    }


def surface_gate(raw_rows: list[dict], calibrated_rows: list[dict]) -> dict:
    raw = aggregate(raw_rows)
    calibrated = aggregate(calibrated_rows)
    fold_wins = sum(c["stock_return"] > r["stock_return"] for r, c in zip(raw_rows, calibrated_rows))
    positive_excess_folds = sum(c["stock_minus_matched_etf_return"] > 0 for c in calibrated_rows)
    supported = bool(
        calibrated["compound_stock_return"] > raw["compound_stock_return"]
        and calibrated["compound_stock_minus_matched_etf"] > 0
        and calibrated["compound_stock_minus_matched_etf"] > raw["compound_stock_minus_matched_etf"]
        and fold_wins >= 2
        and positive_excess_folds >= 2
        and calibrated["accepted_trades"] >= 0.70 * raw["accepted_trades"]
    )
    return {
        "raw_prediction": raw,
        "matched_alpha_calibrated": calibrated,
        "fold_wins_vs_raw": fold_wins,
        "positive_matched_etf_excess_folds": positive_excess_folds,
        "decision": "CALIBRATION_SUPPORTED_ON_SURFACE" if supported else "CALIBRATION_NOT_SUPPORTED_ON_SURFACE",
    }


def evaluate_development(mod, contract: dict) -> dict:
    calendar, _, families_spec, records = development.build_records(mod, contract)
    families = tuple(sorted(families_spec))
    raw_rows = []
    calibrated_rows = []
    fold_detail = []
    for fold in EVAL_FOLDS:
        model, diagnostics = fit_calibrator(records, fold, "stock_minus_etf_bps", families)
        raw = development.simulate(records, fold, "global_raw_prediction", {})
        calibrated = simulate_calibrated(records, fold, model, families)
        raw_rows.append(raw)
        calibrated_rows.append(calibrated)
        fold_detail.append({"fold": fold, "calibrator": diagnostics, "raw_prediction": raw, "matched_alpha_calibrated": calibrated})
    gate = surface_gate(raw_rows, calibrated_rows)
    return {
        "surface": "homebuilders_plus_biotech",
        "families": families_spec,
        "selection_calendar_rows": len(calendar),
        "candidate_primary_states": len(records),
        "folds": fold_detail,
        "gate": gate,
    }


def evaluate_disjoint(mod) -> dict:
    calendar, records = disjoint.build_records(mod)
    families = tuple(sorted(disjoint.FAMILIES))
    raw_rows = []
    calibrated_rows = []
    fold_detail = []
    for fold in EVAL_FOLDS:
        model, diagnostics = fit_calibrator(records, fold, "matched_excess_bps", families)
        raw = disjoint.simulate(records, fold, "raw_prediction", {})
        calibrated = simulate_calibrated(records, fold, model, families)
        raw_rows.append(raw)
        calibrated_rows.append(calibrated)
        fold_detail.append({"fold": fold, "calibrator": diagnostics, "raw_prediction": raw, "matched_alpha_calibrated": calibrated})
    gate = surface_gate(raw_rows, calibrated_rows)
    return {
        "surface": "consumer_staples_metals_reits_pharma",
        "families": disjoint.FAMILIES,
        "selection_calendar_rows": len(calendar),
        "candidate_primary_states": len(records),
        "folds": fold_detail,
        "gate": gate,
    }


def main():
    mod = development.load_adapter()
    contract = json.loads(Path(".campaign/stagea_contract.json").read_text(encoding="utf-8"))
    surfaces = [evaluate_development(mod, contract), evaluate_disjoint(mod)]
    both = all(surface["gate"]["decision"] == "CALIBRATION_SUPPORTED_ON_SURFACE" for surface in surfaces)
    receipt = {
        "schema": "public_research.opportunity_score_matched_alpha_calibration.v1",
        "research_only": True,
        "objective": "Test whether the existing causal Stage-A setup score can be converted into expected matched-industry excess more reliably than ranking raw predicted stock return.",
        "architecture": {
            "stage_a_candidate_semantics": "unchanged accepted Stage-A primary states",
            "calibration_target": "realized stock return after 25 bp stock cost minus matched industry ETF gross return",
            "calibration_features": [
                "current Stage-A prediction_bps",
                "family one-hot identity",
                "prediction_bps x family interactions",
            ],
            "ticker_identity_feature": False,
            "ticker_historical_alpha_feature": False,
            "calibrator": f"StandardScaler + Ridge(alpha={RIDGE_ALPHA})",
            "calibration_training": "completed earlier folds only",
            "capacity": CAPACITY,
            "parameter_search": False,
        },
        "evaluation_folds": list(EVAL_FOLDS),
        "surfaces": surfaces,
        "decision": "MATCHED_ALPHA_SCORE_CALIBRATION_SUPPORTED" if both else "MATCHED_ALPHA_SCORE_CALIBRATION_NOT_SUPPORTED",
        "next_boundary": (
            "If both surfaces support calibration, freeze this exact calibrator and test it on a new unseen family batch before any product promotion. "
            "If either surface fails, stop transforming historical matched-alpha memory/score calibration and rotate ranking improvement into a genuinely independent information representation."
        ),
        "external_holdouts_loaded": False,
        "threshold_search": False,
        "hyperparameter_search": False,
        "allocation_runtime_authority": False,
        "strategy_spec_mutation": False,
        "promotion_authority": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("OPPORTUNITY_SCORE_MATCHED_ALPHA_CALIBRATION=" + json.dumps(receipt, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
