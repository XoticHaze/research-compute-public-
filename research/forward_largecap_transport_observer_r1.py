from __future__ import annotations

"""Observation-only prospective tape for the generalized large-cap Ridge transport.

The source adapter already freezes signal date, +1-session execution, fixed-20
horizon, positive/negative symbols, predictions, and SPY/QQQ benchmarks. This
observer measures those frozen signals without granting sizing, allocation,
promotion, broker, or live-trading authority.

The adapter's predictions are labelled net values but do not carry an explicit
transaction-cost contract. Therefore this tape scores direction and gross matched
excess only; prediction-magnitude calibration remains deliberately blocked.
"""

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

SCHEMA = "research.forward_largecap_transport_observation_r1"
ADAPTER_SCHEMA = "foundry.forward_program_adapter.v1"
SCOREBOARD_SCHEMA = "research.forward_market_scoreboard_r1"
PROGRAM_ID = "GENERALIZED_LARGECAP_RIDGE"

# Recovery evidence for the earliest durable observer publication. The initial
# artifact predated the first_registered_at field, so generated_at is the correct
# registration anchor. This is provenance repair only, not model science.
# Evidence commit: ae327a88bf02dc55f596416ad563375b0cd076d7.
RECOVERED_REGISTRATION_ANCHORS = {
    "2026-09-11": {
        "first_registered_at": "2026-09-18T05:03:20.113496+00:00",
        "evidence_commit": "ae327a88bf02dc55f596416ad563375b0cd076d7",
    },
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
    return _normalize_series(close)


def _common_calendar(prices: dict[str, pd.Series], symbols: list[str]) -> pd.DatetimeIndex:
    sets = [set(prices[s].index) for s in symbols]
    if not sets:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted(set.intersection(*sets)))


def _ret_bps(series: pd.Series, entry: pd.Timestamp, exit_: pd.Timestamp) -> float:
    return float((series.loc[exit_] / series.loc[entry] - 1.0) * 10000.0)


def _first_entry(calendar: pd.DatetimeIndex, signal_date: str, delay: int) -> tuple[int, pd.Timestamp] | None:
    after = [i for i, ts in enumerate(calendar) if ts.date().isoformat() > signal_date]
    if len(after) < delay:
        return None
    idx = after[delay - 1]
    return idx, calendar[idx]


def _validate_adapter(adapter: dict[str, Any]) -> None:
    if adapter.get("schema") != ADAPTER_SCHEMA:
        raise RuntimeError(f"unexpected adapter schema {adapter.get('schema')}")
    if adapter.get("program_id") != PROGRAM_ID:
        raise RuntimeError(f"unexpected adapter program {adapter.get('program_id')}")
    boundaries = adapter.get("boundaries") or {}
    for key in ("allocation_authority", "broker_action", "live_trading_change", "runtime_mutation", "promotion_authority"):
        if boundaries.get(key) is not False:
            raise RuntimeError(f"adapter boundary must remain false key={key}")
    timing = adapter.get("timing") or {}
    if int(timing.get("execution_delay_sessions", 0)) != 1:
        raise RuntimeError("large-cap transport must retain +1-session execution")
    if int(timing.get("holding_horizon_sessions", 0)) != 20:
        raise RuntimeError("large-cap transport must retain fixed20 horizon")


