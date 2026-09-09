from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE = Path("results/p46_issuer_totalreturn_replay_r1.json")
COSTS_BPS = (25, 50, 100)
WINDOWS = {
    "full": None,
    "2020_forward": "2020-01",
    "2022_forward": "2022-01",
    "2024_forward": "2024-01",
}


def cagr(r: pd.Series):
    r = pd.Series(r).dropna()
    return float((1.0 + r).prod() ** (12.0 / len(r)) - 1.0) if len(r) else None


def max_dd(r: pd.Series):
    eq = (1.0 + pd.Series(r).dropna()).cumprod()
    return float((eq / eq.cummax() - 1.0).min()) if len(eq) else None


def folds(candidate: pd.Series, control: pd.Series):
    chunks = np.array_split(np.arange(len(candidate)), 5)
    values = []
    for idx in chunks:
        if len(idx) < 2:
            continue
        values.append(cagr(candidate.iloc[idx]) - cagr(control.iloc[idx]))
    return {"values": [float(x) for x in values], "positive": int(sum(x > 0 for x in values)), "count": len(values)}


def main():
    source = json.loads(SOURCE.read_text())
    f = pd.DataFrame(source["rows"])
    f["return_period"] = pd.PeriodIndex(f["return_month"], freq="M")
    output = {
        "schema": "research.p46_issuer_replay_chronology_r1",
        "parent": "P46",
        "source_result_sha": source.get("schema"),
        "contract": {
            "fixed_windows": WINDOWS,
            "costs_bps": list(COSTS_BPS),
            "same_rows_and_controls_as_source_replay": True,
            "no_parameter_or_weight_changes": True,
            "decision_rule": "matched-control support requires positive 50-bps excess in at least three of four fixed windows; opportunity-cost weakness is reported separately rather than converted into a model kill",
        },
        "windows": {},
    }
    positive_50 = 0
    for name, start in WINDOWS.items():
        x = f.copy()
        if start is not None:
            x = x[x.return_period >= pd.Period(start, freq="M")]
        entry = {
            "months": int(len(x)),
            "matched_ew_cagr": cagr(x.matched_ew),
            "spy_cagr": cagr(x.spy),
            "qqq_cagr": cagr(x.qqq),
            "matched_ew_max_drawdown": max_dd(x.matched_ew),
            "costs": {},
        }
        for bps in COSTS_BPS:
            candidate = x.gross - x.turnover * (bps / 10000.0)
            candidate_cagr = cagr(candidate)
            matched_excess = candidate_cagr - entry["matched_ew_cagr"]
            entry["costs"][str(bps)] = {
                "candidate_cagr": candidate_cagr,
                "matched_ew_excess_cagr": matched_excess,
                "spy_excess_cagr": candidate_cagr - entry["spy_cagr"],
                "qqq_excess_cagr": candidate_cagr - entry["qqq_cagr"],
                "candidate_max_drawdown": max_dd(candidate),
                "folds_vs_matched": folds(candidate.reset_index(drop=True), x.matched_ew.reset_index(drop=True)),
            }
        if entry["costs"]["50"]["matched_ew_excess_cagr"] > 0:
            positive_50 += 1
        output["windows"][name] = entry
    output["positive_50bps_windows"] = positive_50
    output["decision"] = (
        "P46_ISSUER_MATCHED_ALPHA_CHRONOLOGY_SUPPORTED"
        if positive_50 >= 3
        else "P46_ISSUER_MATCHED_ALPHA_CHRONOLOGY_WEAK"
    )
    Path("results/p46_issuer_replay_chronology_r1.json").write_text(json.dumps(output, indent=2, sort_keys=True))
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
