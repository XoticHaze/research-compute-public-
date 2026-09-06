from __future__ import annotations

"""First real consumer of the frozen semiconductor SEC fundamental cache.

The scientific contract is frozen in semiconductor_fundamental_consumer_contract_20260906.json.
This experiment keeps the exact PR31/PR34 learner, targets and chronology. It adds only five
predeclared filing-safe balance-sheet features and re-evaluates the 19-feature control on the
exact same rows. Duration facts are deliberately excluded.
"""

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import research.semiconductor_path_head_predictability_20260905 as ph

CACHE = Path("sec_hf_root_parquet_semiconductor_cache_20260906.json")
CONTRACT = Path("research/semiconductor_fundamental_consumer_contract_20260906.json")
OUT = Path("semiconductor_sec_balance_sheet_information_value_20260906.json")
FUND_FEATURES = [
    "inventory_to_assets",
    "cash_to_assets",
    "inventory_to_assets_change_vs_prior_annual_comparable",
    "cash_to_assets_change_vs_prior_annual_comparable",
    "balance_sheet_filing_age_days",
]
INSTANT_CATEGORIES = ("assets", "inventory", "cash")
EXPECTED_UNIVERSE = ("AMAT", "APH", "KLAC", "LRCX", "TXN", "NXPI", "ADI")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_date(value) -> date | None:
    if value in (None, "", "None", "NaT"):
        return None
    try:
        return pd.Timestamp(value).date()
    except Exception:
        return None


def parse_float(value):
    if value in (None, "", "None", "nan", "NaN"):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def accession_category_observations(rows):
    """Return one unambiguous latest-period observation per accession/category."""
    grouped = {}
    for row in rows:
        accn = str(row.get("accn") or "")
        filed = parse_date(row.get("filed"))
        period_end = parse_date(row.get("end"))
        value = parse_float(row.get("val_dec"))
        if not accn or filed is None or period_end is None or value is None:
            continue
        grouped.setdefault(accn, []).append((filed, period_end, value))

    out = {}
    ambiguous = 0
    for accn, raw in grouped.items():
        # Exact duplicate collapse first, as frozen by the consumer contract.
        exact = sorted(set(raw), key=lambda x: (x[1], x[0], x[2]))
        latest_end = max(x[1] for x in exact)
        latest = [x for x in exact if x[1] == latest_end]
        # Filing date should be accession-stable. Preserve the latest if duplicate rows disagree.
        latest_filed = max(x[0] for x in latest)
        values = sorted({x[2] for x in latest if x[0] == latest_filed})
        if len(values) != 1:
            ambiguous += 1
            continue
        out[accn] = {
            "filed": latest_filed,
            "period_end": latest_end,
            "value": values[0],
        }
    return out, ambiguous


def build_snapshots(symbol_payload):
    category_obs = {}
    ambiguous = {}
    for category in INSTANT_CATEGORIES:
        rows = symbol_payload["categories"][category]["rows"]
        category_obs[category], ambiguous[category] = accession_category_observations(rows)

    common = sorted(set.intersection(*(set(category_obs[c]) for c in INSTANT_CATEGORIES)))
    snapshots = []
    rejected_mismatch = 0
    for accn in common:
        a = category_obs["assets"][accn]
        i = category_obs["inventory"][accn]
        c = category_obs["cash"][accn]
        if not (a["filed"] == i["filed"] == c["filed"] and a["period_end"] == i["period_end"] == c["period_end"]):
            rejected_mismatch += 1
            continue
        assets = a["value"]
        if not np.isfinite(assets) or assets <= 0:
            continue
        snapshots.append(
            {
                "accn": accn,
                "filed": a["filed"],
                "period_end": a["period_end"],
                "inventory_to_assets": i["value"] / assets,
                "cash_to_assets": c["value"] / assets,
            }
        )

    snapshots.sort(key=lambda x: (x["filed"], x["period_end"], x["accn"]))
    for idx, current in enumerate(snapshots):
        candidates = []
        for prior in snapshots[:idx]:
            if prior["filed"] >= current["filed"]:
                continue
            days = (current["period_end"] - prior["period_end"]).days
            if 330 <= days <= 400:
                candidates.append(prior)
        prior = max(candidates, key=lambda x: (x["filed"], x["period_end"], x["accn"])) if candidates else None
        if prior is None:
            current["inventory_to_assets_change_vs_prior_annual_comparable"] = None
            current["cash_to_assets_change_vs_prior_annual_comparable"] = None
        else:
            current["inventory_to_assets_change_vs_prior_annual_comparable"] = (
                current["inventory_to_assets"] - prior["inventory_to_assets"]
            )
            current["cash_to_assets_change_vs_prior_annual_comparable"] = (
                current["cash_to_assets"] - prior["cash_to_assets"]
            )
    diagnostics = {
        "unambiguous_accessions_by_category": {k: len(v) for k, v in category_obs.items()},
        "ambiguous_accessions_by_category": ambiguous,
        "common_accessions": len(common),
        "same_period_snapshots": len(snapshots),
        "period_mismatch_rejections": rejected_mismatch,
        "snapshots_with_prior_annual_comparable": sum(
            s["inventory_to_assets_change_vs_prior_annual_comparable"] is not None for s in snapshots
        ),
    }
    return snapshots, diagnostics


