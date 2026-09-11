from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from research.p279_p249_p266_forward_shadow_observer_r1 import (
    ALL as CORE_SYMBOLS,
    P266_COST_BP,
    _month_costs,
    _portfolio_weights,
    _turnover,
)

START_DOWNLOAD = "2018-01-01"
START_EVAL = "2021-01-01"
END = "2026-09-12"
CANDIDATE_WEIGHT = 0.25
CORE_WEIGHT = 0.75
MIX_REBALANCE_COST = 0.001  # 10 bp per dollar one-way traded notional.
ENDPOINT_COST = 0.0025      # 25 bp at each diagnostic endpoint.
CASH = "BIL"
SIMPLE_CANDIDATES = ["JAAA", "SRLN", "KMLM"]
CANDIDATES = ["P266", *SIMPLE_CANDIDATES]
OUT = Path("research/artifacts/p249_orthogonal_sleeve_tournament_r1.json")


def stats(s: pd.Series) -> dict[str, float | int | None]:
    x = s.dropna().astype(float)
    if len(x) < 12:
        return {
            "months": int(len(x)),
            "cagr": None,
            "vol": None,
            "sharpe": None,
            "max_drawdown": None,
        }
    y = x.to_numpy().copy()
    y[0] -= ENDPOINT_COST
    y[-1] -= ENDPOINT_COST
    wealth = np.cumprod(1 + y)
    years = len(y) / 12.0
    cagr = float(wealth[-1] ** (1 / years) - 1)
    vol = float(np.std(y, ddof=1) * math.sqrt(12))
    sharpe = float(np.mean(y) * 12 / vol) if vol > 0 else None
    maxdd = float(np.min(wealth / np.maximum.accumulate(wealth) - 1))
    return {
        "months": int(len(y)),
        "cagr": cagr,
        "vol": vol,
        "sharpe": sharpe,
        "max_drawdown": maxdd,
    }


def mix_net(core: pd.Series, sleeve: pd.Series) -> pd.Series:
    q = pd.concat([core.rename("core"), sleeve.rename("sleeve")], axis=1).dropna()
    out: list[float] = []
    for core_ret, sleeve_ret in q.to_numpy():
        gross = CORE_WEIGHT * core_ret + CANDIDATE_WEIGHT * sleeve_ret
        denom = 1 + gross
        if denom <= 0:
            out.append(np.nan)
            continue
        core_after = CORE_WEIGHT * (1 + core_ret) / denom
        sleeve_after = CANDIDATE_WEIGHT * (1 + sleeve_ret) / denom
        traded_notional = abs(core_after - CORE_WEIGHT) + abs(sleeve_after - CANDIDATE_WEIGHT)
        out.append(gross - MIX_REBALANCE_COST * traded_notional)
    return pd.Series(out, index=q.index, dtype=float)


def build_core_and_p266_monthly(close: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict[str, object]]:
    core_close = close[list(CORE_SYMBOLS)].dropna(how="all").astype(float)
    daily_ret = core_close.pct_change(fill_method=None)
    eval_days = daily_ret.index[daily_ret.index >= pd.Timestamp(START_EVAL)]
    core_rows: list[tuple[pd.Timestamp, float]] = []
    p266_rows: list[tuple[pd.Timestamp, float]] = []
    prev_state = None
    state_cache: dict[str, dict[str, dict[str, float]]] = {}
    seen_months: set[str] = set()
    cost_detail: dict[str, object] = {}

    for dt in eval_days:
        period = dt.to_period("M")
        key = str(period)
        if key not in state_cache:
            state_cache[key] = _portfolio_weights(core_close.loc[:dt], period)
        state = state_cache[key]
        core_cost = 0.0
        p266_cost = 0.0
        if key not in seen_months:
            core_cost, _, detail = _month_costs(prev_state, state)
            p266_turn = _turnover(None if prev_state is None else prev_state["p266"], state["p266"])
            p266_cost = P266_COST_BP * p266_turn / 10000.0
            cost_detail[key] = {
                **detail,
                "p266_standalone_cost_bp": P266_COST_BP * p266_turn,
            }
            prev_state = state
            seen_months.add(key)

        day = daily_ret.loc[dt]
        core_gross = sum(
            state["p249_core"].get(sym, 0.0) * float(day.get(sym, np.nan))
            for sym in state["p249_core"]
        )
        p266_gross = sum(
            state["p266"].get(sym, 0.0) * float(day.get(sym, np.nan))
            for sym in state["p266"]
        )
        if not np.isnan(core_gross):
            core_rows.append((dt, core_gross - core_cost))
        if not np.isnan(p266_gross):
            p266_rows.append((dt, p266_gross - p266_cost))

    core_daily = pd.Series(dict(core_rows), dtype=float).sort_index()
    p266_daily = pd.Series(dict(p266_rows), dtype=float).sort_index()
    core_monthly = core_daily.resample("ME").apply(
        lambda x: float((1 + x).prod() - 1) if len(x) else np.nan
    ).dropna()
    p266_monthly = p266_daily.resample("ME").apply(
        lambda x: float((1 + x).prod() - 1) if len(x) else np.nan
    ).dropna()
    diag = {
        "core_months": int(len(core_monthly)),
        "p266_months": int(len(p266_monthly)),
        "first_core_month": str(core_monthly.index.min().date()) if len(core_monthly) else None,
        "last_core_month": str(core_monthly.index.max().date()) if len(core_monthly) else None,
        "monthly_cost_detail": cost_detail,
    }
    return core_monthly, p266_monthly, diag


