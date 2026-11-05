from __future__ import annotations

"""Prospective, fixed-weight persistence falsifier for the September Ridge signal.

This is NOT a regenerated Ridge prediction or a new qualifying model cohort.
The September 11 public 13-stock weights remain immutable. A later, separately
predeclared November 6 close entry tests only their out-of-sample persistence.
No broker, portfolio allocator, private source or model-promotion authority.
"""

import argparse
import hashlib
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = "research.ridge_frozen_weight_persistence_forward_r1"
CONTRACT_SCHEMA = "research.ridge_weight_persistence_freeze.v1"
SOURCE_ADAPTER = Path("research/current/native_adapters/semiconductor_shared_ridge.json")
SOURCE_ADAPTER_BLOB = "05238d7c359ea59495100711f37d6f88cc095816"
CONTRACT_PATH = Path("research/contracts/ridge_weight_persistence_20261105.v1.json")
ENTRY_DATE = date(2026, 11, 6)
HOLD_SESSIONS = 20
STOCK_ROUND_TRIP_BPS = 25.0
SMH_ROUND_TRIP_BPS = 10.0
FROZEN_SYMBOLS = frozenset((
    "ADI", "AMAT", "AMD", "APH", "AVGO", "KLAC", "LRCX",
    "MCHP", "MRVL", "MU", "NVDA", "NXPI", "TXN",
))
BOUNDARIES = {
    "research_only": True,
    "new_model_prediction": False,
    "original_shared_ridge_h20_cohort": False,
    "signed_model_promotion": False,
    "allocation_authority": False,
    "broker_action": False,
    "live_trading_change": False,
    "paper_broker_fill": False,
}


def _read_frozen_weights(adapter_path: Path = SOURCE_ADAPTER) -> dict[str, float]:
    raw = adapter_path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\\0" + raw).hexdigest()
    if blob != SOURCE_ADAPTER_BLOB:
        raise RuntimeError("FROZEN_ADAPTER_BLOB_CHANGED")
    adapter = json.loads(raw)
    if (adapter.get("schema") != "foundry.forward_program_adapter.v1"
            or adapter.get("program_id") != "SEMICONDUCTOR_SHARED_RIDGE"
            or adapter.get("signal_date") != "2026-09-11"):
        raise RuntimeError("FROZEN_MODEL_IDENTITY_CHANGED")
    book = ((adapter.get("paper_action") or {}).get("ticker_book") or {})
    capital_weights = book.get("cohort_target_weights_nav") or {}
    if set(capital_weights) != FROZEN_SYMBOLS:
        raise RuntimeError("FROZEN_UNIVERSE_CHANGED")
    values = {s: float(capital_weights[s]) for s in sorted(FROZEN_SYMBOLS)}
    if (any(not math.isfinite(w) or w <= 0 for w in values.values())
            or abs(sum(values.values()) - 0.05) > 1e-8):
        raise RuntimeError("FROZEN_5PCT_SLEEVE_WEIGHTS_INVALID")
    return {s: w / sum(values.values()) for s, w in values.items()}


def _read_contract(path: Path = CONTRACT_PATH) -> dict:
    c = json.loads(path.read_text(encoding="utf-8"))
    if (c.get("schema") != CONTRACT_SCHEMA
            or c.get("entry_date") != ENTRY_DATE.isoformat()
            or c.get("hold_sessions") != HOLD_SESSIONS
            or c.get("original_adapter_git_blob") != SOURCE_ADAPTER_BLOB
            or c.get("model_prediction_retrained") is not False
            or c.get("scientific_promotion_authority") is not False):
        raise RuntimeError("FROZEN_PERSISTENCE_CONTRACT_INVALID")
    frozen = datetime.fromisoformat(c["freeze_observed_at_utc"].replace("Z", "+00:00"))
    if frozen.tzinfo is None or not (frozen < datetime(2026, 11, 6, 21, 0, tzinfo=timezone.utc)):
        raise RuntimeError("FROZEN_PERSISTENCE_AFTER_ENTRY")
    if not isinstance(c.get("freeze_source_commit_sha"), str) or len(c["freeze_source_commit_sha"]) != 40:
        raise RuntimeError("FROZEN_PERSISTENCE_SOURCE_UNPINNED")
    return c


