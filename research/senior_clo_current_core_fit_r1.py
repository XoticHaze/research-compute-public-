from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from research.p558_current_core_opportunity_cost_r1 import CORE_SYMBOLS, build_incumbent_monthly

START_DOWNLOAD = "2018-01-01"
START_EVAL = "2021-01-01"
END = "2026-09-12"
CANDIDATE = "JAAA"
CASH = "BIL"
MIX_WEIGHT = 0.50
MONTHLY_REBALANCE_COST = 0.001
ENDPOINT_COST = 0.0025
OUT = Path("research/artifacts/senior_clo_current_core_fit_r1.json")


def stats(s: pd.Series) -> dict[str, float | int | None]:
    x = s.dropna().astype(float)
    if len(x) < 12:
        return {"months": int(len(x)), "cagr": None, "vol": None, "sharpe": None, "max_drawdown": None}
    y = x.to_numpy().copy()
    y[0] -= ENDPOINT_COST
    y[-1] -= ENDPOINT_COST
    wealth = np.cumprod(1 + y)
    years = len(y) / 12.0
    cagr = float(wealth[-1] ** (1 / years) - 1)
    vol = float(np.std(y, ddof=1) * math.sqrt(12))
    sharpe = float(np.mean(y) * 12 / vol) if vol > 0 else None
    maxdd = float(np.min(wealth / np.maximum.accumulate(wealth) - 1))
    return {"months": int(len(y)), "cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": maxdd}


def mixed_net(a: pd.Series, b: pd.Series) -> pd.Series:
    q = pd.concat([a, b], axis=1).dropna()
    out: list[float] = []
    for ra, rb in q.to_numpy():
        gross = MIX_WEIGHT * ra + (1 - MIX_WEIGHT) * rb
        denom = 1 + gross
        if denom <= 0:
            out.append(np.nan)
            continue
        w1_after = MIX_WEIGHT * (1 + ra) / denom
        w2_after = (1 - MIX_WEIGHT) * (1 + rb) / denom
        traded = abs(w1_after - MIX_WEIGHT) + abs(w2_after - (1 - MIX_WEIGHT))
        out.append(gross - MONTHLY_REBALANCE_COST * traded)
    return pd.Series(out, index=q.index, dtype=float)


def frame(base: pd.DataFrame, start: str, end: str | None = None) -> dict[str, object]:
    q = base.loc[start:end].dropna()
    challenger = stats(q["challenger"])
    matched = stats(q["matched_control"])
    incumbent = stats(q["incumbent"])
    corr = float((q[CANDIDATE] - q[CASH]).corr(q["incumbent"])) if len(q) >= 12 else None
    return {
        "months": int(len(q)),
        "challenger": challenger,
        "matched_control": matched,
        "incumbent": incumbent,
        "matched_excess_pp": None if challenger["cagr"] is None or matched["cagr"] is None else 100 * (challenger["cagr"] - matched["cagr"]),
        "incumbent_cagr_delta_pp": None if challenger["cagr"] is None or incumbent["cagr"] is None else 100 * (challenger["cagr"] - incumbent["cagr"]),
        "sharpe_delta_vs_incumbent": None if challenger["sharpe"] is None or incumbent["sharpe"] is None else challenger["sharpe"] - incumbent["sharpe"],
        "maxdd_improvement_vs_incumbent_pp": None if challenger["max_drawdown"] is None or incumbent["max_drawdown"] is None else 100 * (challenger["max_drawdown"] - incumbent["max_drawdown"]),
        "candidate_excess_to_incumbent_corr": corr,
    }


