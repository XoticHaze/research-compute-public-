from __future__ import annotations

"""Prospective observation-only tape for GENERALIZED_LARGECAP_RIDGE.

The source adapter already freezes signal date, +1-session entry, fixed-20 horizon,
positive/negative direction, and SPY/QQQ controls. This observer measures that contract
without granting sizing, promotion, broker, or live-trading authority. The adapter does
not freeze a transaction-cost contract, so prediction-error/net calibration remains
explicitly unavailable; current and terminal marks are gross plus matched-control excess.
"""

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

SCHEMA = "research.forward_generalized_largecap_observation_r1"
ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"
PROGRAM_ID = "GENERALIZED_LARGECAP_RIDGE"
BENCHMARKS = ("SPY", "QQQ")


def _normalize(series: pd.Series) -> pd.Series:
    x = series.dropna().astype(float).copy()
    idx = pd.to_datetime(x.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(None)
    x.index = pd.DatetimeIndex(idx).normalize()
    return x[~x.index.duplicated(keep="last")].sort_index()


def _download(symbol: str, start: date, end: date) -> pd.Series:
    import yfinance as yf

    frame = yf.download(
        symbol,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if frame.empty:
        raise RuntimeError(f"no market data symbol={symbol}")
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        if close.shape[1] != 1:
            raise RuntimeError(f"ambiguous close columns symbol={symbol}")
        close = close.iloc[:, 0]
    return _normalize(close)


def _common_calendar(prices: dict[str, pd.Series], symbols: list[str]) -> pd.DatetimeIndex:
    sets = [set(prices[s].index) for s in symbols]
    if not sets:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted(set.intersection(*sets)))


def _first_entry(calendar: pd.DatetimeIndex, signal_date: str, delay: int) -> tuple[int, pd.Timestamp] | None:
    after = [i for i, ts in enumerate(calendar) if ts.date().isoformat() > signal_date]
    if len(after) < delay:
        return None
    i = after[delay - 1]
    return i, calendar[i]


def _ret_bps(series: pd.Series, entry: pd.Timestamp, exit_: pd.Timestamp) -> float:
    return float((series.loc[exit_] / series.loc[entry] - 1.0) * 10000.0)


def _validate_adapter(adapter: dict[str, Any]) -> None:
    if adapter.get("schema") != ADAPTER_SCHEMA:
        raise RuntimeError(f"unexpected adapter schema {adapter.get('schema')}")
    if adapter.get("program_id") != PROGRAM_ID:
        raise RuntimeError(f"unexpected program {adapter.get('program_id')}")
    boundaries = adapter.get("boundaries") or {}
    for key in ("allocation_authority", "broker_action", "live_trading_change", "runtime_mutation", "promotion_authority"):
        if boundaries.get(key) is not False:
            raise RuntimeError(f"largecap observer requires false boundary {key}")
    timing = adapter.get("timing") or {}
    if int(timing.get("execution_delay_sessions", -1)) != 1:
        raise RuntimeError("largecap observer requires frozen +1-session execution delay")
    if int(timing.get("holding_horizon_sessions", -1)) != 20:
        raise RuntimeError("largecap observer requires frozen 20-session horizon")
    benchmarks = set(adapter.get("benchmarks") or [])
    if not set(BENCHMARKS).issubset(benchmarks):
        raise RuntimeError("largecap observer requires frozen SPY and QQQ controls")


def build(
    adapter: dict[str, Any],
    adapter_raw: bytes,
    asof: date,
    now_iso: str,
    loader: Callable[[str, date, date], pd.Series] = _download,
) -> dict[str, Any]:
    _validate_adapter(adapter)
    signal = adapter.get("signal") or {}
    predictions = {str(k): float(v) for k, v in (signal.get("predicted_fixed20_net_value_bps") or {}).items()}
    positive = [str(x) for x in (signal.get("positive_symbols") or [])]
    negative = [str(x) for x in (signal.get("negative_symbols") or [])]
    symbols = list(dict.fromkeys(positive + negative))
    if not symbols:
        raise RuntimeError("largecap observer has no frozen signal symbols")
    if set(symbols) - set(predictions):
        raise RuntimeError("largecap observer symbol missing frozen prediction")

    signal_date = str(adapter.get("signal_date") or "")[:10]
    start = date.fromisoformat(signal_date) - timedelta(days=10)
    required = symbols + list(BENCHMARKS)
    prices = {s: loader(s, start, asof) for s in required}
    calendar = _common_calendar(prices, required)
    entry = _first_entry(calendar, signal_date, 1)

    base: dict[str, Any] = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "generated_at": now_iso,
        "requested_asof": asof.isoformat(),
        "signal_date": signal_date,
        "source_adapter_sha256": hashlib.sha256(adapter_raw).hexdigest(),
        "source_adapter_contract_commit": "f439f34394356e03b82328b0827a7d637ab29faf",
        "timing": {
            "execution_delay_sessions": 1,
            "holding_horizon_sessions": 20,
        },
        "symbols": symbols,
        "positive_symbols": positive,
        "negative_symbols": negative,
        "predicted_fixed20_net_value_bps": predictions,
        "benchmarks": list(BENCHMARKS),
        "sector_benchmark_status": "UNRESOLVED_CONTRACT",
        "transaction_cost_contract_status": "NOT_FROZEN_IN_ADAPTER",
        "prediction_error_status": "UNAVAILABLE_UNTIL_COST_CONTRACT_IS_FROZEN",
        "boundaries": {
            "research_only": True,
            "allocation_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "promotion_authority": False,
            "signal_mutation": False,
            "horizon_mutation": False,
        },
    }

    if entry is None:
        return {
            **base,
            "state": "AWAITING_ENTRY_SESSION",
            "market_latest_date": None if len(calendar) == 0 else calendar[-1].date().isoformat(),
            "entry_date": None,
            "sessions_completed": 0,
            "observations": [],
            "mark_to_market_scorecard": None,
            "formal_resolved_scorecard": None,
        }

    entry_i, entry_ts = entry
    horizon = 20
    exit_i = entry_i + horizon
    resolved = exit_i < len(calendar)
    mark_ts = calendar[exit_i] if resolved else calendar[-1]
    sessions_completed = horizon if resolved else max(0, len(calendar) - 1 - entry_i)
    spy = _ret_bps(prices["SPY"], entry_ts, mark_ts)
    qqq = _ret_bps(prices["QQQ"], entry_ts, mark_ts)

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        gross = _ret_bps(prices[symbol], entry_ts, mark_ts)
        pred = float(predictions[symbol])
        direction = 1.0 if pred >= 0 else -1.0
        directed_absolute = direction * gross
        directed_spy = direction * (gross - spy)
        directed_qqq = direction * (gross - qqq)
        rows.append({
            "symbol": symbol,
            "predicted_fixed20_net_value_bps": pred,
            "predicted_direction": "POSITIVE" if direction > 0 else "NEGATIVE",
            "gross_return_bps": round(gross, 4),
            "spy_return_bps": round(spy, 4),
            "qqq_return_bps": round(qqq, 4),
            "directional_absolute_bps": round(directed_absolute, 4),
            "directional_excess_vs_spy_bps": round(directed_spy, 4),
            "directional_excess_vs_qqq_bps": round(directed_qqq, 4),
            "absolute_direction_hit": bool(directed_absolute > 0),
            "relative_vs_spy_hit": bool(directed_spy > 0),
            "relative_vs_qqq_hit": bool(directed_qqq > 0),
            "prediction_error_bps": None,
        })

    def rate(key: str) -> float:
        return round(sum(bool(r[key]) for r in rows) / len(rows), 6)

    mark_scorecard = {
        "observation_count": len(rows),
        "absolute_direction_hit_rate": rate("absolute_direction_hit"),
        "relative_vs_spy_hit_rate": rate("relative_vs_spy_hit"),
        "relative_vs_qqq_hit_rate": rate("relative_vs_qqq_hit"),
        "mean_directional_absolute_bps": round(sum(float(r["directional_absolute_bps"]) for r in rows) / len(rows), 4),
        "mean_directional_excess_vs_spy_bps": round(sum(float(r["directional_excess_vs_spy_bps"]) for r in rows) / len(rows), 4),
        "mean_directional_excess_vs_qqq_bps": round(sum(float(r["directional_excess_vs_qqq_bps"]) for r in rows) / len(rows), 4),
    }

    return {
        **base,
        "state": "RESOLVED" if resolved else "PROSPECTIVE_OPEN",
        "market_latest_date": calendar[-1].date().isoformat(),
        "entry_date": entry_ts.date().isoformat(),
        "mark_date": mark_ts.date().isoformat(),
        "exit_date": mark_ts.date().isoformat() if resolved else None,
        "sessions_completed": sessions_completed,
        "observations": rows,
        "mark_to_market_scorecard": mark_scorecard,
        "formal_resolved_scorecard": mark_scorecard if resolved else None,
    }


