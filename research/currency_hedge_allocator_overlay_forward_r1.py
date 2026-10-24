from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

import pandas as pd
import yfinance as yf

SCHEMA = "research.currency_hedge_allocator_overlay_forward_r1"
PROGRAM_ID = "CURRENCY_HEDGE_ALLOCATOR_OVERLAY"
SESSION_SETTLE_ET = dt_time(18, 30)


def _completed_market_data_date(now_utc: datetime) -> date:
    eastern = now_utc.astimezone(ZoneInfo("America/New_York"))
    return eastern.date() if eastern.time() >= SESSION_SETTLE_ET else eastern.date() - timedelta(days=1)


REGISTRATION_DATE = date(2026, 9, 13)
OVERLAY_WEIGHT = 0.05
ENDPOINT_COST_BPS = 25.0
FROZEN_ALLOCATOR_COMMIT = "6a800febaf1232fe77cd377ab28cd70e380fb8e0"
FROZEN_ALLOCATOR_BLOB = "c1af1ffa76aeb8db6538f0813721382e88be0151"
FROZEN_CURRENCY_OBSERVER_BLOB = "0dd0311365dd5e147fd69ef9d35aa3dc92fd66fc"

# Source-event valuation is separate from the Yahoo price panel. Eligible BZH
# shares converted to a $33.50 cash right on 2026-10-20 (SEC 8-K). No traded
# BZH close exists after the 2026-10-19 session. Do not create one.
BZH_MERGER_EFFECTIVE = pd.Timestamp("2026-10-20")
BZH_LAST_TRADE = pd.Timestamp("2026-10-19")
BZH_CASH_RIGHT_USD = 33.50
BZH_ENTRY_RAW_REFERENCE = 33.23
BZH_LAST_RAW_REFERENCE = 33.48
BZH_RAW_BASIS_TOLERANCE_USD = 0.05
BZH_ISSUER_FILING = (
    "https://www.sec.gov/Archives/edgar/data/915840/"
    "000110465926117198/tm2622398d20_8k.htm"
)


def _bzh_receivable_value(panel: pd.DataFrame, entry: pd.Timestamp, latest: pd.Timestamp) -> float:
    """Mark the nontrading cash right without inventing a BZH market close."""
    if latest < BZH_MERGER_EFFECTIVE:
        return float(panel.loc[latest, "BZH"])
    if entry >= BZH_MERGER_EFFECTIVE or BZH_LAST_TRADE not in panel.index:
        raise RuntimeError("BZH_CASH_MERGER_ENTRY_OR_LAST_TRADE_MISSING")
    if panel.loc[panel.index >= BZH_MERGER_EFFECTIVE, "BZH"].notna().any():
        raise RuntimeError("BZH_CASH_MERGER_POST_EVENT_PRICE_NOT_ADMITTED")
    # The original Yahoo panel is auto_adjust=True. Independently observed
    # raw SIP references bound the 2026 entry and last pre-event close.
    # If a corporate action or vendor revision changes the basis, fail closed
    # rather than divide raw merger dollars by adjusted-share units.
    entry_px = float(panel.loc[entry, "BZH"])
    last_px = float(panel.loc[BZH_LAST_TRADE, "BZH"])
    if (not pd.notna(entry_px) or not pd.notna(last_px)
            or abs(entry_px - BZH_ENTRY_RAW_REFERENCE) > BZH_RAW_BASIS_TOLERANCE_USD
            or abs(last_px - BZH_LAST_RAW_REFERENCE) > BZH_RAW_BASIS_TOLERANCE_USD):
        raise RuntimeError("BZH_CASH_MERGER_ADJUSTED_RAW_BASIS_UNVERIFIED")
    return BZH_CASH_RIGHT_USD

FROZEN_ALLOCATOR_WEIGHTS = {
    "AVDV": 0.1,
    "AVUV": 0.1,
    "BZH": 0.0125,
    "CASH": 0.1,
    "CCS": 0.0125,
    "DBC": 0.05,
    "HOV": 0.0125,
    "IGV": 0.0333333333,
    "MHO": 0.0125,
    "QQQ": 0.05,
    "SMH": 0.05,
    "SOXX": 0.2333333333,
    "XBI": 0.1,
    "XPH": 0.0666666667,
    "XSD": 0.0666666667,
}


