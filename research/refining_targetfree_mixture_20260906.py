from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

import refining_mechanism_attribution_20260906 as base

K = 4
RANDOM_STATE = 20260906
N_INIT = 50
MIN_DEV_CLUSTER = 12
MIN_HOLDOUT_CLUSTER = 6
WIN_GATE = 0.55
BLOCK_GATE = 2
SLEEVES = ["CRAK", *base.COMPLEMENTS]


def all_features() -> list[str]:
    cols: list[str] = []
    for family in base.FAMILIES.values():
        cols.extend(family)
    return cols


def sleeve_return(row: pd.Series, sleeve: str) -> float:
    if sleeve == "CRAK":
        return float(row.crak_net50)
    return float(row[f"{sleeve}_net10"])


def block_stats(rows: pd.DataFrame, values: pd.Series, blocks: int = 3) -> list[dict]:
    if rows.empty:
        return []
    chunks = np.array_split(np.arange(len(rows)), blocks)
    out = []
    for k, idx in enumerate(chunks, 1):
        if len(idx) == 0:
            continue
        v = values.iloc[idx]
        out.append({
            "block": k,
            "start": rows.date.iloc[int(idx[0])].isoformat(),
            "end": rows.date.iloc[int(idx[-1])].isoformat(),
            "n": int(len(idx)),
            "mean_bps": float(v.mean() * 10000.0),
            "win_rate": float((v > 0).mean()),
        })
    return out


def excess_summary(rows: pd.DataFrame, ret_values: pd.Series) -> dict:
    if rows.empty:
        return {"n": 0}
    excess = {
        "XLE": ret_values - rows.xle_fwd,
        "SPY": ret_values - rows.spy_fwd,
        "QQQ": ret_values - rows.qqq_fwd,
    }
    out = {
        "n": int(len(rows)),
        "start": rows.date.iloc[0].isoformat(),
        "end": rows.date.iloc[-1].isoformat(),
        "mean_return_pct": float(ret_values.mean() * 100.0),
    }
    for b, v in excess.items():
        blocks = block_stats(rows, v)
        out[f"excess_{b.lower()}_bps"] = float(v.mean() * 10000.0)
        out[f"{b.lower()}_win_rate"] = float((v > 0).mean())
        out[f"{b.lower()}_blocks"] = blocks
        out[f"positive_{b.lower()}_blocks"] = int(sum(1 for row in blocks if row["mean_bps"] > 0))
    return out


def refining_gate(summary: dict, min_n: int) -> bool:
    if summary.get("n", 0) < min_n:
        return False
    for b in ["xle", "spy", "qqq"]:
        if summary.get(f"excess_{b}_bps", -1e9) <= 0:
            return False
        if summary.get(f"{b}_win_rate", 0.0) < WIN_GATE:
            return False
        if summary.get(f"positive_{b}_blocks", 0) < BLOCK_GATE:
            return False
    return True


def broad_gate(summary: dict, min_n: int) -> bool:
    if summary.get("n", 0) < min_n:
        return False
    for b in ["spy", "qqq"]:
        if summary.get(f"excess_{b}_bps", -1e9) <= 0:
            return False
        if summary.get(f"{b}_win_rate", 0.0) < WIN_GATE:
            return False
        if summary.get(f"positive_{b}_blocks", 0) < BLOCK_GATE:
            return False
    return True


def top_centroid_features(center: np.ndarray, cols: list[str], n: int = 6) -> list[dict]:
    order = np.argsort(np.abs(center))[::-1][:n]
    return [{"feature": cols[int(i)], "z": float(center[int(i)])} for i in order]


def component_residuals(rows: pd.DataFrame, close: pd.DataFrame) -> dict:
    out = {}
    if rows.empty:
        return out
    for symbol in ["MPC", "VLO", "PSX"]:
        vals = []
        for row in rows.itertuples(index=False):
            i = int(row.pos)
            gross = float(close[symbol].iloc[i + base.FORWARD] / close[symbol].iloc[i] - 1.0)
            net = (1.0 + gross) * (1.0 - base.CRAK_COST_BPS / 10000.0) - 1.0
            vals.append(net - float(row.crak_net50))
        arr = np.asarray(vals, dtype=float)
        out[symbol] = {
            "n": int(len(arr)),
            "mean_residual_vs_crak_bps": float(arr.mean() * 10000.0),
            "win_rate_vs_crak": float((arr > 0).mean()),
        }
    return out


