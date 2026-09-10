from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DECISION_AT = pd.Timestamp("2026-09-10T07:25:00Z")
P248_SOURCE_COMMIT = "20490f115d901aac3b586c33072c1157ad4d10a6"
P249_RESULT_RUN_ID = 34441059315
P249_RESULT_ARTIFACT_ID = 10137946389
P266_SOURCE_COMMIT = "4cca78d08bd6ce21726be9bef9b09b0387e197ce"
P278_RESULT_RUN_ID = 34449749421
P278_RESULT_ARTIFACT_ID = 10141056125

CROSS = ["SPY", "QQQ", "TLT", "GLD", "DBC"]
P64_INDUSTRIES = ["SOXX", "XBI", "XHB", "KRE", "ITA", "IGV", "IYT", "XRT", "XOP", "IHI"]
P266_INDUSTRIES = ["XAR", "XBI", "XHB", "XME", "XOP", "XPH", "XRT", "XSD", "XSW", "XTN", "KRE"]
SMALL_VALUE = ["AVUV", "AVDV"]
ALL = list(dict.fromkeys(CROSS + P64_INDUSTRIES + P266_INDUSTRIES + SMALL_VALUE))

P64_COST_BP = 50.0
P36_COST_BP = 50.0
P266_COST_BP = 50.0
SMALL_VALUE_ENTRY_BP = 10.0
START_DOWNLOAD = "2024-01-01"


def _month_end_frame(close: pd.DataFrame) -> pd.DataFrame:
    return close.resample("ME").last()


def _period_end_index(monthly: pd.DataFrame, period: pd.Period) -> pd.Timestamp:
    matches = monthly.index.to_period("M") == period
    if not matches.any():
        raise RuntimeError(f"missing monthly close for {period}")
    return monthly.index[matches][-1]


def _p64_weights(close: pd.DataFrame, holding_month: pd.Period) -> dict[str, float]:
    formation = holding_month - 1
    monthly = _month_end_frame(close)
    formation_ix = _period_end_index(monthly, formation)
    mom6 = monthly[CROSS + P64_INDUSTRIES].pct_change(6).loc[formation_ix]
    trend = close[CROSS + P64_INDUSTRIES] / close[CROSS + P64_INDUSTRIES].rolling(200, min_periods=160).mean() - 1
    trend_m = trend.resample("ME").last().loc[formation_ix]

    def select(symbols: list[str], top_k: int) -> list[str]:
        frame = pd.DataFrame({"mom6": mom6[symbols], "trend200": trend_m[symbols]}, index=symbols)
        if frame.isna().any().any():
            raise RuntimeError(f"P64 formation data incomplete for {holding_month}")
        score = frame.rank(axis=0, pct=True, method="average").mean(axis=1)
        return list(score.sort_values(ascending=False).head(top_k).index)

    cross = select(CROSS, 2)
    industries = select(P64_INDUSTRIES, 3)
    out: dict[str, float] = defaultdict(float)
    for symbol in cross:
        out[symbol] += 0.5 / 2
    for symbol in industries:
        out[symbol] += 0.5 / 3
    return dict(out)


def _p36_weights(close: pd.DataFrame, holding_month: pd.Period) -> dict[str, float]:
    formation = holding_month - 1
    monthly = _month_end_frame(close[["SOXX", "QQQ"]])
    formation_ix = _period_end_index(monthly, formation)
    rel = monthly["SOXX"].pct_change(6).loc[formation_ix] - monthly["QQQ"].pct_change(6).loc[formation_ix]
    if pd.isna(rel):
        raise RuntimeError(f"P36 formation data incomplete for {holding_month}")
    return {"SOXX" if rel > 0 else "QQQ": 1.0}


def _p266_weights(close: pd.DataFrame, holding_month: pd.Period) -> dict[str, float]:
    monthly = _month_end_frame(close[P266_INDUSTRIES])
    numerator_period = holding_month - 1
    denominator_period = holding_month - 12
    num_ix = _period_end_index(monthly, numerator_period)
    den_ix = _period_end_index(monthly, denominator_period)
    score = monthly.loc[num_ix, P266_INDUSTRIES] / monthly.loc[den_ix, P266_INDUSTRIES] - 1
    if score.isna().any():
        raise RuntimeError(f"P266 formation data incomplete for {holding_month}")
    selected = list(score.sort_values(ascending=False).head(3).index)
    return {symbol: 1 / 3 for symbol in selected}