def self_test() -> None:
    dates = pd.to_datetime([
        "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
        "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15",
        "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22", "2026-01-23",
        "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30",
        "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    ])
    fake: dict[str, pd.Series] = {
        "CAT": pd.Series([100 + i for i in range(len(dates))], index=dates, dtype=float),
        "XOM": pd.Series([100 - 0.5 * i for i in range(len(dates))], index=dates, dtype=float),
        "SPY": pd.Series([100 + 0.2 * i for i in range(len(dates))], index=dates, dtype=float),
        "QQQ": pd.Series([100 + 0.3 * i for i in range(len(dates))], index=dates, dtype=float),
    }

    def loader(symbol: str, _start: date, end: date) -> pd.Series:
        x = fake[symbol]
        return x[x.index <= pd.Timestamp(end)]

    adapter = {
        "schema": ADAPTER_SCHEMA,
        "program_id": PROGRAM_ID,
        "signal_date": "2026-01-02",
        "signal": {
            "positive_symbols": ["CAT"],
            "negative_symbols": ["XOM"],
            "predicted_fixed20_net_value_bps": {"CAT": 100.0, "XOM": -100.0},
        },
        "timing": {"execution_delay_sessions": 1, "holding_horizon_sessions": 20},
        "benchmarks": ["SPY", "QQQ", "appropriate_sector_or_industry_benchmark"],
        "boundaries": {
            "allocation_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "runtime_mutation": False,
            "promotion_authority": False,
        },
    }
    raw = json.dumps(adapter, sort_keys=True).encode()
    open_result = build(adapter, raw, date(2026, 1, 15), "2026-01-15T00:00:00+00:00", loader)
    assert open_result["state"] == "PROSPECTIVE_OPEN"
    assert open_result["formal_resolved_scorecard"] is None
    assert open_result["mark_to_market_scorecard"]["absolute_direction_hit_rate"] == 1.0
    resolved = build(adapter, raw, date(2026, 2, 6), "2026-02-06T00:00:00+00:00", loader)
    assert resolved["state"] == "RESOLVED"
    assert resolved["sessions_completed"] == 20
    assert resolved["formal_resolved_scorecard"]["absolute_direction_hit_rate"] == 1.0
    assert all(r["prediction_error_bps"] is None for r in resolved["observations"])
    print("FORWARD_GENERALIZED_LARGECAP_OBSERVER_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--adapter")
    p.add_argument("--output")
    p.add_argument("--asof")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.adapter or not args.output:
        p.error("--adapter and --output are required unless --self-test")
    adapter_path = Path(args.adapter)
    raw = adapter_path.read_bytes()
    adapter = json.loads(raw)
    now = datetime.now(timezone.utc)
    asof = date.fromisoformat(args.asof) if args.asof else now.date()
    result = build(adapter, raw, asof, now.isoformat())
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": result["state"],
        "entry_date": result["entry_date"],
        "sessions_completed": result["sessions_completed"],
        "market_latest_date": result["market_latest_date"],
        "mark_to_market_scorecard": result["mark_to_market_scorecard"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