def _variant(kind: str) -> dict[str, float]:
    w = dict(FROZEN_ALLOCATOR_WEIGHTS)
    if kind == "incumbent":
        return w
    w["CASH"] -= OVERLAY_WEIGHT
    if kind == "hedged":
        w["HEFA"] = OVERLAY_WEIGHT / 2.0
        w["DBEF"] = OVERLAY_WEIGHT / 2.0
    elif kind == "unhedged":
        w["IEFA"] = OVERLAY_WEIGHT / 2.0
        w["EFA"] = OVERLAY_WEIGHT / 2.0
    elif kind == "spy":
        w["SPY"] = OVERLAY_WEIGHT
    else:
        raise ValueError(kind)
    return dict(sorted(w.items()))


INCUMBENT = _variant("incumbent")
HEDGED = _variant("hedged")
UNHEDGED = _variant("unhedged")
SPY_OPPORTUNITY = _variant("spy")
MARKET_SYMBOLS = tuple(
    sorted((set(INCUMBENT) | set(HEDGED) | set(UNHEDGED) | set(SPY_OPPORTUNITY)) - {"CASH"})
)


def _download(asof: date) -> tuple[pd.DataFrame, str]:
    raw = yf.download(
        list(MARKET_SYMBOLS),
        start="2026-09-10",
        end=(pd.Timestamp(asof) + pd.Timedelta(days=1)).date().isoformat(),
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if raw.empty:
        raise RuntimeError("allocator-overlay observer received no market data")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(close, pd.Series):
        close = close.to_frame()
    if isinstance(close.columns, pd.MultiIndex):
        close.columns = close.columns.get_level_values(-1)
    missing = sorted(set(MARKET_SYMBOLS) - set(map(str, close.columns)))
    if missing:
        raise RuntimeError(f"allocator-overlay observer missing symbols: {missing}")
    panel = close.loc[:, list(MARKET_SYMBOLS)].astype(float).dropna(how="all")
    idx = pd.to_datetime(panel.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(None)
    panel.index = pd.DatetimeIndex(idx).normalize()
    panel = panel[~panel.index.duplicated(keep="last")].sort_index()
    digest = hashlib.sha256(
        panel.reset_index().to_csv(index=False, float_format="%.10g").encode("utf-8")
    ).hexdigest()
    return panel, digest


def _common_calendar(panel: pd.DataFrame) -> pd.DatetimeIndex:
    """Require real closes for every active symbol, except a cash-converted BZH.

    Preserve calendar sessions after the issuer-confirmed terminal event while
    leaving the BZH raw price column NaN. Missing other closes fail closed.
    """
    eligible = panel.loc[panel.index.date > REGISTRATION_DATE]
    if eligible.empty:
        return panel.dropna(subset=list(MARKET_SYMBOLS)).index
    active = [symbol for symbol in MARKET_SYMBOLS if symbol != "BZH"]
    if eligible.loc[:, active].isna().any().any():
        raise RuntimeError("INCOMPLETE_ACTIVE_SYMBOL_FORWARD_CLOSES")
    before = eligible.loc[eligible.index < BZH_MERGER_EFFECTIVE]
    after = eligible.loc[eligible.index >= BZH_MERGER_EFFECTIVE]
    if before["BZH"].isna().any():
        raise RuntimeError("BZH_PRE_MERGER_SOURCE_GAP")
    if after["BZH"].notna().any():
        raise RuntimeError("BZH_POST_MERGER_PRICE_MUST_REMAIN_MISSING")
    return eligible.index


def _portfolio_return_bps(weights: dict[str, float], panel: pd.DataFrame, entry: pd.Timestamp, latest: pd.Timestamp) -> float:
    total = 0.0
    for symbol, weight in weights.items():
        if symbol == "CASH" or weight == 0.0:
            continue
        mark = (
            _bzh_receivable_value(panel, entry, latest)
            if symbol == "BZH" else float(panel.loc[latest, symbol])
        )
        total += weight * (mark / float(panel.loc[entry, symbol]) - 1.0)
    return total * 10000.0


def _overlay_roundtrip_cost_bps() -> float:
    return OVERLAY_WEIGHT * 2.0 * ENDPOINT_COST_BPS


def _validate_contract() -> None:
    if "CASH" in MARKET_SYMBOLS:
        raise RuntimeError("cash accounting key leaked into market-data symbols")
    for name, weights in {
        "incumbent": INCUMBENT,
        "hedged": HEDGED,
        "unhedged": UNHEDGED,
        "spy": SPY_OPPORTUNITY,
    }.items():
        if abs(sum(weights.values()) - 1.0) > 1e-9:
            raise RuntimeError(f"{name} weights do not sum to one")
        if min(weights.values()) < -1e-12:
            raise RuntimeError(f"{name} contains negative weight")
    if FROZEN_ALLOCATOR_WEIGHTS["CASH"] < OVERLAY_WEIGHT:
        raise RuntimeError("overlay exceeds frozen cash funding")
    if HEDGED["CASH"] != 0.05 or UNHEDGED["CASH"] != 0.05 or SPY_OPPORTUNITY["CASH"] != 0.05:
        raise RuntimeError("overlay funding must reduce cash from 10% to 5%")
    if abs(HEDGED["HEFA"] - 0.025) > 1e-12 or abs(HEDGED["DBEF"] - 0.025) > 1e-12:
        raise RuntimeError("hedged implementation weights changed")
    if abs(UNHEDGED["IEFA"] - 0.025) > 1e-12 or abs(UNHEDGED["EFA"] - 0.025) > 1e-12:
        raise RuntimeError("unhedged matched weights changed")


def build(asof: date) -> dict[str, Any]:
    _validate_contract()
    panel, digest = _download(asof)
    calendar = _common_calendar(panel)
    eligible = [ts for ts in calendar if ts.date() > REGISTRATION_DATE]
    base: dict[str, Any] = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_data_asof": asof.isoformat(),
        "registered_at_date": REGISTRATION_DATE.isoformat(),
        "contract": {
            "incumbent": "frozen deterministic allocator target published 2026-09-13",
            "challenger": "incumbent with 5% cash replaced by 2.5% HEFA + 2.5% DBEF",
            "matched_control": "incumbent with 5% cash replaced by 2.5% IEFA + 2.5% EFA",
            "opportunity_control": "incumbent with 5% cash replaced by 5% SPY",
            "overlay_weight": OVERLAY_WEIGHT,
            "funding_source": "CASH_ONLY",
            "gross_cap": 1.0,
            "leverage": False,
            "entry_rule": "first common market-session close after registration",
            "holding_rule": "buy-and-hold frozen registration weights; no rebalance or allocator mutation",
            "cost_bps_each_endpoint_on_overlay_notional": ENDPOINT_COST_BPS,
            "no_weight_product_date_cost_or_regime_search": True,
        },
        "source_pins": {
            "frozen_allocator_commit": FROZEN_ALLOCATOR_COMMIT,
            "frozen_allocator_blob": FROZEN_ALLOCATOR_BLOB,
            "currency_mechanism_current_blob": FROZEN_CURRENCY_OBSERVER_BLOB,
        },
        "positions": {
            "incumbent": INCUMBENT,
            "hedged_challenger": HEDGED,
            "unhedged_matched_control": UNHEDGED,
            "spy_opportunity_control": SPY_OPPORTUNITY,
        },
        "source": {
            "provider": "Yahoo Finance via yfinance; research-only public data",
            "panel_sha256": digest,
            "symbols": list(MARKET_SYMBOLS),
            "bzh_issuer_cash_merger": {
                "effective_date": BZH_MERGER_EFFECTIVE.date().isoformat(),
                "last_traded_date": BZH_LAST_TRADE.date().isoformat(),
                "cash_right_per_eligible_share_usd": BZH_CASH_RIGHT_USD,
                "issuer": BZH_ISSUER_FILING,
                "provider_payable_date": "2026-10-21",
                "receivable_not_trading_cash": True,
                "price_panel_not_filled_or_synthesized": True,
                "valuation_applies": asof >= BZH_MERGER_EFFECTIVE.date(),
                "raw_vs_adjusted_basis_requires_reference_check": True,
                "same_issuer_event_all_four_frozen_arms": True,
            },
        },
        "decision_use": (
            "Prospective portfolio-level falsifier: determine whether the replicated developed-ex-US currency hedge "
            "improves the actual frozen allocator target beyond both unchanged cash and an equal unhedged developed-ex-US overlay."
        ),
        "boundaries": {
            "research_only": True,
            "allocation_authority": False,
            "promotion_authority": False,
            "runtime_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "allocator_mutation": False,
            "currency_mechanism_mutation": False,
        },
    }
    if not eligible:
        return {
            **base,
            "state": "AWAITING_ENTRY_SESSION",
            "scientific_forward_credit": True,
            "entry_date": None,
            "latest_common_market_date": None,
            "forward_sessions": 0,
            "market_sessions_observed_including_entry": 0,
            "elapsed_close_to_close_sessions": 0,
            "forward_session_clock_semantics": "forward_sessions is legacy inclusive-entry count; elapsed_close_to_close_sessions is the cross-program comparable elapsed clock",
            "scorecard": None,
        }

    entry = eligible[0]
    usable = [ts for ts in calendar if ts >= entry and ts.date() <= asof]
    if not usable:
        raise RuntimeError("entry session found but no usable prospective dates")
    latest = usable[-1]
    incumbent_bps = _portfolio_return_bps(INCUMBENT, panel, entry, latest)
    hedged_gross_bps = _portfolio_return_bps(HEDGED, panel, entry, latest)
    unhedged_gross_bps = _portfolio_return_bps(UNHEDGED, panel, entry, latest)
    spy_gross_bps = _portfolio_return_bps(SPY_OPPORTUNITY, panel, entry, latest)
    cost_bps = _overlay_roundtrip_cost_bps()
    hedged_net_bps = hedged_gross_bps - cost_bps
    unhedged_net_bps = unhedged_gross_bps - cost_bps
    spy_net_bps = spy_gross_bps - cost_bps
    return {
        **base,
        "state": "PROSPECTIVE_OPEN",
        "scientific_forward_credit": True,
        "entry_date": entry.date().isoformat(),
        "latest_common_market_date": latest.date().isoformat(),
        "forward_sessions": len(usable),
        "market_sessions_observed_including_entry": len(usable),
        "elapsed_close_to_close_sessions": max(0, len(usable) - 1),
        "forward_session_clock_semantics": "forward_sessions is legacy inclusive-entry count; elapsed_close_to_close_sessions is the cross-program comparable elapsed clock",
        "scorecard": {
            "incumbent_return_bps": round(incumbent_bps, 4),
            "hedged_challenger": {
                "gross_return_bps": round(hedged_gross_bps, 4),
                "net_if_flattened_now_bps": round(hedged_net_bps, 4),
                "excess_vs_incumbent_bps": round(hedged_net_bps - incumbent_bps, 4),
            },
            "unhedged_matched_control": {
                "gross_return_bps": round(unhedged_gross_bps, 4),
                "net_if_flattened_now_bps": round(unhedged_net_bps, 4),
                "excess_vs_incumbent_bps": round(unhedged_net_bps - incumbent_bps, 4),
            },
            "spy_opportunity_control": {
                "gross_return_bps": round(spy_gross_bps, 4),
                "net_if_flattened_now_bps": round(spy_net_bps, 4),
                "excess_vs_incumbent_bps": round(spy_net_bps - incumbent_bps, 4),
            },
            "mechanism_attribution": {
                "hedged_minus_unhedged_bps": round(hedged_net_bps - unhedged_net_bps, 4),
                "hedged_minus_spy_overlay_bps": round(hedged_net_bps - spy_net_bps, 4),
                "portfolio_improvement_and_hedge_edge_both_positive": bool(
                    hedged_net_bps > incumbent_bps and hedged_net_bps > unhedged_net_bps
                ),
            },
            "cost_interpretation": {
                "overlay_notional": OVERLAY_WEIGHT,
                "entry_cost_bps_on_overlay": ENDPOINT_COST_BPS,
                "hypothetical_exit_cost_bps_on_overlay": ENDPOINT_COST_BPS,
                "portfolio_roundtrip_cost_bps_if_flattened_now": round(cost_bps, 4),
            },
        },
    }


def self_test() -> None:
    # A genuine source gap in the delisted stock is not a synthetic flat close.
    ix = pd.DatetimeIndex(["2026-09-14", "2026-10-19", "2026-10-20"])
    tiny = pd.DataFrame(1.0, index=ix, columns=list(MARKET_SYMBOLS))
    tiny.loc[ix[0], "BZH"] = 33.23
    tiny.loc[ix[1], "BZH"] = 33.48
    tiny.loc[ix[2], "BZH"] = float("nan")
    assert len(_common_calendar(tiny)) == 3
    expected = 0.0125 * (33.50 / 33.23 - 1.0) * 10000.0
    actual = _portfolio_return_bps({"BZH": 0.0125}, tiny, ix[0], ix[2])
    assert abs(actual - expected) < 1e-10
    assert pd.isna(tiny.loc[ix[2], "BZH"])  # no invented post-merger price
    broken = tiny.copy()
    broken.loc[ix[2], "BZH"] = 33.50
    try:
        _common_calendar(broken)
    except RuntimeError as exc:
        assert "BZH_POST_MERGER_PRICE" in str(exc)
    else:
        raise AssertionError("synthetic post-merger BZH price was accepted")
    synthetic = [pd.Timestamp("2026-09-14"), pd.Timestamp("2026-09-15"), pd.Timestamp("2026-09-16")]
    assert len(synthetic) == 3
    assert max(0, len(synthetic) - 1) == 2
    assert _completed_market_data_date(datetime(2026, 9, 29, 18, 43, tzinfo=timezone.utc)) == date(2026, 9, 28)
    assert _completed_market_data_date(datetime(2026, 9, 29, 23, 10, tzinfo=timezone.utc)) == date(2026, 9, 29)
    _validate_contract()
    assert REGISTRATION_DATE == date(2026, 9, 13)
    assert FROZEN_ALLOCATOR_COMMIT == "6a800febaf1232fe77cd377ab28cd70e380fb8e0"
    assert FROZEN_ALLOCATOR_BLOB == "c1af1ffa76aeb8db6538f0813721382e88be0151"
    assert FROZEN_CURRENCY_OBSERVER_BLOB == "0dd0311365dd5e147fd69ef9d35aa3dc92fd66fc"
    assert "CASH" not in MARKET_SYMBOLS
    assert abs(_overlay_roundtrip_cost_bps() - 2.5) < 1e-12
    assert INCUMBENT["CASH"] == 0.1
    assert HEDGED["CASH"] == 0.05
    assert HEDGED["HEFA"] == HEDGED["DBEF"] == 0.025
    assert UNHEDGED["IEFA"] == UNHEDGED["EFA"] == 0.025
    assert SPY_OPPORTUNITY["SPY"] == 0.05
    print("CURRENCY_HEDGE_ALLOCATOR_OVERLAY_FORWARD_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof")
    parser.add_argument("--output", default="artifacts/currency_hedge_allocator_overlay_forward_r1.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    now = datetime.now(timezone.utc)
    asof = date.fromisoformat(args.asof) if args.asof else _completed_market_data_date(now)
    result = build(asof)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({
        "state": result["state"],
        "entry_date": result["entry_date"],
        "forward_sessions": result["forward_sessions"],
        "scorecard": result["scorecard"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