def frame(core: pd.Series, sleeve: pd.Series, cash: pd.Series, start: str, end: str | None = None) -> dict[str, object]:
    q = pd.concat(
        [core.rename("core"), sleeve.rename("sleeve"), cash.rename("cash")],
        axis=1,
    ).loc[start:end].dropna()
    challenger_series = mix_net(q["core"], q["sleeve"])
    matched_series = mix_net(q["core"], q["cash"])
    core_stats = stats(q["core"])
    challenger = stats(challenger_series)
    matched = stats(matched_series)
    excess = q["sleeve"] - q["cash"]
    full_corr = float(excess.corr(q["core"])) if len(q) >= 12 else None
    down = q[q["core"] < 0]
    downside_corr = float((down["sleeve"] - down["cash"]).corr(down["core"])) if len(down) >= 6 else None
    downside_positive_fraction = float((down["sleeve"] > 0).mean()) if len(down) else None
    return {
        "months": int(len(q)),
        "core": core_stats,
        "challenger": challenger,
        "capital_parking_control": matched,
        "matched_capital_excess_cagr_pp": (
            None if challenger["cagr"] is None or matched["cagr"] is None
            else 100 * (challenger["cagr"] - matched["cagr"])
        ),
        "core_cagr_delta_pp": (
            None if challenger["cagr"] is None or core_stats["cagr"] is None
            else 100 * (challenger["cagr"] - core_stats["cagr"])
        ),
        "sharpe_delta_vs_core": (
            None if challenger["sharpe"] is None or core_stats["sharpe"] is None
            else challenger["sharpe"] - core_stats["sharpe"]
        ),
        "maxdd_improvement_vs_core_pp": (
            None if challenger["max_drawdown"] is None or core_stats["max_drawdown"] is None
            else 100 * (challenger["max_drawdown"] - core_stats["max_drawdown"])
        ),
        "sleeve_excess_to_core_corr": full_corr,
        "downside_excess_to_core_corr": downside_corr,
        "downside_months": int(len(down)),
        "sleeve_positive_when_core_negative_fraction": downside_positive_fraction,
    }