def build(
    adapter: dict[str, Any],
    asof: date,
    now_iso: str,
    loader: Callable[[str, date, date], pd.Series] = _download_close,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_adapter(adapter)
    signal = adapter.get("signal") or {}
    positive = [str(x) for x in signal.get("positive_symbols") or []]
    negative = [str(x) for x in signal.get("negative_symbols") or []]
    symbols = positive + [x for x in negative if x not in positive]
    if not symbols:
        raise RuntimeError("large-cap transport has no symbols")

    signal_date = str(adapter.get("signal_date") or "")[:10]
    if not signal_date:
        raise RuntimeError("large-cap transport missing signal_date")
    timing = adapter.get("timing") or {}
    delay = int(timing["execution_delay_sessions"])
    horizon = int(timing["holding_horizon_sessions"])
    prior_is_same_signal = bool(
        prior
        and prior.get("schema") == SCHEMA
        and prior.get("program_id") == PROGRAM_ID
        and prior.get("signal_date") == signal_date
        and prior.get("first_registered_at")
    )
    recovered = RECOVERED_REGISTRATION_ANCHORS.get(signal_date)
    recovered_first = None if recovered is None else str(recovered["first_registered_at"])
    candidates = [now_iso]
    if prior_is_same_signal:
        candidates.append(str(prior["first_registered_at"]))
    if recovered_first:
        candidates.append(recovered_first)
    first_registered_at = min(candidates, key=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")))
    registration_evidence_present = prior_is_same_signal or recovered is not None
    registration_anchor_source = (
        {"kind": "repo_history_recovery", **recovered}
        if recovered_first and first_registered_at == recovered_first
        else {"kind": "prior_current_artifact" if prior_is_same_signal else "current_run"}
    )
    required = symbols + ["SPY", "QQQ"]
    start = date.fromisoformat(signal_date) - timedelta(days=10)
    prices = {s: loader(s, start, asof) for s in dict.fromkeys(required)}
    latest_by_symbol = {
        symbol: (None if prices[symbol].empty else pd.Timestamp(prices[symbol].index.max()).date().isoformat())
        for symbol in required
    }
    dated = [value for value in latest_by_symbol.values() if value]
    source_max_date = max(dated) if dated else None
    source_health = {
        "provider": "yfinance_adjusted_close",
        "source_max_date": source_max_date,
        "latest_by_symbol": latest_by_symbol,
        "lagging_symbols_vs_source_max": sorted(
            symbol for symbol, value in latest_by_symbol.items()
            if source_max_date is not None and value != source_max_date
        ),
    }
    source_health["all_symbols_share_latest_date"] = (
        not source_health["lagging_symbols_vs_source_max"] and len(dated) == len(required)
    )
    calendar = _common_calendar(prices, required)

    entry = _first_entry(calendar, signal_date, delay)
    if entry is None:
        return {
            "schema": SCHEMA,
            "generated_at": now_iso,
            "market_data_asof": asof.isoformat(),
            "program_id": PROGRAM_ID,
            "signal_date": signal_date,
            "first_registered_at": first_registered_at,
            "registration_anchor_source": registration_anchor_source,
            "state": "AWAITING_ENTRY_SESSION",
            "source_health": source_health,
            "execution_delay_sessions": delay,
            "holding_horizon_sessions": horizon,
            "symbols": symbols,
            "boundaries": {
                "research_only": True,
                "allocation_authority": False,
                "promotion_authority": False,
                "broker_action": False,
                "live_trading_change": False,
                "transaction_cost_calibration_authority": False,
                "no_outcome_backfill_after_maturity": True,
            },
        }

    entry_i, entry_ts = entry
    sessions_completed = max(0, len(calendar) - 1 - entry_i)
    terminal = entry_i + horizon < len(calendar)
    if terminal and not registration_evidence_present:
        return {
            "schema": SCHEMA,
            "generated_at": now_iso,
            "market_data_asof": calendar[-1].date().isoformat(),
            "program_id": PROGRAM_ID,
            "signal_date": signal_date,
            "first_registered_at": first_registered_at,
            "registration_anchor_source": registration_anchor_source,
            "state": "LATE_REGISTRATION_REJECTED",
            "source_health": source_health,
            "entry_date": entry_ts.date().isoformat(),
            "execution_delay_sessions": delay,
            "holding_horizon_sessions": horizon,
            "sessions_completed": horizon,
            "benchmarks": ["SPY", "QQQ"],
            "observations": [],
            "summary": None,
            "rejection_reason": "fixed20 outcome was already observable before first durable observer registration",
            "boundaries": {
                "research_only": True,
                "allocation_authority": False,
                "promotion_authority": False,
                "broker_action": False,
                "live_trading_change": False,
                "sizing_book_created": False,
                "transaction_cost_calibration_authority": False,
                "no_outcome_backfill_after_maturity": True,
            },
        }
    eval_i = entry_i + horizon if terminal else len(calendar) - 1
    eval_ts = calendar[eval_i]
    spy = _ret_bps(prices["SPY"], entry_ts, eval_ts)
    qqq = _ret_bps(prices["QQQ"], entry_ts, eval_ts)
    predictions = {str(k): float(v) for k, v in (signal.get("predicted_fixed20_net_value_bps") or {}).items()}

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        direction = "POSITIVE" if symbol in positive else "NEGATIVE"
        sign = 1.0 if direction == "POSITIVE" else -1.0
        raw = _ret_bps(prices[symbol], entry_ts, eval_ts)
        directional = sign * raw
        rows.append({
            "symbol": symbol,
            "direction": direction,
            "predicted_fixed20_net_value_bps": predictions.get(symbol),
            "gross_return_bps": round(raw, 4),
            "directional_return_bps": round(directional, 4),
            "gross_sign_hit": bool(directional > 0),
            "directional_excess_vs_spy_bps": round(sign * (raw - spy), 4),
            "directional_excess_vs_qqq_bps": round(sign * (raw - qqq), 4),
            "prediction_error_bps": None,
            "prediction_calibration_status": "BLOCKED_NO_FROZEN_TRANSACTION_COST_CONTRACT",
        })

    pos_rows = [r for r in rows if r["direction"] == "POSITIVE"]
    neg_rows = [r for r in rows if r["direction"] == "NEGATIVE"]
    summary = {
        "observation_count": len(rows),
        "directional_sign_hit_rate": round(sum(bool(r["gross_sign_hit"]) for r in rows) / len(rows), 6),
        "positive_sign_hit_rate": None if not pos_rows else round(sum(bool(r["gross_sign_hit"]) for r in pos_rows) / len(pos_rows), 6),
        "negative_sign_hit_rate": None if not neg_rows else round(sum(bool(r["gross_sign_hit"]) for r in neg_rows) / len(neg_rows), 6),
        "mean_directional_return_bps": round(sum(float(r["directional_return_bps"]) for r in rows) / len(rows), 4),
        "mean_directional_excess_vs_spy_bps": round(sum(float(r["directional_excess_vs_spy_bps"]) for r in rows) / len(rows), 4),
        "mean_directional_excess_vs_qqq_bps": round(sum(float(r["directional_excess_vs_qqq_bps"]) for r in rows) / len(rows), 4),
        "spy_return_bps": round(spy, 4),
        "qqq_return_bps": round(qqq, 4),
    }
    return {
        "schema": SCHEMA,
        "generated_at": now_iso,
        "market_data_asof": calendar[-1].date().isoformat() if len(calendar) else asof.isoformat(),
        "program_id": PROGRAM_ID,
        "signal_date": signal_date,
        "first_registered_at": first_registered_at,
        "registration_anchor_source": registration_anchor_source,
        "state": "RESOLVED" if terminal else "PROSPECTIVE_OPEN",
        "source_health": {
            **source_health,
            "latest_common_session": calendar[-1].date().isoformat() if len(calendar) else None,
            "common_session_lags_source_max": bool(len(calendar) and source_max_date and calendar[-1].date().isoformat() < source_max_date),
        },
        "entry_date": entry_ts.date().isoformat(),
        "evaluation_date": eval_ts.date().isoformat(),
        "execution_delay_sessions": delay,
        "holding_horizon_sessions": horizon,
        "sessions_completed": min(sessions_completed, horizon),
        "benchmarks": ["SPY", "QQQ"],
        "observations": rows,
        "summary": summary,
        "interpretation": {
            "negative_signal_is_scored_as_directional_prediction_not_short_position": True,
            "current_mark_before_horizon_is_not_terminal_accuracy": not terminal,
            "prediction_magnitude_calibration_blocked_without_frozen_transaction_cost_contract": True,
        },
        "boundaries": {
            "research_only": True,
            "allocation_authority": False,
            "promotion_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "sizing_book_created": False,
            "transaction_cost_calibration_authority": False,
            "no_outcome_backfill_after_maturity": True,
        },
    }


def enrich_scoreboard(
    scoreboard: dict[str, Any],
    observation: dict[str, Any],
    observation_sha256: str | None = None,
) -> dict[str, Any]:
    if scoreboard.get("schema") != SCOREBOARD_SCHEMA:
        raise RuntimeError(f"unexpected scoreboard schema {scoreboard.get('schema')}")
    if observation.get("schema") != SCHEMA or observation.get("program_id") != PROGRAM_ID:
        raise RuntimeError("unexpected large-cap observation payload")

    lane = next((x for x in scoreboard.get("lanes", []) if x.get("program_id") == PROGRAM_ID), None)
    if lane is None:
        raise RuntimeError("large-cap lane missing from scoreboard")
    lane["forward_observation"] = observation
    lane["observation_status"] = "ACTIVE"
    lane.setdefault("observation_lineage", {}).update({
        "largecap_observation_sha256": observation_sha256,
        "largecap_observation_generated_at": observation.get("generated_at"),
        "largecap_market_data_asof": observation.get("market_data_asof"),
    })
    lane["evidence_grade"] = "FORWARD_OBSERVATION_RESOLVED" if observation.get("state") == "RESOLVED" else "FORWARD_OBSERVATION_OPEN"
    scorecard = dict(lane.get("scorecard") or {})
    scorecard.update({
        "forward_state": observation.get("state"),
        "forward_sessions_completed": observation.get("sessions_completed"),
        "directional_sign_hit_rate_current": (observation.get("summary") or {}).get("directional_sign_hit_rate"),
        "mean_directional_excess_vs_spy_bps_current": (observation.get("summary") or {}).get("mean_directional_excess_vs_spy_bps"),
        "mean_directional_excess_vs_qqq_bps_current": (observation.get("summary") or {}).get("mean_directional_excess_vs_qqq_bps"),
        "terminal_accuracy_available": observation.get("state") == "RESOLVED",
    })
    lane["scorecard"] = scorecard

    scoreboard.setdefault("coverage", {})["largecap_transport_observer"] = {
        "present": True,
        "state": observation.get("state"),
        "generated_at": observation.get("generated_at"),
        "market_data_asof": observation.get("market_data_asof"),
        "sessions_completed": observation.get("sessions_completed"),
        "source_health": observation.get("source_health"),
        "sha256": observation_sha256,
    }
    scoreboard.setdefault("interpretation", {})["largecap_transport_observation_does_not_grant_allocation_authority"] = True
    scoreboard.setdefault("decision_chain", {}).setdefault("tickers", {})["largecap_transport_forward_observation"] = {
        "state": observation.get("state"),
        "sessions_completed": observation.get("sessions_completed"),
        "summary": observation.get("summary"),
    }
    return scoreboard


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def self_test() -> None:
    dates = pd.to_datetime([
        "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ])
    fake = {
        "CAT": pd.Series([100, 101, 102, 103, 104, 105], index=dates, dtype=float),
        "XOM": pd.Series([100, 99, 98, 97, 96, 95], index=dates, dtype=float),
        "SPY": pd.Series([100, 100.5, 101, 101.5, 102, 102.5], index=dates, dtype=float),
        "QQQ": pd.Series([100, 100.25, 100.5, 100.75, 101, 101.25], index=dates, dtype=float),
    }

    def loader(symbol: str, _start: date, _end: date) -> pd.Series:
        return fake[symbol][fake[symbol].index <= pd.Timestamp(_end)]

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
        "boundaries": {
            "allocation_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "runtime_mutation": False,
            "promotion_authority": False,
        },
    }
    out = build(adapter, date(2026, 1, 9), "2026-01-09T00:00:00+00:00", loader)
    assert out["state"] == "PROSPECTIVE_OPEN"
    assert out["first_registered_at"] == "2026-01-09T00:00:00+00:00"
    recovered_adapter = dict(adapter)
    recovered_adapter["signal_date"] = "2026-09-11"
    recovered = build(recovered_adapter, date(2026, 1, 9), "2026-09-18T06:00:00+00:00", loader)
    assert recovered["first_registered_at"] == "2026-09-18T05:03:20.113496+00:00"
    assert recovered["registration_anchor_source"]["evidence_commit"] == "ae327a88bf02dc55f596416ad563375b0cd076d7"
    assert out["entry_date"] == "2026-01-05"
    assert out["summary"]["directional_sign_hit_rate"] == 1.0
    assert out["source_health"]["all_symbols_share_latest_date"] is True
    assert all(r["prediction_error_bps"] is None for r in out["observations"])
    continued = build(adapter, date(2026, 1, 9), "2026-01-10T00:00:00+00:00", loader, prior=out)
    assert continued["first_registered_at"] == out["first_registered_at"]

    long_dates = pd.bdate_range("2026-01-02", periods=26)
    long_fake = {
        "CAT": pd.Series([100 + i for i in range(len(long_dates))], index=long_dates, dtype=float),
        "XOM": pd.Series([100 - 0.5 * i for i in range(len(long_dates))], index=long_dates, dtype=float),
        "SPY": pd.Series([100 + 0.2 * i for i in range(len(long_dates))], index=long_dates, dtype=float),
        "QQQ": pd.Series([100 + 0.3 * i for i in range(len(long_dates))], index=long_dates, dtype=float),
    }
    def long_loader(symbol: str, _start: date, _end: date) -> pd.Series:
        return long_fake[symbol][long_fake[symbol].index <= pd.Timestamp(_end)]
    late = build(adapter, long_dates[-1].date(), "2026-02-10T00:00:00+00:00", long_loader)
    assert late["state"] == "LATE_REGISTRATION_REJECTED"
    resolved = build(adapter, long_dates[-1].date(), "2026-02-10T00:00:00+00:00", long_loader, prior=out)
    assert resolved["state"] == "RESOLVED"

    score = {"schema": SCOREBOARD_SCHEMA, "lanes": [{"program_id": PROGRAM_ID}], "coverage": {}, "decision_chain": {}}
    score = enrich_scoreboard(score, out, "test-largecap-sha")
    lane = score["lanes"][0]
    assert lane["observation_status"] == "ACTIVE"
    assert lane["scorecard"]["terminal_accuracy_available"] is False
    assert lane["observation_lineage"]["largecap_observation_sha256"] == "test-largecap-sha"
    print("FORWARD_LARGECAP_TRANSPORT_OBSERVER_SELF_TEST=PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--adapter", default="research/current/native_adapters/generalized_largecap_ridge.json")
    p.add_argument("--output")
    p.add_argument("--prior", default="research/current/forward_largecap_transport_observation_r1.json")
    p.add_argument("--scoreboard")
    p.add_argument("--scoreboard-output")
    p.add_argument("--asof")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.output:
        p.error("--output is required unless --self-test")

    adapter = json.loads(Path(args.adapter).read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    asof = date.fromisoformat(args.asof) if args.asof else now.date()
    prior_path = Path(args.prior) if args.prior else None
    prior = (
        json.loads(prior_path.read_text(encoding="utf-8"))
        if prior_path is not None and prior_path.is_file()
        else None
    )
    observation = build(adapter, asof, now.isoformat(), prior=prior)
    output_path = Path(args.output)
    _write(output_path, observation)
    observation_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()

    if args.scoreboard:
        score = json.loads(Path(args.scoreboard).read_text(encoding="utf-8"))
        score = enrich_scoreboard(score, observation, observation_sha256)
        score_out = Path(args.scoreboard_output or args.scoreboard)
        _write(score_out, score)

    print(json.dumps({
        "program_id": PROGRAM_ID,
        "state": observation.get("state"),
        "market_data_asof": observation.get("market_data_asof"),
        "sessions_completed": observation.get("sessions_completed"),
        "summary": observation.get("summary"),
        "observation_sha256": observation_sha256,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
