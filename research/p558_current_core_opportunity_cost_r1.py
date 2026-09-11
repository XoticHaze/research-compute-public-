from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from research.p279_p249_p266_forward_shadow_observer_r1 import (
    ALL as CORE_SYMBOLS,
    _month_costs,
    _portfolio_weights,
)

START_DOWNLOAD = "2018-01-01"
START_EVAL = "2021-01-01"
END = "2026-09-12"
KMLM = "KMLM"
CASH = "BIL"
MIX_WEIGHT = 0.50
MONTHLY_REBALANCE_COST = 0.001  # 10 bp traded notional, frozen from P558
ENDPOINT_COST = 0.0025          # 25 bp each endpoint, frozen from P558
OUT = Path("research/artifacts/p558_current_core_opportunity_cost_r1.json")


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
        traded_notional = abs(w1_after - MIX_WEIGHT) + abs(w2_after - (1 - MIX_WEIGHT))
        out.append(gross - MONTHLY_REBALANCE_COST * traded_notional)
    return pd.Series(out, index=q.index, dtype=float)


def build_incumbent_monthly(close: pd.DataFrame) -> tuple[pd.Series, dict[str, object]]:
    daily_ret = close.pct_change(fill_method=None)
    eval_days = daily_ret.index[daily_ret.index >= pd.Timestamp(START_EVAL)]
    rows: list[tuple[pd.Timestamp, float]] = []
    prev_state = None
    seen_months: set[str] = set()
    state_cache: dict[str, dict[str, dict[str, float]]] = {}
    monthly_cost_detail: dict[str, object] = {}

    for dt in eval_days:
        period = dt.to_period("M")
        key = str(period)
        if key not in state_cache:
            state_cache[key] = _portfolio_weights(close.loc[:dt], period)
        state = state_cache[key]
        cost = 0.0
        if key not in seen_months:
            _, sat_cost, detail = _month_costs(prev_state, state)
            cost = sat_cost
            monthly_cost_detail[key] = detail
            prev_state = state
            seen_months.add(key)
        day = daily_ret.loc[dt]
        gross = sum(
            state["p249_plus_p266"].get(sym, 0.0) * float(day.get(sym, np.nan))
            for sym in state["p249_plus_p266"]
        )
        if np.isnan(gross):
            continue
        rows.append((dt, gross - cost))

    daily = pd.Series({dt: ret for dt, ret in rows}, dtype=float).sort_index()
    monthly = daily.resample("ME").apply(lambda x: float((1 + x).prod() - 1) if len(x) else np.nan).dropna()
    return monthly, {
        "months": int(len(monthly)),
        "first_month": str(monthly.index.min().date()) if len(monthly) else None,
        "last_month": str(monthly.index.max().date()) if len(monthly) else None,
        "monthly_cost_detail": monthly_cost_detail,
    }


def frame(base: pd.DataFrame, start: str, end: str | None = None) -> dict[str, object]:
    q = base.loc[start:end].dropna()
    challenger = stats(q["challenger"])
    matched = stats(q["matched_control"])
    incumbent = stats(q["incumbent"])
    corr = float((q[KMLM] - q[CASH]).corr(q["incumbent"])) if len(q) >= 12 else None
    return {
        "months": int(len(q)),
        "challenger": challenger,
        "matched_control": matched,
        "incumbent": incumbent,
        "matched_excess_pp": None if challenger["cagr"] is None or matched["cagr"] is None else 100 * (challenger["cagr"] - matched["cagr"]),
        "incumbent_cagr_delta_pp": None if challenger["cagr"] is None or incumbent["cagr"] is None else 100 * (challenger["cagr"] - incumbent["cagr"]),
        "sharpe_delta_vs_incumbent": None if challenger["sharpe"] is None or incumbent["sharpe"] is None else challenger["sharpe"] - incumbent["sharpe"],
        "maxdd_improvement_vs_incumbent_pp": None if challenger["max_drawdown"] is None or incumbent["max_drawdown"] is None else 100 * (challenger["max_drawdown"] - incumbent["max_drawdown"]),
        "managed_futures_excess_to_incumbent_corr": corr,
    }


