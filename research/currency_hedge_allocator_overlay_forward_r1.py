from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

SCHEMA = "research.currency_hedge_allocator_overlay_forward_r1"
PROGRAM_ID = "CURRENCY_HEDGE_ALLOCATOR_OVERLAY"
REGISTRATION_DATE = date(2026, 9, 13)
OVERLAY_WEIGHT = 0.05
ENDPOINT_COST_BPS = 25.0
FROZEN_ALLOCATOR_COMMIT = "6a800febaf1232fe77cd377ab28cd70e380fb8e0"
FROZEN_ALLOCATOR_BLOB = "c1af1ffa76aeb8db6538f0813721382e88be0151"
FROZEN_CURRENCY_OBSERVER_BLOB = "0dd0311365dd5e147fd69ef9d35aa3dc92fd66fc"

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
    return panel.dropna(subset=list(MARKET_SYMBOLS)).index


def _portfolio_return_bps(weights: dict[str, float], panel: pd.DataFrame, entry: pd.Timestamp, latest: pd.Timestamp) -> float:
    total = 0.0
    for symbol, weight in weights.items():
        if symbol == "CASH" or weight == 0.0:
            continue
        total += weight * (float(panel.loc[latest, symbol]) / float(panel.loc[entry, symbol]) - 1.0)
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
    asof = date.fromisoformat(args.asof) if args.asof else datetime.now(timezone.utc).date()
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