def _scaled_add(target: dict[str, float], source: dict[str, float], scale: float) -> None:
    for symbol, weight in source.items():
        target[symbol] = target.get(symbol, 0.0) + weight * scale


def _portfolio_weights(close: pd.DataFrame, holding_month: pd.Period) -> dict[str, dict[str, float]]:
    p64 = _p64_weights(close, holding_month)
    p36 = _p36_weights(close, holding_month)
    p266 = _p266_weights(close, holding_month)

    core: dict[str, float] = {}
    core["AVUV"] = 1 / 6
    core["AVDV"] = 1 / 6
    _scaled_add(core, p64, 1 / 3)
    _scaled_add(core, p36, 1 / 3)

    with_satellite: dict[str, float] = {}
    with_satellite["AVUV"] = 1 / 8
    with_satellite["AVDV"] = 1 / 8
    _scaled_add(with_satellite, p64, 1 / 4)
    _scaled_add(with_satellite, p36, 1 / 4)
    _scaled_add(with_satellite, p266, 1 / 4)

    return {"p64": p64, "p36": p36, "p266": p266, "p249_core": core, "p249_plus_p266": with_satellite}


def _turnover(old: dict[str, float] | None, new: dict[str, float]) -> float:
    if old is None:
        return 1.0
    symbols = set(old) | set(new)
    return 0.5 * sum(abs(new.get(s, 0.0) - old.get(s, 0.0)) for s in symbols)


def _month_costs(previous: dict[str, dict[str, float]] | None, current: dict[str, dict[str, float]]) -> tuple[float, float, dict[str, float]]:
    p64_turn = _turnover(None if previous is None else previous["p64"], current["p64"])
    p36_turn = _turnover(None if previous is None else previous["p36"], current["p36"])
    p266_turn = _turnover(None if previous is None else previous["p266"], current["p266"])
    sv_bp = SMALL_VALUE_ENTRY_BP if previous is None else 0.0
    core_bp = (P64_COST_BP * p64_turn + P36_COST_BP * p36_turn + sv_bp) / 3
    satellite_bp = (P64_COST_BP * p64_turn + P36_COST_BP * p36_turn + P266_COST_BP * p266_turn + sv_bp) / 4
    return core_bp / 10000, satellite_bp / 10000, {
        "p64_one_way_turnover": p64_turn,
        "p36_one_way_turnover": p36_turn,
        "p266_one_way_turnover": p266_turn,
        "p249_core_cost_bp": core_bp,
        "p249_plus_p266_cost_bp": satellite_bp,
    }


def _metrics(returns: pd.Series) -> dict[str, float | int | None]:
    q = returns.dropna().astype(float)
    if q.empty:
        return {"days": 0, "cumulative_return": 0.0, "max_drawdown": 0.0, "annualized_vol": None, "sharpe_rf0": None}
    eq = (1 + q).cumprod()
    vol = float(q.std(ddof=1) * math.sqrt(252)) if len(q) > 1 else None
    ann = float(q.mean() * 252) if len(q) > 1 else None
    return {
        "days": int(len(q)),
        "cumulative_return": float(eq.iloc[-1] - 1),
        "max_drawdown": float((eq / eq.cummax() - 1).min()),
        "annualized_vol": vol,
        "sharpe_rf0": float(ann / vol) if vol and ann is not None else None,
    }