def main() -> None:
    tickers = list(dict.fromkeys(list(CORE_SYMBOLS) + [KMLM, CASH]))
    raw = yf.download(tickers, start=START_DOWNLOAD, end=END, auto_adjust=True, progress=False, threads=False)
    if raw.empty:
        raise SystemExit("SOURCE_FAILURE_EMPTY")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[tickers].dropna(how="all").astype(float)
    if close.empty:
        raise SystemExit("SOURCE_FAILURE_NO_CLOSE")

    incumbent, incumbent_diag = build_incumbent_monthly(close)
    simple = close[[KMLM, CASH]].resample("ME").last().pct_change(fill_method=None)
    base = pd.concat({"incumbent": incumbent, KMLM: simple[KMLM], CASH: simple[CASH]}, axis=1).dropna()
    base["challenger"] = mixed_net(base["incumbent"], base[KMLM])
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
    corr = full["managed_futures_excess_to_incumbent_corr"]

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
        decision = "P558_CURRENT_CORE_SOURCE_COVERAGE_NOT_READY"
    elif passed:
        decision = "P558_CURRENT_CORE_COMPLEMENTARITY_SUPPORTED"
    else:
        decision = "P558_CURRENT_CORE_COMPLEMENTARITY_NOT_SUPPORTED"

    result = {
        "schema": "research.p558_current_core_opportunity_cost_r1.v1",
        "workload_id": "P558_CURRENT_CORE_OPPORTUNITY_COST_R1",
        "parent": "MANAGED_FUTURES_RETURN_SOURCE_TRANSPORT",
        "claim": "The already-frozen 50/50 KMLM complementarity diagnostic should remain additive when transplanted from P305 to the actual unchanged P249+P266 incumbent core, after incumbent internal costs and the frozen P558 mix costs.",
        "incumbent_identity": {
            "name": "P249+P266",
            "implementation": "research/p279_p249_p266_forward_shadow_observer_r1.py::_portfolio_weights + _month_costs",
            "p249_result_run_id": 34441059315,
            "p249_result_artifact_id": 10137946389,
            "p266_source_commit": "4cca78d08bd6ce21726be9bef9b09b0387e197ce",
            "p278_result_run_id": 34449749421,
            "p278_result_artifact_id": 10141056125,
        },
        "contract": {
            "challenger": "50% unchanged P249+P266 incumbent + 50% KMLM",
            "matched_control": "50% unchanged P249+P266 incumbent + 50% BIL",
            "fixed_weight": MIX_WEIGHT,
            "monthly_rebalance_traded_notional_cost_bps": 10,
            "endpoint_cost_bps_each": 25,
            "windows": ["2021+", "2022+", "2023+"],
            "blocks": ["2021_2022", "2023_2024", "2025_plus"],
            "max_abs_managed_futures_excess_to_incumbent_corr": 0.50,
            "parameter_search": False,
            "weight_optimization": False,
            "incumbent_internal_costs_preserved": True,
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
        "decision_rule": "SUPPORTED only if all three chronology blocks have >=18 common months, at least 2/3 fixed windows and 2/3 blocks have positive challenger-vs-matched-control CAGR excess, full 2021+ matched excess is positive, abs(KMLM-BIL correlation to incumbent)<=0.50, and full-history Sharpe and max drawdown both improve versus the unchanged incumbent. No weight/date/cost/window rescue.",
        "decision": decision,
        "scientific_consequence": (
            "Advance KMLM to Coordinator opportunity-cost/admission review against P249+P266; no allocation authority is conferred."
            if passed else
            "Do not promote the P558 managed-futures complement into the incumbent core from this frozen crossing. Preserve standalone managed-futures evidence but do not optimize weight, dates, costs, or windows to rescue."
            if coverage_ready else
            "Record common-history coverage insufficiency only; do not move dates or alter weights/costs to rescue coverage."
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
