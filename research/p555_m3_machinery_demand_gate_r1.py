from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import yfinance as yf

SOURCE_PATH = Path("artifacts/p555_m3_vintage_materialize_r1.json")
OUT_PATH = Path("artifacts/p555_m3_machinery_demand_gate_r1.json")
COHORT = ["DOV", "SWK", "GWW", "FAST", "IEX", "XYL", "PNR", "GNRC"]
BENCHMARKS = ["XLI", "SPY"]
ALL = COHORT + BENCHMARKS
START = "2012-01-01"
END = "2026-09-12"
COST = 25.0 / 10000.0
FOLDS = [
    ("2013-01-01", "2016-12-31"),
    ("2017-01-01", "2021-12-31"),
    ("2022-01-01", "2026-09-11"),
]


def cagr(r: pd.Series) -> float | None:
    r = r.dropna()
    if len(r) < 2:
        return None
    years = (r.index[-1] - r.index[0]).days / 365.25
    total = float((1.0 + r).prod())
    return None if years <= 0 or total <= 0 else total ** (1.0 / years) - 1.0


def mdd(r: pd.Series) -> float | None:
    r = r.dropna()
    if r.empty:
        return None
    eq = (1.0 + r).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    return {
        "cagr": cagr(r),
        "max_drawdown": mdd(r),
        "vol": None if len(r) < 2 else float(r.std() * math.sqrt(252.0)),
        "days": int(len(r)),
    }


def evaluate(d: pd.DataFrame, a: str, b: str, matched_weight: float) -> dict:
    z = d.loc[a:b].copy()
    matched = matched_weight * z["cohort"] + (1.0 - matched_weight) * z["XLI"]
    s_cagr = cagr(z["strategy"])
    m_cagr = cagr(matched)
    xli_cagr = cagr(z["XLI"])
    spy_cagr = cagr(z["SPY"])
    cohort_cagr = cagr(z["cohort"])
    return {
        "strategy": stats(z["strategy"]),
        "matched_static": stats(matched),
        "cohort": stats(z["cohort"]),
        "XLI": stats(z["XLI"]),
        "SPY": stats(z["SPY"]),
        "matched_excess_cagr": None if s_cagr is None or m_cagr is None else s_cagr - m_cagr,
        "xli_excess_cagr": None if s_cagr is None or xli_cagr is None else s_cagr - xli_cagr,
        "spy_excess_cagr": None if s_cagr is None or spy_cagr is None else s_cagr - spy_cagr,
        "cohort_excess_cagr": None if s_cagr is None or cohort_cagr is None else s_cagr - cohort_cagr,
        "mean_on_exposure": None if z.empty else float(z["on"].mean()),
        "switches": int(z["switch"].sum()) if not z.empty else 0,
    }