def rank_candidates(candidate_results: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    eligible = {
        name: result for name, result in candidate_results.items()
        if result["persistence_passed"]
    }
    if not eligible:
        return []

    rows = []
    for name, result in eligible.items():
        full = result["windows"]["2021+"]
        rows.append({
            "candidate": name,
            "matched_capital_excess_cagr_pp": full["matched_capital_excess_cagr_pp"],
            "core_cagr_delta_pp": full["core_cagr_delta_pp"],
            "sharpe_delta_vs_core": full["sharpe_delta_vs_core"],
            "maxdd_improvement_vs_core_pp": full["maxdd_improvement_vs_core_pp"],
            "abs_downside_excess_to_core_corr": (
                None if full["downside_excess_to_core_corr"] is None
                else abs(full["downside_excess_to_core_corr"])
            ),
        })
    table = pd.DataFrame(rows).set_index("candidate")
    higher = [
        "matched_capital_excess_cagr_pp",
        "core_cagr_delta_pp",
        "sharpe_delta_vs_core",
        "maxdd_improvement_vs_core_pp",
    ]
    score_parts = []
    n = len(table)
    for col in higher:
        score_parts.append(table[col].rank(method="average", ascending=True, pct=True))
    downside = table["abs_downside_excess_to_core_corr"].copy()
    worst = float(downside.dropna().max()) + 1.0 if downside.notna().any() else 2.0
    downside = downside.fillna(worst)
    score_parts.append((-downside).rank(method="average", ascending=True, pct=True))
    score = pd.concat(score_parts, axis=1).mean(axis=1)
    table["equal_rank_utility_score"] = score
    table["rank"] = table["equal_rank_utility_score"].rank(method="min", ascending=False).astype(int)
    table = table.sort_values(
        ["rank", "matched_capital_excess_cagr_pp", "core_cagr_delta_pp"],
        ascending=[True, False, False],
    )
    return [
        {"candidate": idx, **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()}}
        for idx, row in table.iterrows()
    ]