def main() -> None:
    now = datetime.now(timezone.utc)
    end = (now + timedelta(days=1)).date().isoformat()
    raw = yf.download(ALL, start=START_DOWNLOAD, end=end, auto_adjust=True, progress=False, threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[ALL].dropna(how="all").astype(float)
    if close.empty:
        raise RuntimeError("no price data returned")

    decision_date = DECISION_AT.tz_convert(None).normalize()
    ret = close.pct_change()
    forward_ix = ret.index[ret.index >= decision_date]
    rows = []
    month_states: dict[str, dict[str, dict[str, float]]] = {}
    prev_state = None
    seen_months: set[str] = set()

    for dt in forward_ix:
        period = dt.to_period("M")
        key = str(period)
        if key not in month_states:
            month_states[key] = _portfolio_weights(close.loc[:dt], period)
        state = month_states[key]
        core_cost = 0.0
        sat_cost = 0.0
        cost_detail = None
        if key not in seen_months:
            core_cost, sat_cost, cost_detail = _month_costs(prev_state, state)
            seen_months.add(key)
            prev_state = state
        day = ret.loc[dt]
        core_gross = sum(state["p249_core"].get(s, 0.0) * float(day.get(s, np.nan)) for s in state["p249_core"])
        sat_gross = sum(state["p249_plus_p266"].get(s, 0.0) * float(day.get(s, np.nan)) for s in state["p249_plus_p266"])
        if np.isnan(core_gross) or np.isnan(sat_gross):
            continue
        rows.append({
            "date": dt.date().isoformat(),
            "holding_month": key,
            "p249_core_gross": core_gross,
            "p249_core_net": core_gross - core_cost,
            "p249_plus_p266_gross": sat_gross,
            "p249_plus_p266_net": sat_gross - sat_cost,
            "satellite_increment_net": (sat_gross - sat_cost) - (core_gross - core_cost),
            "cost_detail": cost_detail,
        })

    current_month = pd.Timestamp(now.date()).to_period("M")
    current_state = _portfolio_weights(close, current_month)
    obs = pd.DataFrame(rows)
    if obs.empty:
        core_net = pd.Series(dtype=float)
        sat_net = pd.Series(dtype=float)
        increment = pd.Series(dtype=float)
    else:
        core_net = obs["p249_core_net"]
        sat_net = obs["p249_plus_p266_net"]
        increment = obs["satellite_increment_net"]

    result = {
        "schema": "research.p279_p249_p266_forward_shadow_observer_r1",
        "parent": "P249/P266/P278/P279",
        "decision_at": DECISION_AT.isoformat(),
        "observed_at": now.isoformat(),
        "status": "FORWARD_OBSERVING" if len(rows) else "BASELINE_FROZEN_NO_FORWARD_CLOSES",
        "contract": {
            "p249_core": "fixed equal-third small-value/P64/P36 primitive stack",
            "p266_satellite": "fixed 12-1 top-3 industry momentum",
            "comparison": "P249 core versus fixed equal-quarter small-value/P64/P36/P266 construction",
            "no_weight_window_topk_universe_threshold_or_parameter_search": True,
            "costs": {"P64_bp": P64_COST_BP, "P36_bp": P36_COST_BP, "P266_bp": P266_COST_BP, "small_value_entry_bp": SMALL_VALUE_ENTRY_BP},
            "measurement": "close-to-close shadow returns after decision timestamp; monthly frozen holdings formed only from prior completed information",
        },
        "source_pins": {
            "P248_source_commit": P248_SOURCE_COMMIT,
            "P249_result_run_id": P249_RESULT_RUN_ID,
            "P249_result_artifact_id": P249_RESULT_ARTIFACT_ID,
            "P266_source_commit": P266_SOURCE_COMMIT,
            "P278_result_run_id": P278_RESULT_RUN_ID,
            "P278_result_artifact_id": P278_RESULT_ARTIFACT_ID,
        },
        "current_holding_month": str(current_month),
        "current_state": current_state,
        "forward": {
            "first_close": rows[0]["date"] if rows else None,
            "latest_close": rows[-1]["date"] if rows else None,
            "p249_core_net": _metrics(core_net),
            "p249_plus_p266_net": _metrics(sat_net),
            "satellite_increment_cumulative": float((1 + increment).prod() - 1) if len(increment) else 0.0,
            "observations": rows,
        },
        "interpretation": "This observer measures the already-frozen research identities prospectively. It never allocates capital, changes portfolio weights, modifies StrategySpec/runtime, or submits broker orders.",
        "boundaries": {"allocation_authority": False, "portfolio_ranking": False, "runtime": False, "broker": False, "live_trading": False},
    }
    Path("artifacts").mkdir(exist_ok=True)
    path = Path("artifacts/p279_p249_p266_forward_shadow_observer_r1.json")
    path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