def _calendar_and_asof(now: datetime) -> tuple[list[str], str | None]:
    import pandas_market_calendars as mcal
    market = mcal.get_calendar("NYSE")
    dates = [d.date().isoformat() for d in market.schedule(
        start_date=ENTRY_DATE.isoformat(), end_date=(ENTRY_DATE + timedelta(days=65)).isoformat()
    ).index]
    if len(dates) <= HOLD_SESSIONS or dates[0] != ENTRY_DATE.isoformat():
        raise RuntimeError("FROZEN_ENTRY_OR_H20_MARKET_CALENDAR_INVALID")
    local = now.astimezone(ZoneInfo("America/New_York"))
    cutoff = local.date()
    if local.timetz().replace(tzinfo=None) < time(18, 30):
        cutoff -= timedelta(days=1)
    admissible = [d for d in dates if d <= cutoff.isoformat()]
    return dates, (admissible[-1] if admissible else None)


def evaluate(
    weights: dict[str, float], sessions: list[str],
    close_by_symbol: dict[str, dict[str, float]], latest_asof: str,
) -> dict:
    if sessions[0] != ENTRY_DATE.isoformat() or len(sessions) <= HOLD_SESSIONS:
        raise RuntimeError("FROZEN_ENTRY_SESSION_MISMATCH")
    if set(weights) != FROZEN_SYMBOLS or set(close_by_symbol) != FROZEN_SYMBOLS | {"SMH"}:
        raise RuntimeError("FROZEN_PORTFOLIO_MEMBERSHIP_MISMATCH")
    eligible = [d for d in sessions[:HOLD_SESSIONS + 1] if d <= latest_asof]
    if not eligible:
        raise RuntimeError("ENTRY_PRICE_NOT_FINAL")
    current_date = eligible[-1]
    for symbol, bars in close_by_symbol.items():
        if set(bars) != set(eligible):
            raise RuntimeError("PROVIDER_COMMON_SESSION_GAP")
        if any(not isinstance(v, (float, int)) or isinstance(v, bool)
               or not math.isfinite(v) or v <= 0 for v in bars.values()):
            raise RuntimeError("PROVIDER_PRICE_INVALID")
    entry = eligible[0]
    elapsed = len(eligible) - 1
    done = elapsed == HOLD_SESSIONS
    total = sum(
        weights[s] * close_by_symbol[s][current_date] / close_by_symbol[s][entry]
        for s in sorted(FROZEN_SYMBOLS)
    )
    equal = sum(
        close_by_symbol[s][current_date] / close_by_symbol[s][entry]
        for s in sorted(FROZEN_SYMBOLS)
    ) / len(FROZEN_SYMBOLS)
    smh = close_by_symbol["SMH"][current_date] / close_by_symbol["SMH"][entry]
    # Half the frozen round-trip friction at initial close, half on actual H20 exit.
    stock_multiplier = (1 - STOCK_ROUND_TRIP_BPS / 20000) * (
        (1 - STOCK_ROUND_TRIP_BPS / 20000) if done else 1
    )
    smh_multiplier = (1 - SMH_ROUND_TRIP_BPS / 20000) * (
        (1 - SMH_ROUND_TRIP_BPS / 20000) if done else 1
    )
    book = total * stock_multiplier
    equal_nav = equal * stock_multiplier
    smh_nav = smh * smh_multiplier
    return {
        "status": "RESOLVED" if done else "OPEN",
        "entry_date": entry,
        "latest_completed_session": current_date,
        "exit_date": sessions[HOLD_SESSIONS],
        "elapsed_post_entry_sessions": elapsed,
        "remaining_sessions": HOLD_SESSIONS - elapsed,
        "book_nav": round(book, 10),
        "equal13_nav": round(equal_nav, 10),
        "smh_nav": round(smh_nav, 10),
        "book_return_bps": round((book - 1) * 10000, 4),
        "book_minus_smh_matched_net_bps": round((book - smh_nav) * 10000, 4),
        "book_minus_equal13_matched_net_bps": round((book - equal_nav) * 10000, 4),
        "matched_cost_convention": "half_roundtrip_entry_remaining_half_only_on_H20_exit",
        "terminal_exit_cost_charged": done,
        "is_new_native_ridge_prediction": False,
        "promotion_authority": False,
    }