def main() -> None:
    tickers = list(dict.fromkeys(list(CORE_SYMBOLS) + SIMPLE_CANDIDATES + [CASH]))
    raw = yf.download(
        tickers,
        start=START_DOWNLOAD,
        end=END,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if raw.empty:
        raise SystemExit("SOURCE_FAILURE_EMPTY")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close.reindex(columns=tickers).dropna(how="all").astype(float)
    if close.empty:
        raise SystemExit("SOURCE_FAILURE_NO_CLOSE")

    core, p266, dynamic_diag = build_core_and_p266_monthly(close)
    simple = close[SIMPLE_CANDIDATES + [CASH]].resample("ME").last().pct_change(fill_method=None)
    cash = simple[CASH]
    sleeve_series: dict[str, pd.Series] = {
        "P266": p266,
        "JAAA": simple["JAAA"],
        "SRLN": simple["SRLN"],
        "KMLM": simple["KMLM"],
    }

    windows_spec = {
        "2021+": ("2021-01-01", None),
        "2022+": ("2022-01-01", None),
        "2023+": ("2023-01-01", None),
    }
    blocks_spec = {
        "2021_2022": ("2021-01-01", "2022-12-31"),
        "2023_2024": ("2023-01-01", "2024-12-31"),
        "2025_plus": ("2025-01-01", None),
    }

    candidate_results: dict[str, dict[str, object]] = {}
    for name, sleeve in sleeve_series.items():
        windows = {k: frame(core, sleeve, cash, *bounds) for k, bounds in windows_spec.items()}
        blocks = {k: frame(core, sleeve, cash, *bounds) for k, bounds in blocks_spec.items()}
        coverage_ready = all(v["months"] >= 18 for v in blocks.values())
        positive_windows = sum(
            v["months"] >= 18 and (v["matched_capital_excess_cagr_pp"] or -999) > 0
            for v in windows.values()
        )
        positive_blocks = sum(
            v["months"] >= 18 and (v["matched_capital_excess_cagr_pp"] or -999) > 0
            for v in blocks.values()
        )
        full_excess = windows["2021+"]["matched_capital_excess_cagr_pp"]
        persistence_passed = bool(
            coverage_ready
            and positive_windows >= 2
            and positive_blocks >= 2
            and full_excess is not None
            and full_excess > 0
        )
        candidate_results[name] = {
            "source_identity": {
                "P266": "frozen 12-1 top-3 industry momentum from p279 helper with 50 bp turnover cost",
                "JAAA": "senior CLO fund return; fund expenses embedded in adjusted prices",
                "SRLN": "senior bank-loan fund return; fund expenses embedded in adjusted prices",
                "KMLM": "managed-futures fund return; fund expenses embedded in adjusted prices",
            }[name],
            "windows": windows,
            "blocks": blocks,
            "coverage_ready": coverage_ready,
            "positive_windows": int(positive_windows),
            "positive_blocks": int(positive_blocks),
            "persistence_passed": persistence_passed,
        }

    ranking = rank_candidates(candidate_results)
    top = [r for r in ranking if r["rank"] == 1]
    if not ranking:
        decision = "P249_ORTHOGONAL_SLEEVE_TOURNAMENT__NO_PERSISTENT_CANDIDATE"
    elif len(top) == 1:
        decision = f"P249_ORTHOGONAL_SLEEVE_TOURNAMENT__{top[0]['candidate']}__TOP_NORMALIZED_UTILITY"
    else:
        decision = "P249_ORTHOGONAL_SLEEVE_TOURNAMENT__TOP_UTILITY_TIE"

    result = {
        "schema": "research.p249_orthogonal_sleeve_tournament_r1.v1",
        "workload_id": "P249_ORTHOGONAL_SLEEVE_TOURNAMENT_R1",
        "parent": "P249/P266/SENIOR_CLO/FLOATING_RATE_BANK_LOAN/MANAGED_FUTURES",
        "claim": "Under one frozen 25% sleeve / 75% P249-core capital rule, compare four already-supported orthogonal sleeve classes on matched capital-parking excess, direct P249 opportunity cost, risk efficiency, downside overlap, and chronology without candidate-specific weight/date/cost/product tuning.",
        "incumbent_identity": {
            "name": "P249 core",
            "implementation": "research/p279_p249_p266_forward_shadow_observer_r1.py::_portfolio_weights[p249_core] + _month_costs core cost",
        },
        "contract": {
            "core_weight": CORE_WEIGHT,
            "candidate_weight": CANDIDATE_WEIGHT,
            "capital_parking_control": "75% unchanged P249 core + 25% BIL",
            "mix_monthly_rebalance_traded_notional_cost_bps": MIX_REBALANCE_COST * 10000,
            "endpoint_cost_bps_each": ENDPOINT_COST * 10000,
            "p266_internal_turnover_cost_bps": P266_COST_BP,
            "simple_fund_expenses": "embedded in adjusted prices",
            "windows": list(windows_spec),
            "blocks": list(blocks_spec),
            "persistence_gate": "all three chronology blocks >=18 common months; positive matched-capital excess in >=2/3 fixed windows and >=2/3 blocks; full 2021+ matched-capital excess >0",
            "ranking": "Among persistence-pass candidates only, equal-weight percentile-rank average of full-2021+ matched-capital excess CAGR, direct CAGR delta vs P249, Sharpe delta vs P249, max-drawdown improvement vs P249, and inverse absolute downside candidate-excess/P249 correlation. No score weights or candidate rules are tuned after outcomes.",
            "parameter_search": False,
            "candidate_weight_optimization": False,
            "candidate_specific_dates": False,
            "candidate_specific_capital_rule": False,
            "incumbent_internal_costs_preserved": True,
            "diagnostic_ranking_is_not_allocation_authority": True,
        },
        "candidate_source_evidence": {
            "P266": [
                "CommandCenter P266 independent-universe transport",
                "CommandCenter P273 doubled-cost fixed-combination capital-role stress",
            ],
            "JAAA": ["CommandCenter senior-CLO independent alpha", "public senior_clo_current_core_fit_r1 precedent"],
            "SRLN": ["CommandCenter P373 bank-loan complement role", "public PR #864 frozen bank-loan/P249 gate"],
            "KMLM": ["public p558_current_core_opportunity_cost_r1 current-core precedent", "managed-futures R4/R5 inventory evidence"],
        },
        "dynamic_materialization": dynamic_diag,
        "candidates": candidate_results,
        "ranking": ranking,
        "decision": decision,
        "decision_rule": "This tournament is a scientific portfolio-role discriminator, not allocation authority. A candidate must first pass the common persistence gate. Relative utility is then ranked under one frozen equal-rank multi-metric rule; raw Sharpe/drawdown improvement cannot erase direct P249 return opportunity cost.",
        "scientific_consequence": "Return the top normalized-utility candidate(s), full metric tradeoffs, and any non-dominated alternatives to Coordinator for bounded portfolio-role review. Do not optimize weights or change portfolio/runtime/broker authority.",
        "boundaries": {
            "scientific_authority": True,
            "portfolio_ranking": False,
            "allocation_authority": False,
            "strategy_spec_mutation": False,
            "runtime": False,
            "broker": False,
            "live_trading": False,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps({
        "decision": decision,
        "ranking": ranking,
        "persistence": {k: v["persistence_passed"] for k, v in candidate_results.items()},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
