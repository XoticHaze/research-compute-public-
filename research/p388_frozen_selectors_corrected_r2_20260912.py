from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

AUDIT = Path("research/artifacts/p388_cik_integrity_r2_20260912.json")
OUT = Path("research/artifacts/p388_frozen_selectors_corrected_r2_20260912.json")
OUT.parent.mkdir(parents=True, exist_ok=True)
YEARS = list(range(2018, 2025))
N = 40
COST = 0.0025
READY_DECISION = "P388_IDENTIFIER_AND_ANNUAL_COMPARABILITY_READY__RERUN_FROZEN_SELECTORS"


def selected_value(rec: dict, key: str):
    x = rec.get(key)
    if not isinstance(x, dict) or x.get("material_conflict"):
        return None
    s = x.get("selected")
    if not isinstance(s, dict) or s.get("val") is None:
        return None
    try:
        v = float(s["val"])
    except Exception:
        return None
    return v if np.isfinite(v) else None


def annual_features(rec: dict):
    if rec.get("status") != "checked":
        return {"roe": None, "turnover": None}
    ni = selected_value(rec, "net_income")
    eq = selected_value(rec, "equity")
    rev = selected_value(rec, "revenue")
    assets = selected_value(rec, "assets")
    roe = None if ni is None or eq is None or eq <= 0 else ni / eq
    turnover = None if rev is None or assets is None or assets <= 0 else rev / assets
    return {"roe": roe, "turnover": turnover}


