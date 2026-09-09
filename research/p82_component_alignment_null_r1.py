from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import p82_component_contribution_r2 as p82c

N_REPS = 2000
SEED = 820082
WINDOWS = {"2015_forward": "2015-01-01", "2022_forward": "2022-01-01"}


def cagr(r):
    r = pd.Series(r, dtype=float).dropna()
    return float((1 + r).prod() ** (12 / len(r)) - 1) if len(r) else float("nan")


def mdd(r):
    e = (1 + pd.Series(r, dtype=float).fillna(0)).cumprod()
    return float((e / e.cummax() - 1).min())


def actual_stats(q):
    blend = 0.5 * q.p64 + 0.5 * q.p36
    matched = 0.5 * q.p64_matched + 0.5 * q.p36_matched
    p64_ex = q.p64 - q.p64_matched
    p36_ex = q.p36 - q.p36_matched
    return {
        "months": int(len(q)),
        "blend_cagr": cagr(blend),
        "matched_cagr": cagr(matched),
        "qqq_cagr": cagr(q.qqq),
        "excess_vs_matched_cagr": cagr(blend) - cagr(matched),
        "excess_vs_qqq_cagr": cagr(blend) - cagr(q.qqq),
        "blend_mdd": mdd(blend),
        "qqq_mdd": mdd(q.qqq),
        "component_excess_correlation": float(p64_ex.corr(p36_ex)),
    }


def shifted_stats(q, shift):
    p36 = q.p36.shift(shift)
    p36m = q.p36_matched.shift(shift)
    z = pd.DataFrame(
        {
            "p64": q.p64,
            "p64m": q.p64_matched,
            "p36": p36,
            "p36m": p36m,
            "qqq": q.qqq,
        }
    ).dropna()
    blend = 0.5 * z.p64 + 0.5 * z.p36
    matched = 0.5 * z.p64m + 0.5 * z.p36m
    p64_ex = z.p64 - z.p64m
    p36_ex = z.p36 - z.p36m
    return {
        "excess_vs_matched_cagr": cagr(blend) - cagr(matched),
        "excess_vs_qqq_cagr": cagr(blend) - cagr(z.qqq),
        "component_excess_correlation": float(p64_ex.corr(p36_ex)),
    }


def main():
    f = p82c.build()
    rng = np.random.default_rng(SEED)
    out = {
        "schema": "research.p82_component_alignment_null_r1",
        "parent": "P82",
        "hypothesis": "If P82's observed sleeve complementarity depends on contemporaneous component alignment, the unchanged P64/P36 50/50 blend should beat circular month-shift alignment nulls while preserving each sleeve's own return distribution and 50-bps economics.",
        "scientific_contract": {
            "components": "unchanged P64 and P36 SOXX sleeves, each at 50 bps",
            "blend_weights": [0.5, 0.5],
            "matched_control": "same fixed component matched controls",
            "opportunity_control": "QQQ",
            "null": "circularly shift P36 and its matched control together relative to P64; preserve within-sleeve sequence and distribution",
            "replications": N_REPS,
            "seed": SEED,
            "windows": WINDOWS,
            "no_parameter_or_weight_tuning": True,
        },
        "windows": {},
    }

    for name, start in WINDOWS.items():
        q = f.loc[f.index >= pd.Timestamp(start)].copy()
        actual = actual_stats(q)
        # avoid zero shift; sample shifts from 1..n-1 so every null breaks contemporaneous alignment
        shifts = rng.integers(1, len(q), size=N_REPS)
        matched_excess = []
        qqq_excess = []
        correlations = []
        for shift in shifts:
            s = shifted_stats(q, int(shift))
            matched_excess.append(s["excess_vs_matched_cagr"])
            qqq_excess.append(s["excess_vs_qqq_cagr"])
            correlations.append(s["component_excess_correlation"])
        me = np.asarray(matched_excess, dtype=float)
        qe = np.asarray(qqq_excess, dtype=float)
        co = np.asarray(correlations, dtype=float)
        out["windows"][name] = {
            "actual": actual,
            "null": {
                "excess_vs_matched_mean": float(me.mean()),
                "excess_vs_matched_p05": float(np.quantile(me, 0.05)),
                "excess_vs_matched_p95": float(np.quantile(me, 0.95)),
                "p_null_ge_actual_matched_excess": float(np.mean(me >= actual["excess_vs_matched_cagr"])),
                "actual_matched_excess_percentile": float(np.mean(me < actual["excess_vs_matched_cagr"])),
                "excess_vs_qqq_mean": float(qe.mean()),
                "excess_vs_qqq_p05": float(np.quantile(qe, 0.05)),
                "excess_vs_qqq_p95": float(np.quantile(qe, 0.95)),
                "p_null_ge_actual_qqq_excess": float(np.mean(qe >= actual["excess_vs_qqq_cagr"])),
                "actual_qqq_excess_percentile": float(np.mean(qe < actual["excess_vs_qqq_cagr"])),
                "component_excess_correlation_mean": float(co.mean()),
                "p_null_le_actual_correlation": float(np.mean(co <= actual["component_excess_correlation"])),
            },
        }

    z = out["windows"]["2022_forward"]
    a, n = z["actual"], z["null"]
    out["decision"] = (
        "P82_CONTEMPORANEOUS_COMPONENT_ALIGNMENT_SUPPORTED"
        if a["excess_vs_matched_cagr"] > 0
        and a["excess_vs_qqq_cagr"] > 0
        and n["p_null_ge_actual_matched_excess"] <= 0.05
        and n["p_null_ge_actual_qqq_excess"] <= 0.05
        else "P82_CONTEMPORANEOUS_ALIGNMENT_NOT_DISTINGUISHED_FROM_SHIFT_NULL"
    )

    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/p82_component_alignment_null_r1.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, allow_nan=False)
    )
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
