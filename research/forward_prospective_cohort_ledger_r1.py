from __future__ import annotations

"""Prospective maturity resolver for sanitized forward-model cohorts.

The ledger is deliberately downstream of frozen model/admission authority. It never
changes a signal, horizon, sizing rule, or promotion gate. It records a cohort when a
sanitized adapter first appears, resolves only after its exact +1 execution / frozen
holding horizon is observable, and rejects a newly discovered cohort if its designated
outcome was already knowable at first registration. Synthetic chronology proofs are
cutoff-aware so the late-registration guard is exercised without future leakage.
"""

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import sleep
from typing import Any, Callable

import pandas as pd

SCHEMA = "research.forward_prospective_cohort_ledger_r1"
ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"
SUPPORTED = {"HOMEBUILDERS", "SEMICONDUCTOR_SHARED_RIDGE"}

CONTRACTS: dict[str, dict[str, Any]] = {
    "HOMEBUILDERS": {
        "source_ref": "100e356239b2399c054c1a41a18e4e9a5d07d33a",
        "execution_delay_sessions": 1,
        "stock_round_trip_cost_bps": 25.0,
        "benchmarks": ["ITB", "QQQ"],
        "minimum_resolved_for_promotion": None,
    },
    "SEMICONDUCTOR_SHARED_RIDGE": {
        "source_ref": "e73ec9b15180e208de541ce5d5304888e5550433",
        "execution_delay_sessions": 1,
        "holding_horizon_sessions": 20,
        "stock_round_trip_cost_bps": 25.0,
        "industry_round_trip_cost_bps": 10.0,
        "benchmarks": ["CASH", "SMH", "QQQ", "EQUAL_WEIGHT_13"],
        "minimum_resolved_for_promotion": 20,
    },
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _adapter(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    x = json.loads(raw)
    if x.get("schema") != ADAPTER_SCHEMA:
        raise RuntimeError(f"unexpected adapter schema path={path}")
    program = str(x.get("program_id") or "")
    if program not in SUPPORTED:
        raise RuntimeError(f"unsupported adapter program={program}")
    boundaries = x.get("boundaries") or {}
    for key in ("broker_action", "live_trading_change", "runtime_mutation", "promotion_authority"):
        if boundaries.get(key) is not False:
            raise RuntimeError(f"adapter boundary must remain false program={program} key={key}")
    return x, _sha(raw)


def _cohort_id(program: str, signal_date: str, adapter_sha256: str) -> str:
    return f"{program}:{signal_date}:{adapter_sha256[:16]}"


def _new_cohort(adapter: dict[str, Any], adapter_sha256: str, registered_at: str) -> dict[str, Any] | None:
    program = str(adapter["program_id"])
    signal_date = str(adapter.get("signal_date") or "")[:10]
    if not signal_date:
        raise RuntimeError(f"missing signal_date program={program}")
    contract = CONTRACTS[program]
    signal = adapter.get("signal") or {}

    if program == "HOMEBUILDERS":
        symbols = [str(x) for x in signal.get("admitted_symbols") or []]
        horizons = {str(k): int(v) for k, v in (signal.get("duration_horizon_sessions_by_symbol") or {}).items()}
        if not symbols:
            return None
        if set(symbols) - set(horizons):
            raise RuntimeError("Homebuilders admitted symbol missing frozen duration horizon")
        return {
            "cohort_id": _cohort_id(program, signal_date, adapter_sha256),
            "program_id": program,
            "signal_date": signal_date,
            "source_adapter_sha256": adapter_sha256,
            "source_ref": contract["source_ref"],
            "first_registered_at": registered_at,
            "status": "REGISTERED",
            "execution_delay_sessions": 1,
            "symbols": symbols,
            "horizon_sessions_by_symbol": {s: horizons[s] for s in symbols},
            "admission_score_fixed20_net25_bps": {
                s: float((signal.get("predicted_fixed20_net25_bps") or {})[s])
                for s in symbols
                if s in (signal.get("predicted_fixed20_net25_bps") or {})
            },
            "benchmarks": ["ITB", "QQQ"],
            "stock_round_trip_cost_bps": 25.0,
            "resolution": None,
        }

    positive = [str(x) for x in signal.get("positive_symbols") or []]
    validation = adapter.get("validation") or {}
    if not positive or validation.get("scientific_forward_credit") is not True:
        return None
    book = ((adapter.get("paper_action") or {}).get("ticker_book") or {})
    raw_weights = {str(k): float(v) for k, v in (book.get("cohort_target_weights_nav") or {}).items() if float(v) > 0}
    if not raw_weights:
        raise RuntimeError("Semiconductor prospective cohort missing frozen ticker-book weights")
    gross = sum(raw_weights.values())
    ticker_weights = {k: v / gross for k, v in raw_weights.items()}
    predictions = {
        str(k): float(v) for k, v in (signal.get("predicted_fixed20_net_value_bps") or {}).items()
    }
    return {
        "cohort_id": _cohort_id(program, signal_date, adapter_sha256),
        "program_id": program,
        "signal_date": signal_date,
        "source_adapter_sha256": adapter_sha256,
        "source_ref": contract["source_ref"],
        "first_registered_at": registered_at,
        "status": "REGISTERED",
        "execution_delay_sessions": 1,
        "holding_horizon_sessions": 20,
        "symbols": positive,
        "ticker_book_weights_within_cohort": ticker_weights,
        "predicted_fixed20_net_value_bps": {s: predictions[s] for s in positive if s in predictions},
        "positive_breadth": float(signal.get("positive_breadth", 0.0)),
        "benchmarks": ["CASH", "SMH", "QQQ", "EQUAL_WEIGHT_13"],
        "stock_round_trip_cost_bps": 25.0,
        "industry_round_trip_cost_bps": 10.0,
        "resolution": None,
    }


def _normalize_series(series: pd.Series) -> pd.Series:
    x = series.dropna().astype(float).copy()
    idx = pd.to_datetime(x.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(None)
    x.index = pd.DatetimeIndex(idx).normalize()
    return x[~x.index.duplicated(keep="last")].sort_index()


def _download_close(symbol: str, start: date, end: date) -> pd.Series:
    import yfinance as yf

    frame = pd.DataFrame()
    failures: list[str] = []
    for attempt, delay_seconds in enumerate((0, 3, 9), 1):
        if delay_seconds:
            sleep(delay_seconds)
        try:
            frame = yf.download(
                symbol,
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception as exc:
            failures.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            frame = pd.DataFrame()
        if not frame.empty:
            break
        failures.append(f"attempt={attempt}:empty")
    if frame.empty:
        detail = " | ".join(failures[-6:])
        raise RuntimeError(f"no market data symbol={symbol} after bounded retries; {detail}")
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        if close.shape[1] != 1:
            raise RuntimeError(f"ambiguous close columns symbol={symbol}")
        close = close.iloc[:, 0]
    return _normalize_series(close)


def _common_calendar(prices: dict[str, pd.Series], symbols: list[str]) -> pd.DatetimeIndex:
    sets = [set(prices[s].index) for s in symbols]
    if not sets:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted(set.intersection(*sets)))


def _ret_bps(series: pd.Series, entry: pd.Timestamp, exit_: pd.Timestamp) -> float:
    return float((series.loc[exit_] / series.loc[entry] - 1.0) * 10000.0)


def _prediction_metrics(predicted: list[float], realized: list[float]) -> dict[str, Any]:
    if not predicted or len(predicted) != len(realized):
        return {
            "count": 0,
            "rank_ic_spearman": None,
            "prediction_mae_bps": None,
            "calibration_intercept_bps": None,
            "calibration_slope": None,
        }
    px = pd.Series(predicted, dtype=float)
    ry = pd.Series(realized, dtype=float)
    rank_ic = None
    if len(px) >= 3 and px.nunique() > 1 and ry.nunique() > 1:
        rank_ic = float(px.rank(method="average").corr(ry.rank(method="average")))
    mae = float((ry - px).abs().mean())
    slope = None
    intercept = None
    if len(px) >= 3 and float(((px - px.mean()) ** 2).sum()) > 0:
        slope = float(((px - px.mean()) * (ry - ry.mean())).sum() / ((px - px.mean()) ** 2).sum())
        intercept = float(ry.mean() - slope * px.mean())
    return {
        "count": int(len(px)),
        "rank_ic_spearman": None if rank_ic is None else round(rank_ic, 6),
        "prediction_mae_bps": round(mae, 4),
        "calibration_intercept_bps": None if intercept is None else round(intercept, 4),
        "calibration_slope": None if slope is None else round(slope, 6),
    }


def _source_health(prices: dict[str, pd.Series], required: list[str]) -> dict[str, Any]:
    latest_by_symbol: dict[str, str | None] = {}
    for symbol in required:
        series = prices.get(symbol)
        latest_by_symbol[symbol] = (
            None
            if series is None or series.empty
            else pd.Timestamp(series.index.max()).date().isoformat()
        )
    dated = [value for value in latest_by_symbol.values() if value]
    source_max = max(dated) if dated else None
    lagging = sorted(
        symbol for symbol, value in latest_by_symbol.items()
        if source_max is not None and value != source_max
    )
    return {
        "provider": "yfinance_adjusted_close",
        "source_max_date": source_max,
        "latest_by_symbol": latest_by_symbol,
        "lagging_symbols_vs_source_max": lagging,
        "all_symbols_share_latest_date": not lagging and len(dated) == len(required),
    }


def _first_entry(calendar: pd.DatetimeIndex, signal_date: str, delay: int) -> tuple[int, pd.Timestamp] | None:
    after = [i for i, ts in enumerate(calendar) if ts.date().isoformat() > signal_date]
    if len(after) < delay:
        return None
    idx = after[delay - 1]
    return idx, calendar[idx]


def _prices_for(cohort: dict[str, Any], asof: date, loader: Callable[[str, date, date], pd.Series]) -> dict[str, pd.Series]:
    program = cohort["program_id"]
    symbols = list(cohort["symbols"])
    if program == "HOMEBUILDERS":
        required = symbols + ["ITB", "QQQ"]
    else:
        required = symbols + ["SMH", "QQQ"]
    start = date.fromisoformat(cohort["signal_date"]) - timedelta(days=10)
    out: dict[str, pd.Series] = {}
    for symbol in dict.fromkeys(required):
        out[symbol] = loader(symbol, start, asof)
    return out


def _resolve_homebuilders(cohort: dict[str, Any], prices: dict[str, pd.Series], is_new: bool) -> dict[str, Any]:
    symbols = list(cohort["symbols"])
    calendar = _common_calendar(prices, symbols + ["ITB", "QQQ"])
    entry = _first_entry(calendar, cohort["signal_date"], int(cohort["execution_delay_sessions"]))
    if entry is None:
        return {**cohort, "status": "AWAITING_ENTRY_SESSION", "resolution": None}
    entry_i, entry_ts = entry
    horizons = cohort["horizon_sessions_by_symbol"]
    matured = {s: entry_i + int(horizons[s]) < len(calendar) for s in symbols}
    if is_new and any(matured.values()):
        return {
            **cohort,
            "status": "LATE_REGISTRATION_REJECTED",
            "resolution": {
                "reason": "designated prospective outcome was already observable at first ledger registration",
                "entry_date": entry_ts.date().isoformat(),
            },
        }

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        horizon = int(horizons[symbol])
        exit_i = entry_i + horizon
        if exit_i >= len(calendar):
            mark_ts = calendar[-1]
            gross = _ret_bps(prices[symbol], entry_ts, mark_ts)
            net = gross - float(cohort["stock_round_trip_cost_bps"])
            itb = _ret_bps(prices["ITB"], entry_ts, mark_ts)
            qqq = _ret_bps(prices["QQQ"], entry_ts, mark_ts)
            rows.append({
                "symbol": symbol,
                "status": "OPEN",
                "horizon_sessions": horizon,
                "entry_date": entry_ts.date().isoformat(),
                "sessions_completed": max(0, len(calendar) - 1 - entry_i),
                "current_mark": {
                    "nonterminal": True,
                    "mark_date": mark_ts.date().isoformat(),
                    "gross_return_bps": round(gross, 4),
                    "net_if_flattened_now_bps": round(net, 4),
                    "itb_return_bps": round(itb, 4),
                    "qqq_return_bps": round(qqq, 4),
                    "matched_excess_vs_itb_bps": round(net - itb, 4),
                    "opportunity_excess_vs_qqq_bps": round(net - qqq, 4),
                    "net_positive": bool(net > 0),
                },
                "admission_score_fixed20_net25_bps": cohort.get("admission_score_fixed20_net25_bps", {}).get(symbol),
            })
            continue
        exit_ts = calendar[exit_i]
        gross = _ret_bps(prices[symbol], entry_ts, exit_ts)
        net = gross - float(cohort["stock_round_trip_cost_bps"])
        itb = _ret_bps(prices["ITB"], entry_ts, exit_ts)
        qqq = _ret_bps(prices["QQQ"], entry_ts, exit_ts)
        rows.append({
            "symbol": symbol,
            "status": "RESOLVED",
            "horizon_sessions": horizon,
            "entry_date": entry_ts.date().isoformat(),
            "exit_date": exit_ts.date().isoformat(),
            "gross_return_bps": round(gross, 4),
            "net_return_bps": round(net, 4),
            "itb_return_bps": round(itb, 4),
            "qqq_return_bps": round(qqq, 4),
            "excess_vs_itb_bps": round(net - itb, 4),
            "excess_vs_qqq_bps": round(net - qqq, 4),
            "net_positive": bool(net > 0),
            "admission_score_fixed20_net25_bps": cohort.get("admission_score_fixed20_net25_bps", {}).get(symbol),
        })

    resolved = [r for r in rows if r["status"] == "RESOLVED"]
    status = "RESOLVED" if len(resolved) == len(rows) else ("PARTIALLY_RESOLVED" if resolved else "OPEN")
    summary = None
    if resolved:
        summary = {
            "resolved_observations": len(resolved),
            "positive_observations": sum(1 for r in resolved if r["net_positive"]),
            "mean_net_return_bps": round(sum(r["net_return_bps"] for r in resolved) / len(resolved), 4),
            "mean_excess_vs_itb_bps": round(sum(r["excess_vs_itb_bps"] for r in resolved) / len(resolved), 4),
            "mean_excess_vs_qqq_bps": round(sum(r["excess_vs_qqq_bps"] for r in resolved) / len(resolved), 4),
        }
    current_rows = []
    for row in rows:
        if row["status"] == "RESOLVED":
            current_rows.append({
                "predicted": row.get("admission_score_fixed20_net25_bps"),
                "net": row.get("net_return_bps"),
                "excess": row.get("excess_vs_itb_bps"),
                "positive": row.get("net_positive"),
            })
        else:
            mark = row.get("current_mark") or {}
            current_rows.append({
                "predicted": row.get("admission_score_fixed20_net25_bps"),
                "net": mark.get("net_if_flattened_now_bps"),
                "excess": mark.get("matched_excess_vs_itb_bps"),
                "positive": mark.get("net_positive"),
            })
    usable = [row for row in current_rows if row["predicted"] is not None and row["net"] is not None]
    current_metrics = _prediction_metrics(
        [float(row["predicted"]) for row in usable],
        [float(row["net"]) for row in usable],
    )
    excess_values = [float(row["excess"]) for row in current_rows if row["excess"] is not None]
    current_metrics.update({
        "nonterminal": status != "RESOLVED",
        "mean_matched_excess_vs_itb_bps": None if not excess_values else round(sum(excess_values) / len(excess_values), 4),
        "net_positive_hit_rate": None if not current_rows else round(sum(bool(row["positive"]) for row in current_rows) / len(current_rows), 6),
    })
    required = symbols + ["ITB", "QQQ"]
    return {
        **cohort,
        "status": status,
        "source_health": _source_health(prices, required),
        "resolution": {
            "common_entry_date": entry_ts.date().isoformat(),
            "common_market_latest_date": calendar[-1].date().isoformat() if len(calendar) else None,
            "observations": rows,
            "summary": summary,
            "current_mark_metrics": current_metrics,
        },
    }


def _resolve_semiconductor(cohort: dict[str, Any], prices: dict[str, pd.Series], is_new: bool) -> dict[str, Any]:
    symbols = list(cohort["symbols"])
    calendar = _common_calendar(prices, symbols + ["SMH", "QQQ"])
    entry = _first_entry(calendar, cohort["signal_date"], int(cohort["execution_delay_sessions"]))
    if entry is None:
        return {**cohort, "status": "AWAITING_ENTRY_SESSION", "resolution": None}
    entry_i, entry_ts = entry
    horizon = int(cohort["holding_horizon_sessions"])
    exit_i = entry_i + horizon
    if is_new and exit_i < len(calendar):
        return {
            **cohort,
            "status": "LATE_REGISTRATION_REJECTED",
            "resolution": {
                "reason": "designated prospective outcome was already observable at first ledger registration",
                "entry_date": entry_ts.date().isoformat(),
            },
        }
    if exit_i >= len(calendar):
        mark_ts = calendar[-1]
        stock_cost = float(cohort["stock_round_trip_cost_bps"])
        predicted = cohort.get("predicted_fixed20_net_value_bps", {})
        marks: dict[str, dict[str, Any]] = {}
        for symbol in symbols:
            gross = _ret_bps(prices[symbol], entry_ts, mark_ts)
            net = gross - stock_cost
            pred = predicted.get(symbol)
            marks[symbol] = {
                "predicted_fixed20_net_value_bps": pred,
                "gross_return_bps": round(gross, 4),
                "net_if_flattened_now_bps": round(net, 4),
                "sign_hit_current": bool(net > 0),
                "partial_prediction_error_bps_nonterminal": None if pred is None else round(net - float(pred), 4),
            }
        smh = _ret_bps(prices["SMH"], entry_ts, mark_ts)
        qqq = _ret_bps(prices["QQQ"], entry_ts, mark_ts)
        ew = sum(float(row["gross_return_bps"]) for row in marks.values()) / len(marks)
        weights = cohort["ticker_book_weights_within_cohort"]
        ticker_gross = sum(float(weights.get(symbol, 0.0)) * float(marks[symbol]["gross_return_bps"]) for symbol in symbols)
        ticker_net = ticker_gross - stock_cost
        usable = [
            (float(row["predicted_fixed20_net_value_bps"]), float(row["net_if_flattened_now_bps"]))
            for row in marks.values()
            if row["predicted_fixed20_net_value_bps"] is not None
        ]
        metrics = _prediction_metrics([x[0] for x in usable], [x[1] for x in usable])
        metrics.update({
            "nonterminal": True,
            "mark_date": mark_ts.date().isoformat(),
            "ticker_positive_hit_rate": round(sum(bool(row["sign_hit_current"]) for row in marks.values()) / len(marks), 6),
            "ticker_book_net_if_flattened_now_bps": round(ticker_net, 4),
            "ticker_book_matched_excess_vs_smh_bps": round(ticker_net - smh, 4),
            "ticker_book_opportunity_excess_vs_qqq_bps": round(ticker_net - qqq, 4),
            "ticker_book_excess_vs_equal_weight_universe_bps": round(ticker_net - ew, 4),
            "smh_return_bps": round(smh, 4),
            "qqq_return_bps": round(qqq, 4),
            "equal_weight_universe_return_bps": round(ew, 4),
            "calibration_interpretation": "partial-horizon diagnostic only; terminal fixed20 calibration remains authoritative",
        })
        required = symbols + ["SMH", "QQQ"]
        return {
            **cohort,
            "status": "OPEN",
            "source_health": _source_health(prices, required),
            "resolution": {
                "entry_date": entry_ts.date().isoformat(),
                "horizon_sessions": horizon,
                "sessions_completed": max(0, len(calendar) - 1 - entry_i),
                "common_market_latest_date": calendar[-1].date().isoformat() if len(calendar) else None,
                "current_ticker_marks": marks,
                "current_mark_metrics": metrics,
            },
        }

    exit_ts = calendar[exit_i]
    stock_cost = float(cohort["stock_round_trip_cost_bps"])
    realized: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        gross = _ret_bps(prices[symbol], entry_ts, exit_ts)
        net = gross - stock_cost
        pred = cohort.get("predicted_fixed20_net_value_bps", {}).get(symbol)
        realized[symbol] = {
            "gross_return_bps": round(gross, 4),
            "net_return_bps": round(net, 4),
            "predicted_net_value_bps": pred,
            "prediction_error_bps": None if pred is None else round(net - float(pred), 4),
            "sign_hit": bool(net > 0),
        }

    weights = cohort["ticker_book_weights_within_cohort"]
    ticker_gross = sum(float(weights.get(s, 0.0)) * realized[s]["gross_return_bps"] for s in symbols)
    ticker_net = ticker_gross - stock_cost
    smh = _ret_bps(prices["SMH"], entry_ts, exit_ts)
    qqq = _ret_bps(prices["QQQ"], entry_ts, exit_ts)
    ew13 = sum(realized[s]["gross_return_bps"] for s in symbols) / len(symbols)
    industry_net = smh - float(cohort["industry_round_trip_cost_bps"])
    abs_errors = [abs(float(v["prediction_error_bps"])) for v in realized.values() if v["prediction_error_bps"] is not None]
    usable = [
        (float(v["predicted_net_value_bps"]), float(v["net_return_bps"]))
        for v in realized.values()
        if v["predicted_net_value_bps"] is not None
    ]
    terminal_metrics = _prediction_metrics([x[0] for x in usable], [x[1] for x in usable])
    required = symbols + ["SMH", "QQQ"]

    return {
        **cohort,
        "status": "RESOLVED",
        "source_health": _source_health(prices, required),
        "resolution": {
            "entry_date": entry_ts.date().isoformat(),
            "exit_date": exit_ts.date().isoformat(),
            "horizon_sessions": horizon,
            "ticker_observations": realized,
            "ticker_book_gross_return_bps": round(ticker_gross, 4),
            "ticker_book_net_return_bps": round(ticker_net, 4),
            "industry_book_smh_net_return_bps": round(industry_net, 4),
            "benchmarks": {
                "cash_return_bps": 0.0,
                "smh_buy_and_hold_return_bps": round(smh, 4),
                "qqq_buy_and_hold_return_bps": round(qqq, 4),
                "equal_weight_13_return_bps": round(ew13, 4),
            },
            "ticker_book_excess_vs_smh_bps": round(ticker_net - smh, 4),
            "ticker_book_excess_vs_qqq_bps": round(ticker_net - qqq, 4),
            "ticker_book_excess_vs_equal_weight_13_bps": round(ticker_net - ew13, 4),
            "ticker_book_excess_vs_cash_bps": round(ticker_net, 4),
            "ticker_positive_hit_rate": round(sum(1 for v in realized.values() if v["sign_hit"]) / len(realized), 6),
            "prediction_mae_bps": None if not abs_errors else round(sum(abs_errors) / len(abs_errors), 4),
            "rank_ic_spearman": terminal_metrics["rank_ic_spearman"],
            "calibration_intercept_bps": terminal_metrics["calibration_intercept_bps"],
            "calibration_slope": terminal_metrics["calibration_slope"],
        },
    }


def _advance_cohort(cohort: dict[str, Any], is_new: bool, asof: date, loader: Callable[[str, date, date], pd.Series]) -> dict[str, Any]:
    if cohort.get("status") in {"RESOLVED", "LATE_REGISTRATION_REJECTED"}:
        return cohort
    prices = _prices_for(cohort, asof, loader)
    if cohort["program_id"] == "HOMEBUILDERS":
        return _resolve_homebuilders(cohort, prices, is_new)
    return _resolve_semiconductor(cohort, prices, is_new)


def _summary(cohorts: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for program in sorted(SUPPORTED):
        rows = [c for c in cohorts if c["program_id"] == program]
        resolved = [c for c in rows if c["status"] == "RESOLVED"]
        out[program] = {
            "registered_cohorts": len(rows),
            "resolved_cohorts": len(resolved),
            "open_cohorts": sum(c["status"] in {"REGISTERED", "AWAITING_ENTRY_SESSION", "OPEN", "PARTIALLY_RESOLVED"} for c in rows),
            "late_registration_rejections": sum(c["status"] == "LATE_REGISTRATION_REJECTED" for c in rows),
            "minimum_resolved_for_promotion": CONTRACTS[program]["minimum_resolved_for_promotion"],
            "promotion_authority": False,
        }
        if program == "HOMEBUILDERS":
            obs = []
            for c in rows:
                obs.extend(((c.get("resolution") or {}).get("observations") or []))
            done = [r for r in obs if r.get("status") == "RESOLVED"]
            out[program]["resolved_observations"] = len(done)
            out[program]["positive_hit_rate"] = None if not done else round(sum(bool(r["net_positive"]) for r in done) / len(done), 6)
            out[program]["mean_excess_vs_itb_bps"] = None if not done else round(sum(float(r["excess_vs_itb_bps"]) for r in done) / len(done), 4)
        else:
            if resolved:
                out[program]["mean_ticker_book_excess_vs_smh_bps"] = round(
                    sum(float(c["resolution"]["ticker_book_excess_vs_smh_bps"]) for c in resolved) / len(resolved), 4
                )
                out[program]["mean_ticker_positive_hit_rate"] = round(
                    sum(float(c["resolution"]["ticker_positive_hit_rate"]) for c in resolved) / len(resolved), 6
                )
            else:
                out[program]["mean_ticker_book_excess_vs_smh_bps"] = None
                out[program]["mean_ticker_positive_hit_rate"] = None
    return out


def _observed_market_data_asof(cohorts: list[dict[str, Any]], requested: date) -> str:
    """Return the latest date supported by every active cohort's common tape.

    The requested UTC date can be ahead of the latest completed market close. Using
    it as market_data_asof overstates freshness, so active cohorts with explicit
    common_market_latest_date govern. Resolved cohorts no longer constrain current
    freshness because their terminal outcome is already fixed.
    """
    active = {"REGISTERED", "AWAITING_ENTRY_SESSION", "OPEN", "PARTIALLY_RESOLVED"}
    observed: list[str] = []
    for cohort in cohorts:
        if str(cohort.get("status") or "") not in active:
            continue
        latest = str(((cohort.get("resolution") or {}).get("common_market_latest_date") or ""))[:10]
        if latest:
            observed.append(latest)
    return min(observed) if observed else requested.isoformat()


def build(
    adapter_dir: Path,
    prior: dict[str, Any] | None,
    asof: date,
    now_iso: str,
    loader: Callable[[str, date, date], pd.Series] = _download_close,
) -> dict[str, Any]:
    existing = {str(c["cohort_id"]): dict(c) for c in ((prior or {}).get("cohorts") or [])}
    discovered: dict[str, dict[str, Any]] = {}
    for filename in ("homebuilders.json", "semiconductor_shared_ridge.json"):
        path = adapter_dir / filename
        if not path.is_file():
            continue
        adapter, digest = _adapter(path)
        cohort = _new_cohort(adapter, digest, now_iso)
        if cohort is not None:
            discovered[cohort["cohort_id"]] = cohort

    cohorts: list[dict[str, Any]] = []
    for cohort_id in sorted(set(existing) | set(discovered)):
        is_new = cohort_id not in existing
        cohort = discovered[cohort_id] if is_new else existing[cohort_id]
        cohorts.append(_advance_cohort(cohort, is_new, asof, loader))

    observed_asof = _observed_market_data_asof(cohorts, asof)
    source_health = {
        str(cohort.get("program_id")): cohort.get("source_health")
        for cohort in cohorts
        if cohort.get("source_health")
    }
    lagging = {
        program: health.get("lagging_symbols_vs_source_max")
        for program, health in source_health.items()
        if health.get("lagging_symbols_vs_source_max")
    }
    return {
        "schema": SCHEMA,
        "generated_at": now_iso,
        "requested_market_data_asof": asof.isoformat(),
        "market_data_asof": observed_asof,
        "freshness": {
            "requested_asof": asof.isoformat(),
            "observed_common_asof": observed_asof,
            "source_health_by_program": source_health,
            "lagging_symbols_by_program": lagging,
            "freshness_gap_visible": observed_asof < asof.isoformat(),
            "freshness_gap_note": "A requested/observed gap may be a non-session day; consumers must compare against the expected completed exchange session before classifying stale data.",
        },
        "cohorts": cohorts,
        "summary": _summary(cohorts),
        "boundaries": {
            "research_only": True,
            "broker_action": False,
            "live_trading_change": False,
            "allocation_authority": False,
            "promotion_authority": False,
            "no_outcome_backfill_after_maturity": True,
            "signal_or_horizon_mutation": False,
        },
    }


def self_test() -> None:
    dates = pd.to_datetime([
        "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15",
    ])
    fake: dict[str, pd.Series] = {}
    for i, symbol in enumerate(["CCS", "ITB", "QQQ"]):
        fake[symbol] = pd.Series([100 + i + j for j in range(len(dates))], index=dates, dtype=float)

    def loader(symbol: str, _start: date, _end: date) -> pd.Series:
        series = fake[symbol]
        return series[series.index <= pd.Timestamp(_end)]

    cohort = {
        "cohort_id": "HOMEBUILDERS:2026-01-02:test",
        "program_id": "HOMEBUILDERS",
        "signal_date": "2026-01-02",
        "source_adapter_sha256": "test",
        "source_ref": "test",
        "first_registered_at": "2026-01-03T00:00:00+00:00",
        "status": "REGISTERED",
        "execution_delay_sessions": 1,
        "symbols": ["CCS"],
        "horizon_sessions_by_symbol": {"CCS": 5},
        "admission_score_fixed20_net25_bps": {"CCS": 100.0},
        "benchmarks": ["ITB", "QQQ"],
        "stock_round_trip_cost_bps": 25.0,
        "resolution": None,
    }
    open_row = _advance_cohort(cohort, True, date(2026, 1, 8), loader)
    assert open_row["status"] == "OPEN"
    assert open_row["resolution"]["observations"][0]["current_mark"]["nonterminal"] is True
    assert open_row["resolution"]["current_mark_metrics"]["nonterminal"] is True
    assert open_row["source_health"]["all_symbols_share_latest_date"] is True
    assert _observed_market_data_asof([open_row], date(2026, 1, 9)) == "2026-01-08"
    late = _advance_cohort(cohort, True, date(2026, 1, 15), loader)
    assert late["status"] == "LATE_REGISTRATION_REJECTED"
    resolved = _advance_cohort(open_row, False, date(2026, 1, 15), loader)
    assert resolved["status"] == "RESOLVED"
    obs = resolved["resolution"]["observations"][0]
    assert obs["entry_date"] == "2026-01-05"
    assert obs["exit_date"] == "2026-01-12"
    assert obs["net_return_bps"] < obs["gross_return_bps"]
    print("FORWARD_PROSPECTIVE_COHORT_LEDGER_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--adapter-dir", default="research/current/native_adapters")
    p.add_argument("--prior", default="research/current/forward_prospective_cohort_ledger_r1.json")
    p.add_argument("--output")
    p.add_argument("--asof")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.output:
        p.error("--output is required unless --self-test")
    now = datetime.now(timezone.utc)
    asof = date.fromisoformat(args.asof) if args.asof else now.date()
    prior = _read_json(Path(args.prior)) if args.prior else None
    result = build(Path(args.adapter_dir), prior, asof, now.isoformat())
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"summary": result["summary"], "cohorts": [(c["cohort_id"], c["status"]) for c in result["cohorts"]]}, sort_keys=True))


if __name__ == "__main__":
    main()