def mapping_performance(rows: pd.DataFrame, mapping: dict[int, str]) -> dict:
    records = []
    for row in rows.itertuples(index=False):
        cluster = int(row.cluster)
        sleeve = mapping.get(cluster)
        if sleeve is None:
            records.append({"date": row.date.isoformat(), "cluster": cluster, "sleeve": "CASH", "ret": 0.0, "spy": 0.0, "qqq": 0.0})
            continue
        sret = float(row.crak_net50 if sleeve == "CRAK" else getattr(row, f"{sleeve}_net10"))
        records.append({"date": row.date.isoformat(), "cluster": cluster, "sleeve": sleeve, "ret": sret, "spy": float(row.spy_fwd), "qqq": float(row.qqq_fwd)})
    if not records:
        return {"n": 0}
    frame = pd.DataFrame(records)
    active = frame[frame.sleeve != "CASH"].copy()
    def compound(values: pd.Series) -> float:
        if len(values) == 0:
            return 0.0
        return float(np.prod(1.0 + values.to_numpy(float)) - 1.0)
    out = {
        "decisions": int(len(frame)),
        "active_decisions": int(len(active)),
        "occupancy_fraction": float(len(active) / len(frame)),
        "mapped_total_return_pct": float(compound(frame.ret) * 100.0),
        "same_active_schedule_spy_return_pct": float(compound(active.spy) * 100.0),
        "same_active_schedule_qqq_return_pct": float(compound(active.qqq) * 100.0),
        "active_mean_excess_spy_bps": None if active.empty else float((active.ret - active.spy).mean() * 10000.0),
        "active_mean_excess_qqq_bps": None if active.empty else float((active.ret - active.qqq).mean() * 10000.0),
        "active_spy_win_rate": None if active.empty else float(((active.ret - active.spy) > 0).mean()),
        "active_qqq_win_rate": None if active.empty else float(((active.ret - active.qqq) > 0).mean()),
        "assignments": records,
    }
    return out


