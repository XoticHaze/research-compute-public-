from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

SESSION_SETTLE_ET = dt_time(18, 30)


def _completed_market_data_date(now_utc: datetime) -> date:
    """Return the latest date allowed to contribute a completed US daily bar.

    Before 18:30 America/New_York, exclude the current calendar date even if a
    provider exposes an intraday/partial daily candle. Weekends and holidays are
    harmless because downstream market data naturally falls back to the last
    actual trading session.
    """
    eastern = now_utc.astimezone(ZoneInfo("America/New_York"))
    return eastern.date() if eastern.time() >= SESSION_SETTLE_ET else eastern.date() - timedelta(days=1)


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


def _observed_close_returns(close: pd.DataFrame) -> pd.DataFrame:
    """Missing daily closes must remain missing, never a synthetic flat return."""
    return close.pct_change(fill_method=None)


def _held_symbols_ready(day: pd.Series, state: dict[str, dict[str, float]]) -> bool:
    """Only score a date when both frozen arms have actual paired daily closes."""
    held = set(state["p249_core"]) | set(state["p249_plus_p266"])
    return bool(held) and bool(day.reindex(sorted(held)).notna().all())



def _implicit_target_reset_turnover_audit(
    rows: list[dict[str, object]],
    daily_returns: pd.DataFrame,
    month_states: dict[str, dict[str, dict[str, float]]],
) -> dict[str, object]:
    """Describe the uncharged daily resets implied by constant-target shadow returns.

    This is NOT an executed trade ledger, a funded monthly-hold counterfactual,
    or an economic re-scoring. It consumes only the exact already-scored daily
    returns and frozen monthly target weights, and never changes either arm.
    """
    arms = ("p249_core", "p249_plus_p266")
    result = {
        arm: {
            "intramonth_one_way_turnover": 0.0,
            "intramonth_reset_count": 0,
            "month_boundary_one_way_turnover": 0.0,
            "month_boundary_count": 0,
        }
        for arm in arms
    }
    for current, following in zip(rows, rows[1:]):
        current_day = str(current["date"])
        next_day = str(following["date"])
        if current_day >= next_day:
            raise ValueError("P249_TURNOVER_AUDIT_NONCHRONOLOGICAL")
        current_month = str(current["holding_month"])
        next_month = str(following["holding_month"])
        for arm in arms:
            weights = month_states[current_month][arm]
            next_weights = month_states[next_month][arm]
            if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-8):
                raise ValueError("P249_TURNOVER_AUDIT_INVALID_TARGET")
            if not math.isclose(sum(next_weights.values()), 1.0, abs_tol=1e-8):
                raise ValueError("P249_TURNOVER_AUDIT_INVALID_NEXT_TARGET")
            gross = float(current[f"{arm}_gross"])
            wealth = 1.0 + gross
            if not math.isfinite(wealth) or wealth <= 0:
                raise ValueError("P249_TURNOVER_AUDIT_INVALID_WEALTH")
            pretrade = {}
            for symbol, weight in weights.items():
                daily = float(daily_returns.at[pd.Timestamp(current_day), symbol])
                if not math.isfinite(daily) or daily <= -1.0 or weight < 0:
                    raise ValueError("P249_TURNOVER_AUDIT_INVALID_HELD_RETURN")
                pretrade[symbol] = weight * (1.0 + daily) / wealth
            if not math.isclose(sum(pretrade.values()), 1.0, abs_tol=1e-8):
                raise ValueError("P249_TURNOVER_AUDIT_PRETRADE_SUM")
            one_way = 0.5 * sum(
                abs(next_weights.get(symbol, 0.0) - pretrade.get(symbol, 0.0))
                for symbol in set(pretrade) | set(next_weights)
            )
            kind = "intramonth" if current_month == next_month else "month_boundary"
            result[arm][f"{kind}_one_way_turnover"] += one_way
            result[arm][f"{kind}_{'reset_count' if kind == 'intramonth' else 'count'}"] += 1
    return {
        "status": "DIAGNOSTIC_ONLY_UNCHARGED_IMPLICIT_RESETS",
        "scored_sessions": len(rows),
        "transitions": max(0, len(rows) - 1),
        "source": "exact_already_scored_daily_returns_and_frozen_month_targets",
        "not_actual_trades_or_funded_monthly_hold": True,
        "not_fee_adjusted_or_alpha_credit": True,
        "arms": result,
    }