def _provider_closes(symbols: list[str], dates: list[str]) -> dict[str, dict[str, float]]:
    import yfinance as yf
    start = dates[0]
    end = (date.fromisoformat(dates[-1]) + timedelta(days=1)).isoformat()
    frame = yf.download(
        symbols, start=start, end=end, interval="1d", auto_adjust=True,
        progress=False, threads=False, group_by="column",
    )
    if frame is None or frame.empty or "Close" not in frame:
        raise RuntimeError("PROVIDER_ADJUSTED_CLOSE_UNAVAILABLE")
    panel = frame["Close"]
    result: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        if symbol not in panel.columns:
            raise RuntimeError("PROVIDER_SYMBOL_UNAVAILABLE")
        values = {idx.date().isoformat(): float(v) for idx, v in panel[symbol].items()
                  if idx.date().isoformat() in dates}
        result[symbol] = values
    return result


def build(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    contract = _read_contract()
    weights = _read_frozen_weights()
    sessions, asof = _calendar_and_asof(now)
    result = {
        "schema": SCHEMA,
        "generated_at_utc": now.isoformat(),
        "program_id": "RIDGE_FROZEN_WEIGHT_PERSISTENCE_DIAGNOSTIC",
        "source_model": "SEMICONDUCTOR_SHARED_RIDGE",
        "source_signal_date": "2026-09-11",
        "freeze_source_commit_sha": contract["freeze_source_commit_sha"],
        "freeze_observed_at_utc": contract["freeze_observed_at_utc"],
        "original_adapter_git_blob": SOURCE_ADAPTER_BLOB,
        "frozen_symbols": sorted(FROZEN_SYMBOLS),
        "holding": "fixed_initial_shares_no_interim_rebalance",
        "research_cost_bps": {"stock_round_trip": STOCK_ROUND_TRIP_BPS, "smh_round_trip": SMH_ROUND_TRIP_BPS},
        "data_source": "yfinance_adjusted_close_public_research_only_not_broker_fills_or_original_issuer_admission",
        "boundaries": BOUNDARIES,
    }
    if asof is None:
        result["forward"] = {"status": "AWAITING_ENTRY_FINALITY", "entry_date": ENTRY_DATE.isoformat(),
                             "elapsed_post_entry_sessions": 0, "exit_date": sessions[HOLD_SESSIONS],
                             "promotion_authority": False}
        return result
    scored_dates = [d for d in sessions[:HOLD_SESSIONS + 1] if d <= asof]
    prices = _provider_closes(sorted(FROZEN_SYMBOLS | {"SMH"}), scored_dates)
    result["forward"] = evaluate(weights, sessions, prices, asof)
    return result


def self_test() -> None:
    assert len(FROZEN_SYMBOLS) == 13
    sessions = [(ENTRY_DATE + timedelta(days=i)).isoformat() for i in range(21)]
    weights = {s: 1 / 13 for s in FROZEN_SYMBOLS}
    prices = {s: {d: 100.0 + (2 if i > 0 else 0) for i, d in enumerate(sessions)}
              for s in FROZEN_SYMBOLS | {"SMH"}}
    for i, d in enumerate(sessions):
        prices["SMH"][d] = 100.0 + i
    open_result = evaluate(weights, sessions, {s: {d: v for d, v in bar.items() if d <= sessions[1]}
                                                for s, bar in prices.items()}, sessions[1])
    assert open_result["status"] == "OPEN"
    assert open_result["elapsed_post_entry_sessions"] == 1
    assert open_result["terminal_exit_cost_charged"] is False
    assert open_result["book_minus_equal13_matched_net_bps"] == 0
    final = evaluate(weights, sessions, prices, sessions[-1])
    assert final["status"] == "RESOLVED" and final["elapsed_post_entry_sessions"] == 20
    assert final["book_minus_smh_matched_net_bps"] < 0
    assert final["terminal_exit_cost_charged"] is True
    assert final["promotion_authority"] is False
    try:
        broken = dict(prices)
        broken["ADI"] = dict(prices["ADI"])
        del broken["ADI"][sessions[2]]
        evaluate(weights, sessions, broken, sessions[-1])
    except RuntimeError as exc:
        assert str(exc) == "PROVIDER_COMMON_SESSION_GAP"
    else:
        raise AssertionError("missing symbol date must fail")
    print("RIDGE_FROZEN_WEIGHT_PERSISTENCE_SELF_TEST=PASS")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--output", default="artifacts/ridge_frozen_weight_persistence_forward_r1.json")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    result = build()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\\n", encoding="utf-8")
    print("RIDGE_PERSISTENCE", result["forward"]["status"],
          result["forward"].get("latest_completed_session", "AWAITING"))


if __name__ == "__main__":
    main()