def asof_features(snapshots, signal_date: date):
    eligible = [s for s in snapshots if s["filed"] <= signal_date]
    if not eligible:
        return None
    s = max(eligible, key=lambda x: (x["filed"], x["period_end"], x["accn"]))
    vals = [
        s["inventory_to_assets"],
        s["cash_to_assets"],
        s["inventory_to_assets_change_vs_prior_annual_comparable"],
        s["cash_to_assets_change_vs_prior_annual_comparable"],
        float((signal_date - s["filed"]).days),
    ]
    if not all(v is not None and np.isfinite(float(v)) for v in vals):
        return None
    return dict(zip(FUND_FEATURES, map(float, vals)))


def build_model_frame(cache):
    base = ph.base
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
    frame["signal_date"] = [cal[int(i)].date() for i in frame.signal_i]

    snapshots = {}
    snapshot_diagnostics = {}
    for symbol in base.TRAIN:
        snapshots[symbol], snapshot_diagnostics[symbol] = build_snapshots(cache["symbols"][symbol])

    fund_rows = []
    for row in frame[["symbol", "signal_i", "signal_date"]].itertuples(index=False):
        feats = asof_features(snapshots[row.symbol], row.signal_date)
        if feats is None:
            fund_rows.append({"symbol": row.symbol, "signal_i": row.signal_i, **{f: np.nan for f in FUND_FEATURES}})
        else:
            fund_rows.append({"symbol": row.symbol, "signal_i": row.signal_i, **feats})
    fund = pd.DataFrame(fund_rows)
    frame = frame.merge(fund, on=["symbol", "signal_i"], how="left", validate="one_to_one")
    return frame, folds, cutoff, len(cal), snapshot_diagnostics


def aggregate_metric(pred, truth, baseline):
    return ph.metric(np.asarray(pred, float), np.asarray(truth, float), np.asarray(baseline, float))


def evaluate_target(frame, folds, target):
    base = ph.base
    control_pred, challenger_pred, truths, baselines = [], [], [], []
    fold_results = []
    for fold in range(2, 7):
        start, _ = folds[fold - 1]
        purge = ph.DELAY + ph.HOLD
        train = frame[frame.signal_i < start - purge].copy()
        test = frame[frame.fold == fold].copy()
        finite_cols = [*base.FULL, *FUND_FEATURES, target]
        train = train.replace([np.inf, -np.inf], np.nan).dropna(subset=finite_cols)
        test = test.replace([np.inf, -np.inf], np.nan).dropna(subset=finite_cols)
        if len(train) < 1000 or len(test) < 100:
            raise RuntimeError(f"fold {fold} {target}: support train={len(train)} test={len(test)}")

        y_train = train[target].to_numpy(float)
        y_test = test[target].to_numpy(float)
        median = float(np.median(y_train))
        baseline = np.full(len(test), median, float)

        control = ph.model()
        control.fit(train[base.FULL].to_numpy(float), y_train)
        cp = control.predict(test[base.FULL].to_numpy(float))

        challenger_features = [*base.FULL, *FUND_FEATURES]
        challenger = ph.model()
        challenger.fit(train[challenger_features].to_numpy(float), y_train)
        chp = challenger.predict(test[challenger_features].to_numpy(float))

        cm = aggregate_metric(cp, y_test, baseline)
        hm = aggregate_metric(chp, y_test, baseline)
        fold_results.append(
            {
                "fold": fold,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "control": cm,
                "challenger": hm,
                "spearman_improvement": None if cm["spearman"] is None or hm["spearman"] is None else hm["spearman"] - cm["spearman"],
                "mae_improvement_vs_control": cm["mae"] - hm["mae"],
            }
        )
        control_pred.extend(np.asarray(cp, float).tolist())
        challenger_pred.extend(np.asarray(chp, float).tolist())
        truths.extend(y_test.tolist())
        baselines.extend(baseline.tolist())

    control_agg = aggregate_metric(control_pred, truths, baselines)
    challenger_agg = aggregate_metric(challenger_pred, truths, baselines)
    positive_spearman_folds = sum(
        int(r["challenger"]["spearman"] is not None and r["challenger"]["spearman"] > 0) for r in fold_results
    )
    baseline_mae_win_folds = sum(int(r["challenger"]["mae_improvement_vs_median"] > 0) for r in fold_results)
    spearman_improvement_folds = sum(int(r["spearman_improvement"] is not None and r["spearman_improvement"] > 0) for r in fold_results)
    mae_improvement_folds = sum(int(r["mae_improvement_vs_control"] > 0) for r in fold_results)
    passed = bool(
        challenger_agg["spearman"] is not None
        and control_agg["spearman"] is not None
        and challenger_agg["spearman"] > control_agg["spearman"]
        and challenger_agg["mae"] < control_agg["mae"]
        and challenger_agg["mae"] < challenger_agg["median_baseline_mae"]
        and positive_spearman_folds >= 3
        and baseline_mae_win_folds >= 3
        and spearman_improvement_folds >= 3
        and mae_improvement_folds >= 3
    )
    return {
        "control_aggregate": control_agg,
        "challenger_aggregate": challenger_agg,
        "folds": fold_results,
        "gate_counts": {
            "positive_spearman_folds": positive_spearman_folds,
            "baseline_mae_win_folds": baseline_mae_win_folds,
            "spearman_improvement_folds_vs_control": spearman_improvement_folds,
            "mae_improvement_folds_vs_control": mae_improvement_folds,
        },
        "decision": "EARN_SEC_BALANCE_SHEET_INFORMATION" if passed else "REJECT_SEC_BALANCE_SHEET_INFORMATION",
    }