def _monthly_hold_drift_diagnostic(
    rows: list[dict[str, object]],
    daily_returns: pd.DataFrame,
    month_states: dict[str, dict[str, dict[str, float]]],
) -> dict[str, object]:
    """Same-source monthly buy/hold drift diagnostic; never a broker fill ledger.

    Retains the original monthly target and first-session legacy cost convention,
    but does not reset component weights inside the holding month. No new price
    fetch, weight selection, or change to the original constant-target series.
    """
    arms = ("p249_core", "p249_plus_p266")
    if not rows:
        return {"status": "NO_SCORED_SESSIONS", "arms": {}, "not_broker_or_alpha_credit": True}
    result: dict[str, dict[str, object]] = {}
    for arm in arms:
        positions: dict[str, float] = {}
        last_date = ""
        last_month = ""
        nav_path: list[dict[str, object]] = []
        realized_month_turnover = 0.0
        rebalance_count = 0
        total_legacy_fee_on_nav = 0.0
        for row in rows:
            day = str(row["date"])
            month = str(row["holding_month"])
            if (last_date and day <= last_date) or not day.startswith(month):
                raise ValueError("P249_MONTHLY_DRIFT_NONCHRONOLOGICAL")
            target = month_states[month][arm]
            if (not target or any(not math.isfinite(float(w)) or float(w) < 0 for w in target.values())
                    or not math.isclose(sum(float(w) for w in target.values()), 1.0, abs_tol=1e-8)):
                raise ValueError("P249_MONTHLY_DRIFT_INVALID_TARGET")
            pre_nav = sum(positions.values()) if positions else 1.0
            if not math.isfinite(pre_nav) or pre_nav <= 0:
                raise ValueError("P249_MONTHLY_DRIFT_UNFUNDED_NAV")
            first_of_month = month != last_month
            if first_of_month:
                if row.get("cost_detail") is None:
                    raise ValueError("P249_MONTHLY_DRIFT_MISSING_MONTH_COST")
                if positions:
                    before = {s: v / pre_nav for s, v in positions.items()}
                    realized_month_turnover += 0.5 * sum(
                        abs(float(target.get(s, 0.0)) - before.get(s, 0.0))
                        for s in set(before) | set(target)
                    )
                else:
                    realized_month_turnover += 1.0
                positions = {s: pre_nav * float(w) for s, w in target.items()}
                rebalance_count += 1
                fee_rate = float(row[f"{arm}_gross"]) - float(row[f"{arm}_net"])
                if not math.isfinite(fee_rate) or fee_rate < -1e-12 or fee_rate >= 1:
                    raise ValueError("P249_MONTHLY_DRIFT_INVALID_LEGACY_FEE")
                fee_rate = max(0.0, fee_rate)
            else:
                if row.get("cost_detail") is not None:
                    raise ValueError("P249_MONTHLY_DRIFT_UNEXPECTED_INTRAMONTH_COST")
                fee_rate = 0.0
            for symbol in positions:
                daily = float(daily_returns.at[pd.Timestamp(day), symbol])
                if not math.isfinite(daily) or daily <= -1.0:
                    raise ValueError("P249_MONTHLY_DRIFT_INVALID_HELD_RETURN")
                positions[symbol] *= 1.0 + daily
            before_fee = sum(positions.values())
            fee_nav = pre_nav * fee_rate
            after_fee = before_fee - fee_nav
            if not math.isfinite(after_fee) or after_fee <= 0 or before_fee <= 0:
                raise ValueError("P249_MONTHLY_DRIFT_UNFUNDED_AFTER_FEE")
            if first_of_month:
                observed_gross = before_fee / pre_nav - 1.0
                if not math.isclose(observed_gross, float(row[f"{arm}_gross"]), rel_tol=1e-9, abs_tol=1e-10):
                    raise ValueError("P249_MONTHLY_DRIFT_FIRST_DAY_SOURCE_MISMATCH")
            fee_scale = after_fee / before_fee
            positions = {s: v * fee_scale for s, v in positions.items()}
            total_legacy_fee_on_nav += fee_nav
            nav_path.append({"date": day, "holding_month": month, "nav": after_fee,
                             "monthly_rebalance": first_of_month})
            last_date, last_month = day, month
        navs = [float(x["nav"]) for x in nav_path]
        peak = 1.0
        drawdown = 0.0
        for nav in navs:
            peak = max(peak, nav)
            drawdown = min(drawdown, nav / peak - 1.0)
        result[arm] = {
            "terminal_nav": navs[-1],
            "cumulative_return": navs[-1] - 1.0,
            "max_drawdown": drawdown,
            "monthly_rebalances_including_initial": rebalance_count,
            "realized_month_boundary_one_way_turnover_including_initial": realized_month_turnover,
            "legacy_monthly_fee_nav_total": total_legacy_fee_on_nav,
            "daily_nav": nav_path,
        }
    core = float(result["p249_core"]["terminal_nav"])
    combo = float(result["p249_plus_p266"]["terminal_nav"])
    original_core = math.prod(1.0 + float(row["p249_core_net"]) for row in rows)
    original_combo = math.prod(1.0 + float(row["p249_plus_p266_net"]) for row in rows)
    if min(core, combo, original_core, original_combo) <= 0:
        raise ValueError("P249_MONTHLY_DRIFT_INVALID_COMPARISON_NAV")
    return {
        "status": "SAME_SOURCE_MONTHLY_HOLD_DRIFT_DIAGNOSTIC",
        "scored_sessions": len(rows),
        "source": "exact_existing_yfinance_adjusted_close_scored_returns_and_frozen_month_targets",
        "legacy_month_costs_preserved_not_actual_drift_turnover_pricing": True,
        "not_broker_or_alpha_credit": True,
        "no_new_original_issuer_or_execution_provenance": True,
        "arms": result,
        "matched_relative_wealth_bp": 10000.0 * (combo / core - 1.0),
        "original_constant_target_relative_wealth_bp": 10000.0 * (original_combo / original_core - 1.0),
        "monthly_drift_minus_constant_target_relative_bp":
            10000.0 * (combo / core - original_combo / original_core),
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
    completed_data_date = _completed_market_data_date(now)
    end = (completed_data_date + timedelta(days=1)).isoformat()
    raw = yf.download(ALL, start=START_DOWNLOAD, end=end, auto_adjust=True, progress=False, threads=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    close = close[ALL].dropna(how="all").astype(float)
    if close.empty:
        raise RuntimeError("no price data returned")

    latest_by_symbol = {}
    for symbol in ALL:
        valid = close[symbol].dropna()
        latest_by_symbol[symbol] = None if valid.empty else pd.Timestamp(valid.index.max()).date().isoformat()
    dated = [value for value in latest_by_symbol.values() if value]
    source_max_date = max(dated) if dated else None
    lagging_symbols = sorted(
        symbol for symbol, value in latest_by_symbol.items()
        if source_max_date is not None and value != source_max_date
    )

    decision_date = DECISION_AT.tz_convert(None).normalize()
    ret = _observed_close_returns(close)
    forward_ix = ret.index[ret.index >= decision_date]
    rows = []
    month_states: dict[str, dict[str, dict[str, float]]] = {}
    prev_state = None
    seen_months: set[str] = set()
    unresolved_gap: dict[str, object] | None = None

    for dt in forward_ix:
        period = dt.to_period("M")
        key = str(period)
        if key not in month_states:
            month_states[key] = _portfolio_weights(close.loc[:dt], period)
        state = month_states[key]
        day = ret.loc[dt]
        if not _held_symbols_ready(day, state):
            # A later complete daily return cannot repair exposure lost across
            # an earlier missing held close. Stop, do not resume one-day NAV.
            held = sorted(set(state["p249_core"]) | set(state["p249_plus_p266"]))
            unresolved_gap = {
                "first_unresolved_session": dt.date().isoformat(),
                "reason": "MISSING_HELD_SYMBOL_RETURN",
                "missing_held_symbols": [symbol for symbol in held if pd.isna(day.get(symbol, np.nan))],
            }
            break
        core_gross = sum(state["p249_core"].get(s, 0.0) * float(day.get(s, np.nan)) for s in state["p249_core"])
        sat_gross = sum(state["p249_plus_p266"].get(s, 0.0) * float(day.get(s, np.nan)) for s in state["p249_plus_p266"])
        if not np.isfinite(core_gross) or not np.isfinite(sat_gross):
            unresolved_gap = {
                "first_unresolved_session": dt.date().isoformat(),
                "reason": "NONFINITE_HELD_PORTFOLIO_RETURN",
                "missing_held_symbols": [],
            }
            break
        # A skipped/incomplete first session must not consume the monthly cost.
        core_cost = 0.0
        sat_cost = 0.0
        cost_detail = None
        if key not in seen_months:
            core_cost, sat_cost, cost_detail = _month_costs(prev_state, state)
            seen_months.add(key)
            prev_state = state
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

    try:
        turnover_audit = _implicit_target_reset_turnover_audit(rows, ret, month_states)
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        # Audit-only failure cannot silently change frozen economic arms.
        turnover_audit = {
            "status": "DIAGNOSTIC_UNAVAILABLE",
            "reason": str(exc) if str(exc).startswith("P249_TURNOVER_AUDIT_") else "AUDIT_SOURCE_UNAVAILABLE",
            "not_actual_trades_or_funded_monthly_hold": True,
            "not_fee_adjusted_or_alpha_credit": True,
        }

    try:
        monthly_drift_diagnostic = _monthly_hold_drift_diagnostic(rows, ret, month_states)
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        monthly_drift_diagnostic = {
            "status": "DIAGNOSTIC_UNAVAILABLE",
            "reason": str(exc) if str(exc).startswith("P249_MONTHLY_DRIFT_") else "SOURCE_UNAVAILABLE",
            "not_broker_or_alpha_credit": True,
        }

    result = {
        "schema": "research.p279_p249_p266_forward_shadow_observer_r1",
        "parent": "P249/P266/P278/P279",
        "decision_at": DECISION_AT.isoformat(),
        "observed_at": now.isoformat(),
        "status": "SOURCE_GAP_UNRESOLVED" if unresolved_gap else ("FORWARD_OBSERVING" if len(rows) else "BASELINE_FROZEN_NO_FORWARD_CLOSES"),
        "source_health": {
            "provider": "yfinance_adjusted_close",
            "completed_session_request_date": completed_data_date.isoformat(),
            "in_progress_session_excluded": True,
            "source_max_date": source_max_date,
            "latest_by_symbol": latest_by_symbol,
            "lagging_symbols_vs_source_max": lagging_symbols,
            "all_symbols_share_latest_date": not lagging_symbols and len(dated) == len(ALL),
            "latest_scored_common_session": rows[-1]["date"] if rows else None,
            "unresolved_forward_gap": unresolved_gap,
            "common_session_lags_source_max": bool(rows and source_max_date and rows[-1]["date"] < source_max_date),
        },
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
            "economic_continuity_verified": unresolved_gap is None,
            "first_close": rows[0]["date"] if rows else None,
            "latest_close": rows[-1]["date"] if rows else None,
            "p249_core_net": _metrics(core_net),
            "p249_plus_p266_net": _metrics(sat_net),
            "satellite_increment_cumulative": float((1 + increment).prod() - 1) if len(increment) else 0.0,
            "implicit_target_reset_turnover_audit": turnover_audit,
            "monthly_hold_drift_diagnostic": monthly_drift_diagnostic,
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
