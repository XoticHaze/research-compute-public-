from __future__ import annotations

"""Target-specific path-head test for the SHA-pinned causal ALFRED snapshot cache.

Control is the exact PR31/PR34 19-feature representation and fixed shallow HGB.
Challenger adds only the six cycle features frozen before any equity outcome. Both arms
run on identical matched rows. No external semiconductor holdout is loaded.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import research.semiconductor_path_head_predictability_20260905 as ph
import research.validate_semiconductor_alfred_information_snapshot_cache_20260906 as cache_validator

base = ph.base
OUT = Path("semiconductor_alfred_information_snapshot_path_head_20260906.json")
CACHE = Path(__file__).with_name("semiconductor_alfred_information_snapshot_cache_20260906.json")
CACHE_SHA256 = "__PIN_AFTER_MATERIALIZATION__"
CYCLE = [
    "semi_ip_change_1m", "semi_ip_change_3m", "semi_ip_change_12m",
    "hitek_capacity_utilization", "hitek_capacity_utilization_change_3m",
    "hitek_capacity_utilization_change_12m",
]


def canonical_sha(path: Path) -> str:
    doc = json.loads(path.read_text())
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def cache_matrix(cal: pd.DatetimeIndex):
    doc = cache_validator.validate(CACHE)
    actual = canonical_sha(CACHE)
    if CACHE_SHA256.startswith("__"):
        raise RuntimeError("cache SHA pin not materialized")
    if actual != CACHE_SHA256:
        raise RuntimeError(f"cache SHA mismatch actual={actual} expected={CACHE_SHA256}")
    rows = doc["rows"]
    available = [pd.Timestamp(r["available_from"], tz="UTC") for r in rows]
    matrix = np.full((len(cal), len(CYCLE)), np.nan, float)
    j = -1
    for i, ts in enumerate(cal):
        while j + 1 < len(rows) and available[j + 1].date() <= ts.date():
            j += 1
        if j >= 0:
            matrix[i, :] = [float(rows[j][f]) for f in CYCLE]
    return pd.DataFrame(matrix, columns=CYCLE), actual


def aggregate_metric(pred, truth, baseline, fold_metrics):
    out = ph.metric(np.asarray(pred), np.asarray(truth), np.asarray(baseline))
    out["positive_spearman_folds"] = sum(m["spearman"] is not None and m["spearman"] > 0 for m in fold_metrics)
    out["mae_better_folds"] = sum(m["mae_improvement_vs_median"] > 0 for m in fold_metrics)
    return out


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
    cyc, cache_sha = cache_matrix(cal)
    for f in CYCLE:
        frame[f] = frame["signal_i"].map(cyc[f])
    rows_before = len(frame)
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=CYCLE).copy()
    if frame.empty:
        raise RuntimeError("no matched cycle rows")

    fold_results = []
    truth_all = {t: [] for t in ph.TARGETS}
    baseline_all = {t: [] for t in ph.TARGETS}
    control_all = {t: [] for t in ph.TARGETS}
    challenger_all = {t: [] for t in ph.TARGETS}
    challenger_features = [*base.FULL, *CYCLE]

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
            cm = ph.model(); cm.fit(train[base.FULL].to_numpy(float), train[target].to_numpy(float))
            cp = cm.predict(test[base.FULL].to_numpy(float))
            hm = ph.model(); hm.fit(train[challenger_features].to_numpy(float), train[target].to_numpy(float))
            hp = hm.predict(test[challenger_features].to_numpy(float))
            cmet = ph.metric(cp, truth, baseline); hmet = ph.metric(hp, truth, baseline)
            fr[target] = {
                "control": cmet, "challenger": hmet,
                "spearman_delta": None if cmet["spearman"] is None or hmet["spearman"] is None else float(hmet["spearman"] - cmet["spearman"]),
                "mae_delta": float(hmet["mae"] - cmet["mae"]),
            }
            truth_all[target].extend(truth.tolist()); baseline_all[target].extend(baseline.tolist())
            control_all[target].extend(cp.tolist()); challenger_all[target].extend(hp.tolist())
        fold_results.append(fr)

    comparisons = {}; passing = []
    for target in ph.TARGETS:
        cfold = [r[target]["control"] for r in fold_results]
        hfold = [r[target]["challenger"] for r in fold_results]
        control = aggregate_metric(control_all[target], truth_all[target], baseline_all[target], cfold)
        challenger = aggregate_metric(challenger_all[target], truth_all[target], baseline_all[target], hfold)
        sp_folds = sum(c["spearman"] is not None and h["spearman"] is not None and h["spearman"] > c["spearman"] for c, h in zip(cfold, hfold))
        mae_folds = sum(h["mae"] < c["mae"] for c, h in zip(cfold, hfold))
        robust = bool(
            control["spearman"] is not None and challenger["spearman"] is not None
            and challenger["spearman"] > control["spearman"]
            and challenger["mae"] < control["mae"]
            and challenger["mae_improvement_vs_median"] > 0
            and challenger["positive_spearman_folds"] >= 3
            and challenger["mae_better_folds"] >= 3
            and sp_folds >= 3 and mae_folds >= 3
        )
        comparisons[target] = {
            "control": control, "plus_cycle_snapshots": challenger,
            "spearman_delta": None if control["spearman"] is None or challenger["spearman"] is None else float(challenger["spearman"] - control["spearman"]),
            "mae_delta": float(challenger["mae"] - control["mae"]),
            "spearman_improvement_folds_vs_control": int(sp_folds),
            "mae_improvement_folds_vs_control": int(mae_folds),
            "robust_information_increment": robust,
        }
        if robust:
            passing.append(target)

    out = {
        "schema": "public_compute.semiconductor_alfred_information_snapshot_path_head.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_preflight_pr": 44,
        "cache_materialization_pr": 47,
        "cache_sha256": cache_sha,
        "development_universe": list(base.TRAIN),
        "external_panels_loaded": False,
        "cycle_features": CYCLE,
        "rows_before_cycle_match": int(rows_before), "matched_rows": int(len(frame)),
        "matched_first_signal": cal[int(frame.signal_i.min())].isoformat(),
        "matched_last_signal": cal[int(frame.signal_i.max())].isoformat(),
        "common_cutoff": cutoff.isoformat(), "common_calendar_rows": len(cal),
        "learner": "exact fixed shallow HistGradientBoostingRegressor from PR31/PR34; no sweep",
        "folds": fold_results, "comparisons": comparisons, "passing_targets": passing,
        "decision": "CYCLE_INFORMATION_ADDS_PATH_HEAD_VALUE" if passing else "CYCLE_INFORMATION_NOT_JUSTIFIED_FOR_PATH_HEADS",
        "policy_or_trading_utility_defined": False,
        "next_boundary": "only robust target-specific increments may enter a separately frozen head-specialized architecture; no admission/ranking/duration authority",
        "research_only": True, "promotion_authority": False, "runtime_mutation": False,
        "broker_action": False, "live_trading_change": False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print("SEMICONDUCTOR_ALFRED_INFORMATION_SNAPSHOT_PATH_HEAD=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