def total_returns(tickers, start, end):
    ordered = list(dict.fromkeys([str(t) for t in tickers if t]))
    if not ordered:
        return {}
    raw = yf.download(ordered, start=start, end=end, auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        return {}
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(close, pd.Series):
        close = close.to_frame(ordered[0])
    out = {}
    for t in ordered:
        if t not in close.columns:
            continue
        s = close[t].dropna()
        if len(s) >= 2:
            r = float(s.iloc[-1] / s.iloc[0] - 1)
            if np.isfinite(r):
                out[t] = r
    return out


def evaluate_metric(metric: str, by_year: dict[int, list[dict]], audit_yearly: dict[int, dict]):
    cohorts = []
    for y in YEARS:
        rows = by_year.get(y, [])
        sample_n = int(audit_yearly[y]["sample_n"])
        if sample_n != N or len(rows) != sample_n:
            cohorts.append({
                "year": y,
                "sample_n": sample_n,
                "field_check_n": len(rows),
                "ready": False,
                "reason": "sample_identity_mismatch",
            })
            continue
        feats = []
        for rec in rows:
            v = annual_features(rec)[metric]
            if v is not None and np.isfinite(v):
                feats.append((str(rec["ticker"]), float(v)))
        tickers = [t for t, _ in feats]
        rets = total_returns(tickers + ["SPY"], f"{y}-07-01", f"{y + 1}-07-10")
        usable = sorted([(t, v) for t, v in feats if t in rets], key=lambda x: x[1])
        k = max(1, len(usable) // 4)
        top = usable[-k:] if usable else []
        feature_rate = len(feats) / sample_n if sample_n else 0.0
        price_rate = len(usable) / sample_n if sample_n else 0.0
        ready = feature_rate >= 0.80 and price_rate >= 0.80 and len(top) >= 8 and "SPY" in rets
        if ready:
            candidate = float(np.mean([rets[t] for t, _ in top])) - COST
            control = float(np.mean([rets[t] for t, _ in usable])) - COST
            spy = float(rets["SPY"]) - COST
        else:
            candidate = control = spy = None
        cohorts.append({
            "year": y,
            "sample_n": sample_n,
            "feature_n": len(feats),
            "usable_n": len(usable),
            "feature_rate": feature_rate,
            "price_rate": price_rate,
            "selected_n": len(top),
            "ready": ready,
            "candidate_return": candidate,
            "same_universe_control_return": control,
            "spy_return": spy,
            "excess_vs_control": None if not ready else candidate - control,
            "excess_vs_spy": None if not ready else candidate - spy,
            "selected": [t for t, _ in top],
        })
    valid = [x for x in cohorts if x.get("ready")]
    all_ready = len(valid) == len(YEARS)
    positive_control = sum(x["excess_vs_control"] > 0 for x in valid)
    positive_spy = sum(x["excess_vs_spy"] > 0 for x in valid)
    if all_ready:
        candidate_cagr = float(np.prod([1 + x["candidate_return"] for x in valid]) ** (1 / len(valid)) - 1)
        control_cagr = float(np.prod([1 + x["same_universe_control_return"] for x in valid]) ** (1 / len(valid)) - 1)
        spy_cagr = float(np.prod([1 + x["spy_return"] for x in valid]) ** (1 / len(valid)) - 1)
    else:
        candidate_cagr = control_cagr = spy_cagr = None
    supported = (
        all_ready
        and positive_control >= 5
        and positive_spy >= 4
        and candidate_cagr > control_cagr
        and candidate_cagr > spy_cagr
    )
    if supported:
        decision = f"P388_CORRECTED_{metric.upper()}_SUPPORTED"
    elif all_ready:
        decision = f"P388_CORRECTED_{metric.upper()}_NOT_SUPPORTED"
    else:
        decision = f"P388_CORRECTED_{metric.upper()}_DATA_NOT_READY"
    return {
        "metric": metric,
        "cohorts": cohorts,
        "summary": {
            "ready_years": len(valid),
            "positive_vs_control_years": positive_control,
            "positive_vs_spy_years": positive_spy,
            "candidate_cagr": candidate_cagr,
            "control_cagr": control_cagr,
            "spy_cagr": spy_cagr,
            "excess_cagr_vs_control": None if candidate_cagr is None else candidate_cagr - control_cagr,
            "excess_cagr_vs_spy": None if candidate_cagr is None else candidate_cagr - spy_cagr,
        },
        "decision": decision,
    }


audit = json.loads(AUDIT.read_text())
if audit.get("decision") != READY_DECISION:
    out = {
        "schema": "research.p388_frozen_selectors_corrected_r2_20260912.v1",
        "parent": "P388_POINT_IN_TIME_FUNDAMENTAL_SELECTION",
        "audit_decision": audit.get("decision"),
        "decision": "P388_CORRECTED_SELECTORS_BLOCKED_BY_REPRESENTATION_GATE",
        "alpha_inference": False,
        "boundaries": {"scientific_authority": True, "portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
else:
    by_year = {y: [] for y in YEARS}
    for rec in audit.get("field_checks", []):
        y = int(rec.get("year"))
        if y in by_year:
            by_year[y].append(rec)
    for y in YEARS:
        by_year[y] = sorted(by_year[y], key=lambda r: str(r.get("ticker", "")))
    audit_yearly = {int(x["year"]): x for x in audit.get("yearly", [])}
    roe = evaluate_metric("roe", by_year, audit_yearly)
    turnover = evaluate_metric("turnover", by_year, audit_yearly)
    out = {
        "schema": "research.p388_frozen_selectors_corrected_r2_20260912.v1",
        "parent": "P388_POINT_IN_TIME_FUNDAMENTAL_SELECTION",
        "audit_decision": audit["decision"],
        "audit_sources": audit.get("sources"),
        "contract": {
            "years": YEARS,
            "sample_n": N,
            "sample_identity": "the exact full-PIT sample emitted by the corrected representation audit; no identifier filtering before sample",
            "features": {"roe": "canonical latest-period annual net income / positive equity", "turnover": "canonical latest-period annual revenue / positive assets"},
            "portfolio": "top quartile of usable feature values",
            "cost_bps": 25,
            "coverage_min": 0.80,
            "matched_controls": ["equal-weight same usable PIT feature sample", "SPY"],
            "support_rule": "all 7 cohorts ready; >=5/7 positive vs same-universe; >=4/7 positive vs SPY; compounded candidate CAGR > both controls; no rescue",
            "no_parameter_rescue": True,
        },
        "roe": roe,
        "turnover": turnover,
        "decision": "P388_CORRECTED_FROZEN_CHILDREN_EXECUTED",
        "boundaries": {"scientific_authority": True, "portfolio_ranking": False, "allocation_authority": False, "runtime": False, "broker": False, "live_trading": False},
    }
OUT.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False))
print(json.dumps({
    "decision": out["decision"],
    "audit_decision": out.get("audit_decision"),
    "roe": out.get("roe", {}).get("summary"),
    "roe_decision": out.get("roe", {}).get("decision"),
    "turnover": out.get("turnover", {}).get("summary"),
    "turnover_decision": out.get("turnover", {}).get("decision"),
}, sort_keys=True))