def main() -> None:
    raw = {s: base.load(s) for s in base.SYMBOLS}
    close = pd.concat([raw[s].close.rename(s) for s in base.SYMBOLS], axis=1, join="inner").dropna().sort_index()
    features = base.build_state(close)
    panel = base.decision_panel(close, features)

    split = int(len(panel) * base.DEV_FRACTION)
    dev = panel.iloc[:split].copy().reset_index(drop=True)
    holdout = panel.iloc[split:].copy().reset_index(drop=True)
    cols = all_features()

    scaler = StandardScaler().fit(dev[cols].to_numpy(float))
    xdev = scaler.transform(dev[cols].to_numpy(float))
    xhold = scaler.transform(holdout[cols].to_numpy(float))
    km = KMeans(n_clusters=K, random_state=RANDOM_STATE, n_init=N_INIT, algorithm="lloyd")
    dev["cluster"] = km.fit_predict(xdev)
    holdout["cluster"] = km.predict(xhold)

    # Cluster identity is target-free. Outcome gates below are development-only and freeze exact cluster IDs.
    dev_clusters = {}
    holdout_clusters = {}
    dev_refining_survivors: list[int] = []
    holdout_refining_confirmed: list[int] = []
    ownership_mapping: dict[int, str] = {}
    ownership_dev = {}
    ownership_holdout = {}

    for cluster in range(K):
        d = dev[dev.cluster == cluster].copy().reset_index(drop=True)
        h = holdout[holdout.cluster == cluster].copy().reset_index(drop=True)
        crak_dev = excess_summary(d, d.crak_net50)
        crak_hold = excess_summary(h, h.crak_net50)
        crak_dev["component_residuals_vs_crak"] = component_residuals(d, close)
        crak_hold["component_residuals_vs_crak"] = component_residuals(h, close)
        dev_clusters[str(cluster)] = crak_dev
        holdout_clusters[str(cluster)] = crak_hold
        if refining_gate(crak_dev, MIN_DEV_CLUSTER):
            dev_refining_survivors.append(cluster)

        # Development-only mixture owner selection from a predeclared sleeve set.
        candidates = {}
        for sleeve in SLEEVES:
            r = d.crak_net50 if sleeve == "CRAK" else d[f"{sleeve}_net10"]
            summary = excess_summary(d, r)
            summary["broad_gate"] = broad_gate(summary, MIN_DEV_CLUSTER)
            candidates[sleeve] = summary
        eligible = [s for s, summary in candidates.items() if summary["broad_gate"]]
        selected = None
        if eligible:
            selected = max(eligible, key=lambda s: min(candidates[s]["excess_spy_bps"], candidates[s]["excess_qqq_bps"]))
            ownership_mapping[cluster] = selected
        ownership_dev[str(cluster)] = {
            "selected_sleeve": selected,
            "eligible_sleeves": eligible,
            "candidates": candidates,
        }

    for cluster in dev_refining_survivors:
        h = holdout[holdout.cluster == cluster].copy().reset_index(drop=True)
        if refining_gate(holdout_clusters[str(cluster)], MIN_HOLDOUT_CLUSTER):
            holdout_refining_confirmed.append(cluster)

    for cluster, sleeve in ownership_mapping.items():
        h = holdout[holdout.cluster == cluster].copy().reset_index(drop=True)
        r = h.crak_net50 if sleeve == "CRAK" else h[f"{sleeve}_net10"]
        summary = excess_summary(h, r)
        summary["broad_gate"] = broad_gate(summary, MIN_HOLDOUT_CLUSTER)
        ownership_holdout[str(cluster)] = {"sleeve": sleeve, "summary": summary}

    centroids = {}
    for cluster in range(K):
        centroids[str(cluster)] = {
            "top_standardized_features": top_centroid_features(km.cluster_centers_[cluster], cols),
            "development_n": int((dev.cluster == cluster).sum()),
            "holdout_n": int((holdout.cluster == cluster).sum()),
        }

    dev_map_perf = mapping_performance(dev, ownership_mapping)
    hold_map_perf = mapping_performance(holdout, ownership_mapping)
    mapping_confirmed_clusters = [
        int(cluster) for cluster, row in ownership_holdout.items()
        if row["summary"]["broad_gate"]
    ]

    representation_decision = (
        "TARGET_FREE_REFINING_STATE_CONFIRMED"
        if dev_refining_survivors and holdout_refining_confirmed
        else "NO_TARGET_FREE_REFINING_STATE_CONFIRMED"
    )
    mixture_decision = (
        "TARGET_FREE_MIXTURE_MAPPING_CONFIRMED"
        if ownership_mapping and mapping_confirmed_clusters and hold_map_perf.get("active_mean_excess_spy_bps", -1e9) > 0 and hold_map_perf.get("active_mean_excess_qqq_bps", -1e9) > 0
        else "TARGET_FREE_MIXTURE_MAPPING_NOT_CONFIRMED"
    )

    payload = {
        "schema": "research.refining_targetfree_mixture.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo adjusted daily chart endpoint; environment-independent public data",
        "lineage": {
            "prior_linear_pr": 91,
            "prior_linear_run": 34029120747,
            "prior_linear_decision": "NOT_SUPPORTED",
            "this_is_not_threshold_or_feature_rescue": True,
        },
        "frozen_contract": {
            "representation": "StandardScaler + KMeans",
            "k": K,
            "random_state": RANDOM_STATE,
            "n_init": N_INIT,
            "state_features": cols,
            "state_fit_uses_future_outcomes": False,
            "development_fraction": base.DEV_FRACTION,
            "decision_spacing_sessions": base.DECISION_STEP,
            "forward_sessions": base.FORWARD,
            "crak_cost_bps": base.CRAK_COST_BPS,
            "other_sleeve_cost_bps": base.ETF_COST_BPS,
            "development_refining_gate": {
                "min_cluster_n": MIN_DEV_CLUSTER,
                "positive_mean_excess_vs": ["XLE", "SPY", "QQQ"],
                "min_win_rate_each": WIN_GATE,
                "min_positive_chronology_blocks_each_of_3": BLOCK_GATE,
            },
            "holdout_refining_gate": {
                "min_cluster_n": MIN_HOLDOUT_CLUSTER,
                "same_frozen_cluster_ids_only": True,
                "same_excess_win_block_gates": True,
            },
            "mixture_sleeves": SLEEVES,
            "mixture_owner_selection": "within each target-free cluster, development-only choose among sleeves passing SPY+QQQ mean/win/block gates; maximize min(SPY excess, QQQ excess)",
            "no_holdout_owner_substitution": True,
        },
        "shared_window": {
            "start": close.index[0].isoformat(),
            "end": close.index[-1].isoformat(),
            "rows": int(len(close)),
            "decisions": int(len(panel)),
            "development_decisions": int(len(dev)),
            "holdout_decisions": int(len(holdout)),
            "development_end": dev.date.iloc[-1].isoformat(),
            "holdout_start": holdout.date.iloc[0].isoformat(),
        },
        "centroids": centroids,
        "development_cluster_economics": dev_clusters,
        "holdout_cluster_economics": holdout_clusters,
        "development_refining_survivor_cluster_ids": dev_refining_survivors,
        "holdout_confirmed_refining_cluster_ids": holdout_refining_confirmed,
        "development_mixture_ownership": ownership_dev,
        "frozen_ownership_mapping": {str(k): v for k, v in ownership_mapping.items()},
        "holdout_mixture_ownership_tests": ownership_holdout,
        "development_mapping_performance": dev_map_perf,
        "holdout_mapping_performance": hold_map_perf,
        "holdout_confirmed_mapping_cluster_ids": mapping_confirmed_clusters,
        "decisions": {
            "refining_state": representation_decision,
            "mixture_mapping": mixture_decision,
        },
        "research_only": True,
        "allocation_authority": False,
        "promotion_authority": False,
        "runtime_mutation": False,
        "broker_authority": False,
        "live_trading_change": False,
    }
    with open("refining-targetfree-mixture-20260906.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    print("REFINING_TARGETFREE_MIXTURE=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