def main():
    contract = load_json(CONTRACT)
    cache_bytes = CACHE.read_bytes()
    cache = json.loads(cache_bytes.decode("utf-8"))
    if tuple(cache.get("development_universe") or ()) != EXPECTED_UNIVERSE:
        raise RuntimeError(f"unexpected cache universe={cache.get('development_universe')}")
    if contract["challenger_information"]["features"] != FUND_FEATURES:
        raise RuntimeError("consumer feature list drifted from frozen contract")
    if tuple(contract["control"]["targets"]) != tuple(ph.TARGETS):
        raise RuntimeError("target contract drifted from exact PR31 path heads")

    frame, folds, cutoff, calendar_rows, snapshot_diagnostics = build_model_frame(cache)
    finite = frame[FUND_FEATURES].replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
    finite_by_symbol = {s: int((finite & (frame.symbol == s)).sum()) for s in ph.base.TRAIN}
    results = {target: evaluate_target(frame, folds, target) for target in ph.TARGETS}
    earned = [target for target, result in results.items() if result["decision"] == "EARN_SEC_BALANCE_SHEET_INFORMATION"]

    out = {
        "schema": "public_compute.semiconductor_sec_balance_sheet_information_value.v1",
        "source_cache": str(CACHE),
        "source_cache_sha256": hashlib.sha256(cache_bytes).hexdigest(),
        "source_dataset": cache.get("source_dataset"),
        "source_dataset_revision": cache.get("source_dataset_revision"),
        "consumer_contract": str(CONTRACT),
        "development_universe": list(ph.base.TRAIN),
        "common_cutoff": cutoff.isoformat(),
        "common_calendar_rows": calendar_rows,
        "control_representation": "exact PR31/PR34 19 features",
        "challenger_features": FUND_FEATURES,
        "filing_join_rule": "only snapshots with filed <= signal date; latest eligible filing wins",
        "duration_fact_categories_loaded_into_model": False,
        "external_semiconductor_holdouts_loaded": False,
        "finite_model_rows_by_symbol": finite_by_symbol,
        "snapshot_diagnostics": snapshot_diagnostics,
        "targets": results,
        "earned_targets": earned,
        "decision": "SEC_BALANCE_SHEET_MODALITY_EARNS_AT_LEAST_ONE_PATH_HEAD" if earned else "REJECT_SEC_BALANCE_SHEET_MODALITY_FOR_ALL_PATH_HEADS",
        "trading_utility_defined": False,
        "admission_or_ranking_policy_changed": False,
        "research_only": True,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_action": False,
        "live_trading_change": False,
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SEMICONDUCTOR_SEC_BALANCE_SHEET_INFORMATION_VALUE=" + json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