def main() -> None:
    tickers = list(dict.fromkeys(list(CORE_SYMBOLS) + [CANDIDATE, CASH]))
    raw = yf.download(tickers, start=START_DOWNLOAD, end=END, auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        raise SystemExit("SOURCE_FAILURE_EMPTY")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[tickers].dropna(how="all").astype(float)
    incumbent, incumbent_diag = build_incumbent_monthly(close)
    simple = close[[CANDIDATE, CASH]].resample("ME").last().pct_change(fill_method=None)
    base = pd.concat({"incumbent": incumbent, CANDIDATE: simple[CANDIDATE], CASH: simple[CASH]}, axis=1).dropna()
    base["challenger"] = mixed_net(base["incumbent"], base[CANDIDATE])
    base["matched_control"] = mixed_net(base["incumbent"], base[CASH])
    base = base.dropna()

    windows = {
        "2021+": frame(base, "2021-01-01"),
        "2022+": frame(base, "2022-01-01"),
        "2023+": frame(base, "2023-01-01"),
    }
    blocks = {
        "2021_2022": frame(base, "2021-01-01", "2022-12-31"),
        "2023_2024": frame(base, "2023-01-01", "2024-12-31"),
        "2025_plus": frame(base, "2025-01-01"),
    }
    positive_windows = sum(v["months"] >= 18 and (v["matched_excess_pp"] or -999) > 0 for v in windows.values())
    positive_blocks = sum(v["months"] >= 18 and (v["matched_excess_pp"] or -999) > 0 for v in blocks.values())
    coverage_ready = all(v["months"] >= 18 for v in blocks.values())
    full = windows["2021+"]
    corr = full["candidate_excess_to_incumbent_corr"]

    passed = (
        coverage_ready
        and positive_windows >= 2
        and positive_blocks >= 2
        and (full["matched_excess_pp"] or -999) > 0
        and corr is not None and abs(corr) <= 0.50
        and full["sharpe_delta_vs_incumbent"] is not None and full["sharpe_delta_vs_incumbent"] > 0
        and full["maxdd_improvement_vs_incumbent_pp"] is not None and full["maxdd_improvement_vs_incumbent_pp"] > 0
    )
    if not coverage_ready:
        decision = "SENIOR_CLO_CURRENT_CORE_COVERAGE_NOT_READY"
    elif passed:
        decision = "SENIOR_CLO_CURRENT_CORE_COMPLEMENTARITY_SUPPORTED"
    else:
        decision = "SENIOR_CLO_CURRENT_CORE_COMPLEMENTARITY_NOT_SUPPORTED"

    result = {
        "schema": "research.senior_clo_current_core_fit_r1.v1",
        "workload_id": "SENIOR_CLO_CURRENT_CORE_FIT_R1",
        "parent": "SENIOR_CLO_CARRY_ALPHA",
        "claim": "The independently supported JAAA structured-credit alpha should remain additive when transplanted into the actual unchanged P249+P266 incumbent, versus equal capital parked in BIL, without tuning weight, dates, costs, products, or chronology.",
        "source_evidence": {
            "independent_alpha_commandcenter_commit": "93b21c34aad436b0fe861871b275f6904cd1390f",
            "independent_alpha_run_id": 34588247821,
            "independent_alpha_artifact_id": 10194505774,
        },
        "incumbent_identity": {
            "name": "P249+P266",
            "implementation": "research/p279_p249_p266_forward_shadow_observer_r1.py::_portfolio_weights + _month_costs",
        },
        "contract": {
            "challenger": "50% unchanged P249+P266 + 50% JAAA",
            "matched_control": "50% unchanged P249+P266 + 50% BIL",
            "fixed_diagnostic_weight": MIX_WEIGHT,
            "monthly_rebalance_traded_notional_cost_bps": 10,
            "endpoint_cost_bps_each": 25,
            "windows": ["2021+", "2022+", "2023+"],
            "blocks": ["2021_2022", "2023_2024", "2025_plus"],
            "max_abs_candidate_excess_to_incumbent_corr": 0.50,
            "parameter_search": False,
            "weight_optimization": False,
            "incumbent_internal_costs_preserved": True,
            "diagnostic_weight_is_not_allocation_recommendation": True,
        },
        "incumbent_materialization": incumbent_diag,
        "common_sample": {
            "months": int(len(base)),
            "first_month": str(base.index.min().date()) if len(base) else None,
            "last_month": str(base.index.max().date()) if len(base) else None,
        },
        "windows": windows,
        "blocks": blocks,
        "positive_windows": int(positive_windows),
        "positive_blocks": int(positive_blocks),
        "coverage_ready": coverage_ready,
        "decision_rule": "SUPPORTED only if all three chronology blocks have >=18 common months, at least 2/3 windows and 2/3 blocks have positive challenger-vs-matched-control CAGR excess, full 2021+ matched excess is positive, abs(JAAA-BIL correlation to incumbent)<=0.50, and full-history Sharpe and max drawdown both improve versus unchanged incumbent. No weight/date/cost/product/window rescue.",
        "decision": decision,
        "scientific_consequence": (
            "Advance exact frozen JAAA diagnostic to Coordinator opportunity-cost/forward-shadow review; no allocation authority is conferred."
            if passed else
            "Preserve standalone senior-CLO alpha evidence, but do not promote this frozen current-core complement; no nearby weight/date/cost/product rescue."
            if coverage_ready else
            "Record common-history coverage insufficiency only; do not move dates or change the frozen diagnostic to rescue coverage."
        ),
        "boundaries": {
            "scientific_authority": True,
            "portfolio_ranking": False,
            "allocation_authority": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({
        "decision": decision,
        "common_months": result["common_sample"]["months"],
        "positive_windows": positive_windows,
        "positive_blocks": positive_blocks,
        "full_matched_excess_pp": None if full["matched_excess_pp"] is None else round(full["matched_excess_pp"], 3),
        "full_incumbent_cagr_delta_pp": None if full["incumbent_cagr_delta_pp"] is None else round(full["incumbent_cagr_delta_pp"], 3),
        "full_sharpe_delta": None if full["sharpe_delta_vs_incumbent"] is None else round(full["sharpe_delta_vs_incumbent"], 3),
        "full_maxdd_improvement_pp": None if full["maxdd_improvement_vs_incumbent_pp"] is None else round(full["maxdd_improvement_vs_incumbent_pp"], 3),
        "corr": None if corr is None else round(corr, 3),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