def main() -> None:
    source = json.loads(SOURCE_PATH.read_text())
    if source.get("decision") != "VINTAGE_MATERIALIZATION_READY":
        out = {
            "schema": "research.p555_m3_machinery_demand_gate_r1",
            "parent": "P555",
            "decision": "P555_SOURCE_GATE_NOT_READY",
            "source_decision": source.get("decision"),
            "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
        }
        OUT_PATH.parent.mkdir(exist_ok=True)
        OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True))
        print(json.dumps(out, sort_keys=True))
        return

    records = sorted(source["records"], key=lambda x: (x["release_date"], x["report_month"]))
    if len(records) < 24:
        raise RuntimeError(f"insufficient causal source records: {len(records)}")

    events = []
    for i in range(12, len(records)):
        current = float(records[i]["backlog_ratio"])
        prior = [float(x["backlog_ratio"]) for x in records[i - 12:i]]
        threshold = sum(prior) / len(prior)
        events.append({
            "report_month": records[i]["report_month"],
            "release_date": records[i]["release_date"],
            "backlog_ratio": current,
            "prior12_mean": threshold,
            "on": 1.0 if current > threshold else 0.0,
        })

    raw = yf.download(ALL, start=START, end=END, auto_adjust=True, progress=False, group_by="column", threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[ALL].dropna(how="any")
    rets = close.pct_change(fill_method=None).dropna(how="any")
    if rets.empty:
        raise RuntimeError("no common price returns")

    on = pd.Series(index=rets.index, dtype=float)
    effective_events = []
    for event in events:
        release = pd.Timestamp(event["release_date"])
        future = rets.index[rets.index > release]
        if len(future) == 0:
            continue
        effective = future[0]
        on.loc[effective] = event["on"]
        effective_events.append({**event, "effective_date": str(effective.date())})
    on = on.ffill()
    first_valid = on.first_valid_index()
    if first_valid is None:
        raise RuntimeError("no causal signal became effective")

    d = rets.loc[first_valid:].copy()
    d["cohort"] = d[COHORT].mean(axis=1)
    d["on"] = on.loc[d.index]
    d = d.dropna(subset=["on", "cohort", "XLI", "SPY"])
    d["switch"] = d["on"].diff().abs().fillna(0.0)
    d["strategy"] = d["on"] * d["cohort"] + (1.0 - d["on"]) * d["XLI"] - d["switch"] * COST

    matched_weight = float(d["on"].mean())
    overall = evaluate(d, str(d.index.min().date()), "2026-09-11", matched_weight)
    folds = []
    for a, b in FOLDS:
        f = evaluate(d, a, b, matched_weight)
        f["window"] = [a, b]
        folds.append(f)
    positive_folds = sum(1 for f in folds if f["matched_excess_cagr"] is not None and f["matched_excess_cagr"] > 0)

    supported = bool(
        overall["matched_excess_cagr"] is not None
        and overall["xli_excess_cagr"] is not None
        and overall["matched_excess_cagr"] > 0
        and overall["xli_excess_cagr"] > 0
        and positive_folds >= 2
    )
    decision = "P555_SUPPORTED" if supported else "P555_NOT_SUPPORTED_NO_RESCUE"

    out = {
        "schema": "research.p555_m3_machinery_demand_gate_r1",
        "parent": "P555",
        "claim": "Point-in-time Census M3 Industrial Machinery backlog intensity can identify industry-demand states that improve the fixed fresh Industrial Machinery cohort versus XLI after costs.",
        "frozen_contract": {
            "feature": "Industrial machinery SA preliminary unfilled orders / SA preliminary shipments from original release PDFs",
            "signal": "current backlog_ratio > arithmetic mean of previous 12 released backlog ratios",
            "availability": "first trading day strictly after Census release date",
            "on": "equal-weight DOV/SWK/GWW/FAST/IEX/XYL/PNR/GNRC synthetic cohort index",
            "off": "XLI",
            "full_switch_cost_bps": 25.0,
            "matched_control": "static cohort/XLI mix at full-sample mean ON exposure",
            "opportunity_controls": ["always cohort", "XLI", "SPY"],
            "folds": FOLDS,
            "pass_gate": "full matched excess CAGR > 0 AND full XLI excess CAGR > 0 AND >=2/3 positive matched-excess folds",
            "no_parameter_rescue": True,
            "cohort_limitation": "fixed modern fresh cohort applied retrospectively; this tests industry-state timing and not point-in-time historical stock selection",
        },
        "source_diagnostics": {
            "materializer_decision": source["decision"],
            "coverage": source["coverage"],
            "materialized_months": source["materialized_months"],
            "expected_months": source["expected_months"],
            "source_failures": source["failures"],
        },
        "signal_diagnostics": {
            "candidate_release_events": len(events),
            "effective_events": len(effective_events),
            "first_effective_date": effective_events[0]["effective_date"] if effective_events else None,
            "last_effective_date": effective_events[-1]["effective_date"] if effective_events else None,
            "full_mean_on_exposure": matched_weight,
            "full_switches": int(d["switch"].sum()),
        },
        "overall": overall,
        "folds": folds,
        "positive_fold_count": positive_folds,
        "decision": decision,
        "boundaries": {"portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()
