from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

SCHEMA = "research.currency_hedge_mechanism_forward_r1"
PROGRAM_ID = "DEVELOPED_EXUS_CURRENCY_HEDGE"
REGISTRATION_DATE = date(2026, 9, 13)
ENDPOINT_COST_BPS = 25.0
SYMBOLS = ("HEFA", "IEFA", "DBEF", "EFA", "SPY", "UUP")
FROZEN_SOURCES = {
    "P426_HEFA": {
        "ref": "95a5c966f64f2f680b0c4d22f73b00938e726c7a",
        "path": "research/p426_hefa_currency_hedge_r1.py",
        "blob": "8e783a07b78f4f6efee8963c1d05f07792c12bff",
    },
    "P428_DBEF": {
        "ref": "deddf9d0d8507169eeeb063a14747527e3a4d14e",
        "path": "research/p428_dbef_currency_hedge_replication_r1.py",
        "blob": "f9b0551df904a6234fd6f929eb5b53b7835605fd",
    },
    "P436_REGIME": {
        "ref": "fe674e9b9cff72e9cf758c8bc6548124c6f8cf53",
        "path": "research/p436_currency_hedge_regime_r1.py",
        "blob": "5876281376a298e4738734c98cc4153648085ecb",
    },
}


def _download(asof: date) -> tuple[pd.DataFrame, str]:
    raw = yf.download(
        list(SYMBOLS),
        start="2024-01-01",
        end=(pd.Timestamp(asof) + pd.Timedelta(days=1)).date().isoformat(),
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if raw.empty:
        raise RuntimeError("currency-hedge observer received no market data")
    close = raw["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame()
    if isinstance(close.columns, pd.MultiIndex):
        close.columns = close.columns.get_level_values(-1)
    missing = sorted(set(SYMBOLS) - set(map(str, close.columns)))
    if missing:
        raise RuntimeError(f"currency-hedge observer missing symbols: {missing}")
    panel = close.loc[:, list(SYMBOLS)].astype(float).dropna(how="all")
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
    return panel.dropna(subset=list(SYMBOLS)).index


def _previous_completed_month_end(anchor: date) -> pd.Timestamp:
    return pd.Timestamp(anchor).to_period("M").start_time - pd.Timedelta(days=1)


def _regime(panel: pd.DataFrame, anchor: date) -> dict[str, Any]:
    monthly = panel[["UUP"]].resample("ME").last().dropna()
    uup12 = monthly["UUP"].pct_change(12)
    cut = _previous_completed_month_end(anchor)
    month_key = cut.to_period("M").to_timestamp("M")
    if month_key not in uup12.index or pd.isna(uup12.loc[month_key]):
        raise RuntimeError(f"UUP 12-month regime context unavailable at {month_key.date()}")
    value = float(uup12.loc[month_key])
    return {
        "state": "strong_dollar" if value > 0 else "weak_dollar",
        "prior_completed_month_end": cut.date().isoformat(),
        "prior_completed_12m_uup_return": round(value, 10),
        "rule": "strong_dollar iff prior completed 12-month UUP return > 0; otherwise weak_dollar",
        "timing_authority": False,
    }


def _return_bps(panel: pd.DataFrame, symbol: str, entry: pd.Timestamp, latest: pd.Timestamp) -> float:
    return float((panel.loc[latest, symbol] / panel.loc[entry, symbol] - 1.0) * 10000.0)


def build(asof: date) -> dict[str, Any]:
    panel, digest = _download(asof)
    calendar = _common_calendar(panel)
    regime = _regime(panel, asof)
    eligible = [ts for ts in calendar if ts.date() > REGISTRATION_DATE]
    base = {
        "schema": SCHEMA,
        "program_id": PROGRAM_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_data_asof": asof.isoformat(),
        "registered_at_date": REGISTRATION_DATE.isoformat(),
        "frozen_sources": FROZEN_SOURCES,
        "contract": {
            "implementations": {
                "HEFA": {"matched_control": "IEFA"},
                "DBEF": {"matched_control": "EFA"},
            },
            "opportunity_control": "SPY",
            "cost_bps_each_endpoint": ENDPOINT_COST_BPS,
            "mechanism_summary": "equal mean of HEFA-vs-IEFA and DBEF-vs-EFA matched excess",
            "regime_context": "prior completed 12-month UUP return",
            "regime_is_not_timing_gate": True,
        },
        "regime_context": regime,
        "source": {
            "provider": "Yahoo Finance via yfinance; research-only public data",
            "panel_sha256": digest,
            "symbols": list(SYMBOLS),
        },
        "decision_use": (
            "Prospective replication monitor for the developed-ex-US currency-hedge mechanism. "
            "Judge HEFA and DBEF against their own unhedged controls; report SPY only as opportunity cost."
        ),
        "boundaries": {
            "research_only": True,
            "allocation_authority": False,
            "promotion_authority": False,
            "runtime_authority": False,
            "broker_action": False,
            "live_trading_change": False,
            "hedge_ratio_search": False,
            "product_search": False,
            "regime_rescue": False,
        },
    }
    if not eligible:
        return {
            **base,
            "state": "AWAITING_ENTRY_SESSION",
            "scientific_forward_credit": True,
            "entry": {
                "rule": "first common market-session close after registration",
                "date": None,
            },
            "scorecard": None,
        }

    entry = eligible[0]
    usable = [ts for ts in calendar if ts >= entry and ts.date() <= asof]
    if not usable:
        raise RuntimeError("entry session found but no usable prospective market dates")
    latest = usable[-1]
    round_trip = 2.0 * ENDPOINT_COST_BPS
    gross_hefa = _return_bps(panel, "HEFA", entry, latest)
    gross_dbef = _return_bps(panel, "DBEF", entry, latest)
    ctl_iefa = _return_bps(panel, "IEFA", entry, latest)
    ctl_efa = _return_bps(panel, "EFA", entry, latest)
    spy = _return_bps(panel, "SPY", entry, latest)
    hefa_net = gross_hefa - round_trip
    dbef_net = gross_dbef - round_trip
    hefa_excess = hefa_net - ctl_iefa
    dbef_excess = dbef_net - ctl_efa
    mechanism_excess = 0.5 * (hefa_excess + dbef_excess)
    mechanism_net = 0.5 * (hefa_net + dbef_net)
    return {
        **base,
        "state": "PROSPECTIVE_OPEN",
        "scientific_forward_credit": True,
        "entry": {
            "rule": "first common market-session close after registration",
            "date": entry.date().isoformat(),
        },
        "latest_common_market_date": latest.date().isoformat(),
        "forward_sessions": len(usable),
        "scorecard": {
            "HEFA": {
                "gross_return_bps": round(gross_hefa, 4),
                "net_if_flattened_now_bps": round(hefa_net, 4),
                "IEFA_return_bps": round(ctl_iefa, 4),
                "matched_excess_if_flattened_now_bps": round(hefa_excess, 4),
            },
            "DBEF": {
                "gross_return_bps": round(gross_dbef, 4),
                "net_if_flattened_now_bps": round(dbef_net, 4),
                "EFA_return_bps": round(ctl_efa, 4),
                "matched_excess_if_flattened_now_bps": round(dbef_excess, 4),
            },
            "mechanism": {
                "mean_net_if_flattened_now_bps": round(mechanism_net, 4),
                "mean_matched_excess_if_flattened_now_bps": round(mechanism_excess, 4),
                "SPY_return_bps": round(spy, 4),
                "opportunity_excess_vs_SPY_bps": round(mechanism_net - spy, 4),
                "both_implementations_positive_vs_matched": bool(hefa_excess > 0 and dbef_excess > 0),
            },
            "cost_interpretation": {
                "entry_cost_bps": ENDPOINT_COST_BPS,
                "hypothetical_exit_cost_bps": ENDPOINT_COST_BPS,
                "reported_net_is_if_flattened_now": True,
            },
        },
    }


def self_test() -> None:
    assert REGISTRATION_DATE == date(2026, 9, 13)
    assert ENDPOINT_COST_BPS == 25.0
    assert FROZEN_SOURCES["P426_HEFA"]["blob"] == "8e783a07b78f4f6efee8963c1d05f07792c12bff"
    assert FROZEN_SOURCES["P428_DBEF"]["blob"] == "f9b0551df904a6234fd6f929eb5b53b7835605fd"
    assert FROZEN_SOURCES["P436_REGIME"]["blob"] == "5876281376a298e4738734c98cc4153648085ecb"
    assert _previous_completed_month_end(date(2026, 9, 13)).date() == date(2026, 8, 31)
    assert _previous_completed_month_end(date(2026, 10, 1)).date() == date(2026, 9, 30)
    print("CURRENCY_HEDGE_MECHANISM_FORWARD_SELF_TEST=PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof")
    parser.add_argument("--output", default="artifacts/currency_hedge_mechanism_forward_r1.json")
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
        "entry": result["entry"],
        "regime": result["regime_context"],
        "scorecard": result["scorecard"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
