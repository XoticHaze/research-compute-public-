from __future__ import annotations

"""Target-specific path-head information test for the frozen first-print cycle cache.

Control is the exact PR31/PR34 19-feature representation and exact fixed shallow HGB.
Challenger adds only the six features frozen before the cache/model outcome. Control and
challenger are evaluated on identical rows. No external semiconductor holdout is loaded.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import research.semiconductor_path_head_predictability_20260905 as ph
import research.validate_semiconductor_alfred_first_print_cache_20260906 as cache_validator

base = ph.base
OUT = Path("semiconductor_alfred_cycle_path_head_20260906.json")
CACHE = Path(__file__).with_name("semiconductor_alfred_first_print_cache_20260906.json")
CACHE_SHA256 = "__PIN_AFTER_MATERIALIZATION__"
CYCLE = [
    "semi_ip_change_1m",
    "semi_ip_change_3m",
    "semi_ip_change_12m",
    "hitek_capacity_utilization",
    "hitek_capacity_utilization_change_3m",
    "hitek_capacity_utilization_change_12m",
]


def canonical_file_sha(path: Path) -> str:
    doc = json.loads(path.read_text())
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cycle_frame(cal: pd.DatetimeIndex):
    doc = cache_validator.validate(CACHE)
    actual_sha = canonical_file_sha(CACHE)
    if CACHE_SHA256.startswith("__"):
        raise RuntimeError("cache SHA pin not materialized")
    if actual_sha != CACHE_SHA256:
        raise RuntimeError(f"cache SHA mismatch actual={actual_sha} expected={CACHE_SHA256}")
    rows = doc["rows"]
    available = [pd.Timestamp(r["available_from"], tz="UTC") for r in rows]
    matrix = np.full((len(cal), len(CYCLE)), np.nan, float)
    j = -1
    for i, ts in enumerate(cal):
        while j + 1 < len(rows) and available[j + 1].date() <= ts.date():
            j += 1
        if j >= 0:
            matrix[i, :] = [float(rows[j][f]) for f in CYCLE]
    return pd.DataFrame(matrix, columns=CYCLE), actual_sha


def add_fold_counts(aggregate, fold_metrics):
    aggregate["positive_spearman_folds"] = sum(
        (m["spearman"] is not None and m["spearman"] > 0) for m in fold_metrics
    )
    aggregate["mae_better_folds"] = sum(m["mae_improvement_vs_median"] > 0 for m in fold_metrics)
    return aggregate


def main():
    symbols = (*base.TRAIN, *base.CONTEXT)
    raw = {s: base.load(s) for s in symbols}
    cutoff = min(d.iloc[-1].timestamp for d in raw.values())
    sets = [set(d.loc[d.timestamp <= cutoff, "timestamp"]) for d in raw.values()]
    cal = pd.DatetimeIndex(sorted(set.intersection(*sets)))
    if len(cal) < 1500:
        raise RuntimeError(f"insufficient common calendar={len(cal)}")
    prices = {s: raw[s].set_index("timestamp").price.reindex(cal) for s in raw}
    if any(v.isna().any() for v in prices.values()):
        raise RuntimeError("missing common-calendar price")

    old = base.FRESH
    base.FRESH = ()
    try:
        data = base.engineer(prices, cal)
    finally:
        base.FRESH = old
    folds = base.folds(len(cal))
    frame = ph.build_rows(data, prices, cal, folds)
    cyc, cache_sha = cycle_frame(cal)
    for feature in CYCLE:
        frame[feature] = frame["signal_i"].map(cyc[feature])
    before = len(frame)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=CYCLE).copy()
    matched_first_signal = cal[int(frame.signal_i.min())].isoformat() if len(frame) else None
    matched_last_signal = cal[int(frame.signal_i.max())].isoformat() if len(frame) else None

    fold_results = []
    all_truth = {t: [] for t in ph.TARGETS}
    all_base = {t: [] for t in ph.TARGETS}
    all_control = {t: [] for t in ph.TARGETS}
    all_challenger = {t: [] for t in ph.TARGETS}

    for fold in range(2, 7):
        start, _ = folds[fold - 1]
        purge = ph.DELAY + ph.HOLD
        train = frame[frame.signal_i < start - purge].copy()
        test = frame[frame.fold == fold].copy()
        if len(train) < 1000 or len(test) < 100:
            raise RuntimeError(f"fold {fold}: matched support train={len(train)} test={len(test)}")
        fr = {"fold": fold, "train_rows": int(len(train)), "test_rows": int(len(test))}
        for target in ph.TARGETS:
            truth = test[target].to_numpy(float)
            med = float(np.median(train[target].to_numpy(float)))
            baseline = np.full(len(test), med, float)

            control_model = ph.model()
            control_model.fit(train[base.FULL].to_numpy(float), train[target].to_numpy(float))
            control_pred = control_model.predict(test[base.FULL].to_numpy(float))

            challenger_features = [*base.FULL, *CYCLE]
            challenger_model = ph.model()
            challenger_model.fit(train[challenger_features].to_numpy(float), train[target].to_numpy(float))
            challenger_pred = challenger_model.predict(test[challenger_features].to_numpy(float))

            control_metric = ph.metric(control_pred, truth, baseline)
            challenger_metric = ph.metric(challenger_pred, truth, baseline)
            fr[target] = {
                "control": control_metric,
                "challenger": challenger_metric,
                "spearman_delta": None
                if control_metric["spearman"] is None or challenger_metric["spearman"] is None
                else float(challenger_metric["spearman"] - control_metric["spearman"]),
                "mae_delta": float(challenger_metric["mae"] - control_metric["mae"]),
            }
            all_truth[target].extend(truth.tolist())
            all_base[target].extend(baseline.tolist())
            all_control[target].extend(control_pred.tolist())
            all_challenger[target].extend(challenger_pred.tolist())
        fold_results.append(fr)

    comparisons = {}
    passing = []
    for target in ph.TARGETS:
        fold_control = [r[target]["control"] for r in fold_results]
        fold_challenger = [r[target]["challenger"] for r in fold_results]
        control = add_fold_counts(
            ph.metric(np.asarray(all_control[target]), np.asarray(all_truth[target]), np.asarray(all_base[target])),
            fold_control,
        )
        challenger = add_fold_counts(
            ph.metric(np.asarray(all_challenger[target]), np.asarray(all_truth[target]), np.asarray(all_base[target])),
            fold_challenger,
        )
        sp_improve = sum(
            c["spearman"] is not None
            and h["spearman"] is not None
            and h["spearman"] > c["spearman"]
            for c, h in zip(fold_control, fold_challenger)
        )
        mae_improve = sum(h["mae"] < c["mae"] for c, h in zip(fold_control, fold_challenger))
        robust = bool(
            control["spearman"] is not None
            and challenger["spearman"] is not None
            and challenger["spearman"] > control["spearman"]
            and challenger["mae"] < control["mae"]
            and challenger["mae_improvement_vs_median"] > 0
            and challenger["positive_spearman_folds"] >= 3
            and challenger["mae_better_folds"] >= 3
            and sp_improve >= 3
            and mae_improve >= 3
        )
        comparisons[target] = {
            "control": control,
            "plus_first_print_cycle": challenger,
            "spearman_delta": None
            if control["spearman"] is None or challenger["spearman"] is None
            else float(challenger["spearman"] - control["spearman"]),
            "mae_delta": float(challenger["mae"] - control["mae"]),
            "spearman_improvement_folds_vs_control": int(sp_improve),
            "mae_improvement_folds_vs_control": int(mae_improve),
            "robust_information_increment": robust,
        }
        if robust:
            passing.append(target)

    out = {
        "schema": "public_compute.semiconductor_alfred_cycle_path_head.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_preflight_pr": 44,
        "cache_materialization_pr": 45,
        "cache_sha256": cache_sha,
        "development_universe": list(base.TRAIN),
        "external_panels_loaded": False,
        "cycle_features": CYCLE,
        "matched_rows": int(len(frame)),
        "rows_before_cycle_match": int(before),
        "matched_first_signal": matched_first_signal,
        "matched_last_signal": matched_last_signal,
        "common_cutoff": cutoff.isoformat(),
        "common_calendar_rows": len(cal),
        "learner": "exact fixed shallow HistGradientBoostingRegressor from PR31/PR34; no sweep",
        "folds": fold_results,
        "comparisons": comparisons,
        "passing_targets": passing,
        "decision": "CYCLE_INFORMATION_ADDS_PATH_HEAD_VALUE" if passing else "CYCLE_INFORMATION_NOT_JUSTIFIED_FOR_PATH_HEADS",
        "policy_or_trading_utility_defined": False,
        "next_boundary": "only robust target-specific increments may enter a separately frozen head-specialized architecture; this result does not alter admission/ranking/duration",
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("SEMICONDUCTOR_ALFRED_CYCLE_PATH_HEAD=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
